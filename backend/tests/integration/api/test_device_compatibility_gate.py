"""Signed device WS checks enforce published compatibility on real dispatch."""

import json
from datetime import UTC, datetime
from functools import partial
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agentplatform.rbac_models import UserModel
from app.device_control.broker import DeviceBroker, TaskStatus
from app.device_control.protocol import MessageType, TaskEnvelope, public_key_text, sign_envelope
from app.device_control.receipt_archive import ReceiptArchive
from app.gateway.authz import get_current_rbac_user
from app.gateway.routers import devices
from deerflow.persistence.base import Base


@pytest_asyncio.fixture
async def device_factory(tmp_path, monkeypatch):
    # Server and fixture run on separate loops. A real file database with
    # independent connections avoids sharing SQLite's in-memory connection.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'devices.db'}", poolclass=NullPool)
    async with engine.begin() as db:
        await db.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(UserModel(id="owner", username="owner@example.com", role="user"))
        await session.commit()
    monkeypatch.setattr(devices, "get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def release(tmp_path, monkeypatch):
    root = tmp_path / "reviewed"
    root.mkdir()
    key = Ed25519PrivateKey.generate()
    trust = tmp_path / "trusted-public.pem"
    trust.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    monkeypatch.setenv("UPDATES_CONTROLLED_DIR", str(root))
    monkeypatch.setenv("UPDATES_TRUSTED_PUBLIC_KEY_FILE", str(trust))
    monkeypatch.setenv("UPDATES_STATE_DIR", str(tmp_path / "compat-state"))
    monkeypatch.setenv("SERVER_RELEASE_VERSION", "server-110-candidate")

    def publish(level="compatible", disabled=None, **extra):
        document = {
            "version": 1,
            "level": level,
            "disabledCapabilities": disabled or [],
            "minProtocol": 1,
            "notes": "T110 fixed reviewed combination",
            "candidateCombo": {"desktop": "0.1.0", "runtime": "3.12.10", "server": "server-110-candidate", "legacyHello": {"runtimeVersion": "0.1.0", "protocolVersion": "1"}},
            **extra,
        }
        raw = json.dumps(document).encode()
        (root / "compatibility.json").write_bytes(raw)
        (root / "compatibility.sig").write_text(key.sign(raw).hex())
        return document

    return root, publish


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_signed_hello_and_dynamic_dispatch_preserve_unknown_history(device_factory, release, monkeypatch, legacy):
    from app.device_control import broker as broker_module

    root, publish = release
    publish()
    archive = ReceiptArchive(device_factory)
    broker = DeviceBroker(receipt_archive=archive)
    monkeypatch.setattr(broker_module, "_broker", broker)
    app = FastAPI()
    app.include_router(devices.router)
    owner = UserModel(id="owner", username="owner@example.com", role="user")
    app.dependency_overrides[get_current_rbac_user] = lambda: owner
    key = Ed25519PrivateKey.generate()
    public = public_key_text(key.public_key())
    with TestClient(app) as client:
        challenge = client.post("/api/devices/pairing").json()
        registration = client.post(
            "/api/devices/register",
            json={"pairing_code": challenge["code"], "name": "T110 isolated runtime", "public_key": public, "protocol_version": "1", "runtime_version": "0.1.0", "capabilities": ["local.files.write", "local.files.read"]},
        ).json()
        device_id = registration["device"]["id"]
        assert client.post(f"/api/devices/pairing/{challenge['pairing_id']}/confirm", json={"code": challenge["code"]}).status_code == 200
        paired = client.post("/api/devices/register/complete", json={"device_id": device_id, "public_key": public, "claim_token": registration["claim_token"]}).json()
        with client.websocket_connect("/api/devices/ws") as ws:
            ws.send_text(
                sign_envelope(
                    private_key=key,
                    message_type=MessageType.HELLO,
                    device_id=device_id,
                    session_id=paired["session_id"],
                    payload={
                        "public_key": public,
                        "session_token": paired["session_token"],
                        "protocol_version": "1",
                        "runtime_version": "0.1.0",
                        **({} if legacy else {"desktop_version": "0.1.0", "runtime_python": "3.12.10"}),
                        "capabilities": ["local.files.write", "local.files.read"],
                    },
                ).model_dump_json(by_alias=True)
            )
            hello = TaskEnvelope.model_validate_json(ws.receive_text())
            assert hello.payload.get("server_version") == "server-110-candidate"
            assert hello.payload["compatibility"]["level"] == "compatible"

            def dispatch(operation):
                return client.portal.call(
                    partial(
                        broker.send_task,
                        device_id=device_id,
                        operation=operation,
                        path="/workspace/12345678-1234-4234-8234-123456789abc/unknown.txt",
                        run_id="run-T110",
                        tool_call_id="call-T110",
                        payload_extra={"thread_id": "thread-T110", "arguments": {"content": "T110-UNKNOWN-KEEP", "path": "/workspace/12345678-1234-4234-8234-123456789abc/unknown.txt"}},
                    )
                )

            original = dispatch("local.files.write")
            signed = TaskEnvelope.model_validate_json(ws.receive_text())
            assert signed.task_id == original.task_id and original.status == TaskStatus.SENT

            # Missing result is preserved as a durable unknown, never rewritten
            # by later compatibility checks.
            original.status = TaskStatus.RESULT_NOT_VERIFIED
            original.error_code = "RESULT_UNCERTAIN"
            client.portal.call(broker._persist_task, original)
            before = client.portal.call(partial(archive.get, original.task_id, owner_id="owner"))

            publish("capability", ["local.files.write"])
            denied = dispatch("local.files.write")
            assert denied.status == TaskStatus.FAILED
            assert denied.error_code == "COMPAT_CAPABILITY_DISABLED"
            unaffected = dispatch("local.files.read")
            assert unaffected.status == TaskStatus.SENT
            assert TaskEnvelope.model_validate_json(ws.receive_text()).task_id == unaffected.task_id

            publish("core")
            core = dispatch("local.files.read")
            assert core.status == TaskStatus.FAILED and core.error_code == "COMPAT_CORE_INCOMPATIBLE"
            assert client.portal.call(partial(archive.get, original.task_id, owner_id="owner")) == before
            publish(minProtocol=2)
            assert dispatch("local.files.read").error_code == "COMPAT_CORE_INCOMPATIBLE"
            publish(candidateCombo={"desktop": "0.2.0", "runtime": "3.12.10", "server": "server-110-candidate"})
            assert dispatch("local.files.read").error_code == "COMPAT_CORE_INCOMPATIBLE"
            publish(
                candidateCombo={"desktop": "0.2.0", "runtime": "3.12.10", "server": "server-110-candidate"},
                supportedCombos=[{"desktop": "0.1.0", "runtime": "3.12.10", "server": "server-110-candidate", "level": "compatible", "disabledCapabilities": [], "legacyHello": {"runtimeVersion": "0.1.0", "protocolVersion": "1"}}],
            )
            restored = dispatch("local.files.read")
            assert restored.status == TaskStatus.SENT
            assert TaskEnvelope.model_validate_json(ws.receive_text()).task_id == restored.task_id
            (root / "compatibility.json").unlink()
            assert dispatch("local.files.read").error_code == "COMPAT_CORE_INCOMPATIBLE"
            assert client.portal.call(partial(archive.get, original.task_id, owner_id="owner")) == before

            # Core restrictions affect admission only. The already executed
            # task's signed receipt still reconciles over the same connection.
            from app.device_control.receipt_archive import receipt_digest

            archived_task = before["task"]
            receipt = {
                "task_id": original.task_id,
                "run_id": "run-T110",
                "capability": "local.files.write",
                "request_hash": archived_task["request_hash"],
                "payload_hash": archived_task["request_hash"],
                "status": "completed",
                "policy_decision": "allow",
                "consent_decision": "approved",
                "result_hash": "1" * 64,
                "finished_at": datetime.now(UTC).isoformat(),
            }
            replay = {"receipt_id": str(uuid4()), "binding": broker.receipt_binding(broker.connections[device_id]), "task": archived_task, "receipt": receipt}
            replay["receipt_hash"] = receipt_digest(replay)
            ws.send_text(sign_envelope(private_key=key, message_type=MessageType.RECEIPT_UPLOAD, device_id=device_id, session_id=paired["session_id"], task_id=original.task_id, payload=replay).model_dump_json(by_alias=True))
            acknowledgment = TaskEnvelope.model_validate_json(ws.receive_text())
            assert acknowledgment.type == MessageType.RECEIPT_ACK
            assert acknowledgment.payload["receipt_hash"] == replay["receipt_hash"]


def test_published_signature_and_exact_version_are_required_and_removal_survives_restart(release):
    import subprocess
    import sys
    from types import SimpleNamespace

    from app.device_control.release_compatibility import evaluate_connection

    root, publish = release
    connection = SimpleNamespace(protocol_version="1", desktop_version="0.1.0", runtime_python="3.12.10")
    publish("capability", ["local.python"])
    assert evaluate_connection(connection).rejection("local.python") == "COMPAT_CAPABILITY_DISABLED"
    assert evaluate_connection(connection).rejection("local.files.read") is None
    (root / "compatibility.sig").write_text("00" * 64)
    assert evaluate_connection(connection).level == "core"
    publish()
    assert evaluate_connection(connection).level == "compatible"
    (root / "compatibility.json").unlink()
    (root / "compatibility.sig").unlink()
    # A fresh interpreter must observe the durable seen marker, not fall back
    # to the first-deployment protocol-1 exception after a restart.
    code = (
        "from app.device_control.release_compatibility import evaluate_connection; "
        "from types import SimpleNamespace; "
        "assert evaluate_connection(SimpleNamespace(protocol_version='1', desktop_version='0.1.0', runtime_python='3.12.10')).level == 'core'"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=15)


def test_legacy_mapping_requires_registered_runtime_and_unambiguous_proof(release):
    from types import SimpleNamespace

    from app.device_control.release_compatibility import evaluate_connection

    _, publish = release
    old = SimpleNamespace(protocol_version="1", runtime_version="0.1.0", registered_runtime_version="0.1.0")
    publish()
    assert evaluate_connection(old).level == "compatible"
    old.registered_runtime_version = "unreviewed"
    assert evaluate_connection(old).level == "core"
    old.registered_runtime_version = "0.1.0"
    publish(candidateCombo={"desktop": "0.1.0", "runtime": "3.12.10", "server": "server-110-candidate"})
    assert evaluate_connection(old).level == "core"
    publish(supportedCombos=[{"desktop": "0.0.9", "runtime": "3.12.10", "server": "server-110-candidate", "legacyHello": {"runtimeVersion": "0.1.0", "protocolVersion": "1"}}])
    assert evaluate_connection(old).level == "core"
