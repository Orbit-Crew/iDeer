"""Receipt replay uses current signed sessions and never resumes terminal tasks."""

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.device_control.broker import DeviceBroker, DeviceConnection, TaskStatus
from app.device_control.protocol import MessageType, ProtocolError, payload_digest, sign_envelope
from app.device_control.receipt_archive import ReceiptArchive, receipt_digest
from app.device_control.receipt_models import DeviceTaskReceiptModel


class Socket:
    def __init__(self):
        self.frames = []

    async def send_text(self, text):
        self.frames.append(json.loads(text))

    async def close(self, **kwargs):
        pass


@pytest.mark.asyncio
async def test_terminal_task_receipt_replayed_after_broker_restart(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'receipt.db'}")
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    device_key, broker_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    broker = DeviceBroker(server_private_key=broker_key, receipt_archive=archive)
    connection = DeviceConnection("device-A", "old-session", "synthetic", device_key.public_key(), Socket(), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(connection)
    task = await broker.send_echo_task(device_id="device-A", run_id="terminal-run", tool_call_id="call-A", value="must-not-reexecute")
    task.status = TaskStatus.CANCELLED
    (sent,) = [frame for frame in connection.websocket.frames if frame["type"] == "task"]
    original = await archive.get(task.task_id, owner_id="account-A")
    upload = {
        "receipt_id": "receipt-101",
        "binding": original["binding"],
        "task": original["task"],
        "receipt": {"task_id": task.task_id, "run_id": "terminal-run", "capability": "echo", "request_hash": sent["payload_hash"], "payload_hash": sent["payload_hash"], "status": "completed", "policy_decision": "allow"},
    }
    upload["receipt_hash"] = receipt_digest(upload)
    broker = DeviceBroker(server_private_key=broker_key, receipt_archive=archive)
    current = DeviceConnection("device-A", "new-session", "new-synthetic", device_key.public_key(), Socket(), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(current)
    for _ in range(2):
        await broker.receive(current, sign_envelope(private_key=device_key, message_type=MessageType.RECEIPT_UPLOAD, device_id="device-A", session_id="new-session", task_id=task.task_id, payload=upload))
    acknowledgments = [frame for frame in current.websocket.frames if frame["type"] == "receipt_ack"]
    assert len(acknowledgments) == 2
    assert acknowledgments[0]["payload"] == acknowledgments[1]["payload"]
    assert not broker.tasks
    assert task.status == TaskStatus.CANCELLED
    assert not [frame for frame in current.websocket.frames if frame["type"] in {"task", "task_result"}]
    assert (await archive.get(task.task_id, owner_id="account-A"))["evidence"]["tool_call_id"] == "call-A"
    await engine.dispose()


@pytest.mark.asyncio
async def test_directory_write_receipt_keeps_original_run_after_reconnect(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'directory-receipt.db'}")
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    device_key, broker_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    broker = DeviceBroker(server_private_key=broker_key, receipt_archive=archive)
    connection = DeviceConnection("device-A", "original-session", "synthetic", device_key.public_key(), Socket(), capabilities=frozenset({"local.files.write"}), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(connection)
    task = await broker.send_task(device_id="device-A", operation="local.files.write", path="/workspace/12345678-1234-4234-8234-123456789abc/report.txt", run_id="original-write-run", tool_call_id="original-write-call")
    receipt = {
        "task_id": task.task_id,
        "run_id": "original-write-run",
        "capability": "local.files.write",
        "request_hash": payload_digest(task.payload),
        "payload_hash": payload_digest(task.payload),
        "status": "completed",
        "policy_decision": "allow",
        "consent_decision": "directory:12345678-1234-4234-8234-123456789abc",
    }
    await broker.receive(
        connection,
        sign_envelope(private_key=device_key, message_type=MessageType.TASK_RESULT, device_id=connection.device_id, session_id=connection.session_id, task_id=task.task_id, payload={"result": {"written": True}, "receipt": receipt}),
    )
    assert task.status is TaskStatus.COMPLETED
    assert task.receipt == receipt
    await broker.detach(connection.device_id, connection.session_id)
    original = await archive.get(task.task_id, owner_id="account-A")
    upload = {"receipt_id": "directory-write-receipt", "binding": original["binding"], "task": original["task"], "receipt": receipt}
    upload["receipt_hash"] = receipt_digest(upload)
    restarted = DeviceBroker(server_private_key=broker_key, receipt_archive=archive)
    current = DeviceConnection("device-A", "new-session", "rotated-synthetic", device_key.public_key(), Socket(), owner_id="account-A", server_origin="https://fixture.invalid")
    await restarted.attach(current)
    for _ in range(2):
        await restarted.receive(current, sign_envelope(private_key=device_key, message_type=MessageType.RECEIPT_UPLOAD, device_id=current.device_id, session_id=current.session_id, task_id=task.task_id, payload=upload))
    stored = await archive.get(task.task_id, owner_id="account-A")
    assert stored["receipt"] == receipt
    assert stored["evidence"]["tool_call_id"] == "original-write-call"
    assert stored["evidence"]["local_execution_receipt"]["run_id"] == "original-write-run"
    assert stored["evidence"]["local_execution_receipt"]["consent_decision"] == "directory:12345678-1234-4234-8234-123456789abc"
    assert await archive.get(task.task_id, owner_id="account-B") is None
    acknowledgments = [frame for frame in current.websocket.frames if frame["type"] == "receipt_ack"]
    assert len(acknowledgments) == 2
    assert acknowledgments[0]["payload"] == acknowledgments[1]["payload"]
    assert not restarted.tasks
    assert not [frame for frame in current.websocket.frames if frame["type"] in {"task", "task_result"}]
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", [MessageType.TASK_RESULT, MessageType.RECEIPT_UPLOAD])
@pytest.mark.parametrize(
    "basis",
    [
        None,
        True,
        {},
        [],
        "always_allow",
        "directory:",
        "directory:not-a-uuid",
        "directory:12345678123442348234123456789abc",
        "directory:{12345678-1234-4234-8234-123456789abc}",
        "directory:12345678-1234-4234-8234-123456789ABC",
        "directory:12345678-1234-4234-8234-123456789abc\n",
        "directory:12345678-1234-4234-8234-123456789abc/extra",
    ],
)
async def test_completed_write_requires_valid_local_basis_on_live_and_replay(tmp_path: Path, message_type: MessageType, basis: Any) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'invalid-basis.db'}")
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker(receipt_archive=archive)
    connection = DeviceConnection("device-basis", "session-basis", "synthetic", key.public_key(), Socket(), capabilities=frozenset({"local.files.write"}), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(connection)
    task = await broker.send_task(device_id=connection.device_id, operation="local.files.write", path="/workspace/12345678-1234-4234-8234-123456789abc/report.txt", run_id="basis-run", tool_call_id="basis-call")
    receipt = {"task_id": task.task_id, "run_id": "basis-run", "capability": "local.files.write", "request_hash": payload_digest(task.payload), "payload_hash": payload_digest(task.payload), "status": "completed", "consent_decision": basis}
    if message_type == MessageType.RECEIPT_UPLOAD:
        original = await archive.get(task.task_id, owner_id="account-A")
        payload = {"receipt_id": "invalid-basis", "binding": original["binding"], "task": original["task"], "receipt": receipt}
        payload["receipt_hash"] = receipt_digest(payload)
    else:
        payload = {"result": {"written": True}, "receipt": receipt}
    with pytest.raises(ProtocolError) as rejected:
        await broker.receive(connection, sign_envelope(private_key=key, message_type=message_type, device_id=connection.device_id, session_id=connection.session_id, task_id=task.task_id, payload=payload))
    assert rejected.value.code == "RECEIPT_TASK_MISMATCH"
    assert task.status is TaskStatus.SENT
    assert task.receipt is None
    assert (await archive.get(task.task_id, owner_id="account-A"))["receipt"] is None
    assert not [frame for frame in connection.websocket.frames if frame["type"] == "receipt_ack"]
    await engine.dispose()
