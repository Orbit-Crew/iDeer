"""Public HTTP grants for real paired devices and durable local tasks."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agentplatform.rbac_models import UserModel
from app.device_control.broker import DeviceBroker, DeviceConnection
from app.device_control.protocol import MessageType, public_key_text, sign_envelope
from app.device_control.receipt_archive import ReceiptArchive, receipt_digest
from app.gateway.authz import AuthContext, get_current_rbac_user
from deerflow.persistence.base import Base
from deerflow.persistence.thread_meta.memory import MemoryThreadMetaStore
from deerflow.runtime import RunManager
from tests.integration.api.test_desktop_artifacts import CONTENT, DIGEST, HANDLE, payload


class Socket:
    async def send_text(self, text):
        pass

    async def close(self, **kwargs):
        pass


@pytest_asyncio.fixture
async def artifact_http(tmp_path, monkeypatch):
    from app.device_control import broker as broker_module
    from app.gateway.routers import desktop_artifacts, devices, local_tasks
    from deerflow.config import paths
    from deerflow.persistence import engine as persistence

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'artifacts.db'}")
    async with engine.begin() as db:
        await db.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(persistence, "get_session_factory", lambda: factory)
    monkeypatch.setattr(devices, "get_session_factory", lambda: factory)
    monkeypatch.setattr(desktop_artifacts, "get_session_factory", lambda: factory, raising=False)
    monkeypatch.setattr(paths, "_paths", paths.Paths(tmp_path / "data"))
    archive = ReceiptArchive(factory)
    broker = DeviceBroker(receipt_archive=archive)
    monkeypatch.setattr(broker_module, "_broker", broker)
    owner = UserModel(id="owner-A", username="artifact-owner@example.invalid", role="user")
    async with factory() as session:
        session.add(owner)
        await session.commit()
    app = FastAPI()
    app.state.thread_store = MemoryThreadMetaStore(InMemoryStore())
    app.state.run_manager = RunManager()
    await app.state.thread_store.create("thread-A", user_id="owner-A")
    await app.state.thread_store.create("other-thread", user_id="owner-A")
    app.include_router(desktop_artifacts.router)
    app.include_router(devices.router)
    app.include_router(local_tasks.router)

    @app.middleware("http")
    async def authenticated(request, call_next):
        user = request.headers.get("x-fixture-user", "owner-A")
        permissions = [] if user == "no-permission" else ["threads:read", "threads:write"]
        request.state.auth = AuthContext(SimpleNamespace(id=user), permissions)
        return await call_next(request)

    async def current_user(request: Request):
        return owner

    app.dependency_overrides[get_current_rbac_user] = current_user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid") as client:
        key = Ed25519PrivateKey.generate()
        public = public_key_text(key.public_key())
        challenge = (await client.post("/api/devices/pairing")).json()
        registration = (
            await client.post("/api/devices/register", json={"pairing_code": challenge["code"], "name": "upload-device", "public_key": public, "protocol_version": "1", "runtime_version": "1.0", "capabilities": ["local.files.write"]})
        ).json()
        device_id = registration["device"]["id"]
        assert (await client.post(f"/api/devices/pairing/{challenge['pairing_id']}/confirm", json={"code": challenge["code"]})).status_code == 200
        paired = (await client.post("/api/devices/register/complete", json={"device_id": device_id, "public_key": public, "claim_token": registration["claim_token"]})).json()
        token = paired["session_token"]
        connection = DeviceConnection(device_id, paired["session_id"], token, key.public_key(), Socket(), capabilities=frozenset({"local.files.write"}), owner_id="owner-A", server_origin="http://fixture.invalid")
        await broker.attach(connection)
        record = await broker.send_task(
            device_id=device_id,
            operation="local.files.write",
            path="/workspace/12345678-1234-4234-8234-123456789abc/result-105.txt",
            run_id="run-105",
            tool_call_id="call-105",
            payload_extra={"thread_id": "thread-A", "arguments": {"path": "/workspace/12345678-1234-4234-8234-123456789abc/result-105.txt", "content": CONTENT.decode()}},
        )
        task = (await archive.get(record.task_id, owner_id="owner-A"))["task"]
        receipt = {
            "task_id": record.task_id,
            "run_id": "run-105",
            "capability": "local.files.write",
            "request_hash": task["request_hash"],
            "payload_hash": task["request_hash"],
            "status": "completed",
            "policy_decision": "allow",
            "consent_decision": "approved",
            "result_hash": DIGEST,
            "finished_at": datetime.now(UTC).isoformat(),
        }
        upload = {"receipt_id": str(uuid4()), "binding": broker.receipt_binding(connection), "task": task, "receipt": receipt}
        upload["receipt_hash"] = receipt_digest(upload)
        await broker.receive(connection, sign_envelope(private_key=key, message_type=MessageType.RECEIPT_UPLOAD, device_id=device_id, session_id=paired["session_id"], task_id=record.task_id, payload=upload))
        client.headers["X-Device-Session"] = token
        grant_body = {"device_id": device_id, "run_id": "run-105", "task_id": record.task_id, "name": "result-105.txt", "sha256": DIGEST, "bytes": len(CONTENT)}
        yield client, grant_body
    await engine.dispose()


@pytest.mark.asyncio
async def test_grant_is_issued_for_a_real_completed_task(artifact_http):
    client, body = artifact_http
    response = await client.post("/api/threads/thread-A/artifacts/grant", json=body)
    assert response.status_code == 200, response.text
    grant = response.json()
    assert grant["task_id"] == body["task_id"] and grant["thread_id"] == "thread-A"
    assert len(grant["token"]) >= 32


async def issued_payload(client, source):
    response = await client.post("/api/threads/thread-A/artifacts/grant", json=source)
    assert response.status_code == 200, response.text
    grant = {key: response.json()[key] for key in ("run_id", "task_id", "thread_id", "name", "token")}
    return payload(task_id=source["task_id"], run_id=source["run_id"], grant=grant)


@pytest.mark.asyncio
async def test_issued_grant_cannot_authorize_another_task(artifact_http):
    client, source = artifact_http
    body = await issued_payload(client, source)
    body["task_id"] = "fabricated-task"
    body["grant"]["task_id"] = "fabricated-task"
    response = await client.post("/api/threads/thread-A/artifacts", json=body, headers={"Idempotency-Key": HANDLE})
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "GRANT_INVALID"


@pytest.mark.asyncio
async def test_upload_is_discoverable_and_downloadable_by_another_owned_device(artifact_http):
    client, source = artifact_http
    body = await issued_payload(client, source)
    first = await client.post("/api/threads/thread-A/artifacts", json=body, headers={"Idempotency-Key": HANDLE})
    assert first.status_code == 201, first.text
    artifact_id = first.json()["artifact_id"]
    page = await client.get("/api/threads/thread-A/artifacts", headers={"X-Device-Session": ""})
    assert page.status_code == 200, page.text
    artifact = page.json()["artifacts"][0]
    assert artifact["artifact_id"] == artifact_id and artifact["sha256"] == DIGEST
    assert artifact["task_id"] == source["task_id"] and artifact["bytes"] == 18
    download = await client.get(f"/api/threads/thread-A/artifacts/{artifact_id}/download", headers={"X-Device-Session": ""})
    assert download.status_code == 200 and download.content == CONTENT
    assert download.headers["x-content-sha256"] == DIGEST
    assert (await client.get("/api/threads/thread-A/artifacts", headers={"x-fixture-user": "owner-B"})).status_code == 404
    assert (await client.get(f"/api/threads/thread-A/artifacts/{artifact_id}/download", headers={"x-fixture-user": "owner-B"})).status_code == 404
    retry = await client.post("/api/threads/thread-A/artifacts", json=body, headers={"Idempotency-Key": HANDLE})
    assert retry.status_code == 200 and retry.json()["duplicate"] is True
    fresh = await issued_payload(client, source)
    repeated = await client.post("/api/threads/thread-A/artifacts", json=fresh, headers={"Idempotency-Key": HANDLE})
    assert repeated.status_code == 200 and repeated.json()["artifact_id"] == artifact_id
    assert len((await client.get("/api/threads/thread-A/artifacts")).json()["artifacts"]) == 1
    meta = await client.get(f"/api/threads/thread-A/artifacts/{artifact_id}")
    assert meta.status_code == 200
    assert meta.json()["sha256"] == DIGEST and meta.json()["task_id"] == source["task_id"]


@pytest.mark.asyncio
async def test_grant_rejects_changed_content_and_wrong_thread(artifact_http):
    client, source = artifact_http
    mismatch = await client.post("/api/threads/thread-A/artifacts/grant", json={**source, "sha256": "0" * 64})
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "ARTIFACT_CONTENT_MISMATCH"
    wrong = await client.post("/api/threads/other-thread/artifacts/grant", json=source)
    assert wrong.status_code == 403
    assert wrong.json()["detail"]["code"] == "ARTIFACT_SOURCE_INVALID"


@pytest.mark.asyncio
async def test_revoked_device_cannot_consume_issued_grant(artifact_http):
    client, source = artifact_http
    body = await issued_payload(client, source)
    revoked = await client.post(f"/api/devices/{source['device_id']}/revoke")
    assert revoked.status_code == 200, revoked.text
    response = await client.post("/api/threads/thread-A/artifacts", json=body, headers={"Idempotency-Key": HANDLE})
    assert response.status_code in (401, 403), response.text
    assert not (await client.get("/api/threads/thread-A/artifacts")).json()["artifacts"]


@pytest.mark.asyncio
async def test_compatibility_cannot_grant_permission_or_bypass_upload_restriction(artifact_http, release):
    from app.device_control.broker import get_device_broker

    client, source = artifact_http
    _, publish = release
    body = await issued_payload(client, source)
    connection = get_device_broker().connections[source["device_id"]]
    connection.desktop_version = "0.1.0"
    connection.runtime_python = "3.12.10"
    publish()
    no_permission = await client.post("/api/threads/thread-A/artifacts/grant", json=source, headers={"x-fixture-user": "no-permission"})
    assert no_permission.status_code == 403
    publish("capability", ["local.artifacts.upload"])
    grant = await client.post("/api/threads/thread-A/artifacts/grant", json=source)
    assert grant.status_code == 409
    assert grant.json()["detail"]["code"] == "COMPAT_CAPABILITY_DISABLED"
    upload = await client.post("/api/threads/thread-A/artifacts", json=body, headers={"Idempotency-Key": HANDLE})
    assert upload.status_code == 409
    assert upload.json()["detail"]["code"] == "COMPAT_CAPABILITY_DISABLED"
    assert not (await client.get("/api/threads/thread-A/artifacts")).json()["artifacts"]


from tests.integration.api import test_device_compatibility_gate as compatibility_fixtures  # noqa: E402

release = compatibility_fixtures.release
