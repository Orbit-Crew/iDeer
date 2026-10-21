"""Receipt replay uses current signed sessions and never resumes terminal tasks."""

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.device_control.broker import DeviceBroker, DeviceConnection, TaskStatus
from app.device_control.protocol import MessageType, sign_envelope
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
