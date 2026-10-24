"""Issue 104 signed task cancellation and durable Thread recovery."""

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.device_control.broker import DeviceBroker, DeviceConnection, TaskStatus
from app.device_control.protocol import MessageType, sign_envelope


class Socket:
    def __init__(self):
        self.frames = []

    async def send_text(self, text):
        self.frames.append(json.loads(text))

    async def close(self, **kwargs):
        pass


@pytest.mark.asyncio
async def test_cancel_requests_runtime_stop_without_claiming_terminal_fact():
    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker()
    connection = DeviceConnection("device-A", "session-A", "token", key.public_key(), Socket())
    await broker.attach(connection)
    task = await broker.send_echo_task(device_id="device-A", run_id="run-A", tool_call_id="call-A", value="BEFORE")
    await broker.cancel_task(task.task_id)
    assert task.status == TaskStatus.CANCEL_REQUESTED
    assert task.stop_requested is True
    assert [frame["type"] for frame in connection.websocket.frames].count("task_cancel") == 1
    await broker.cancel_task(task.task_id)
    assert [frame["type"] for frame in connection.websocket.frames].count("task_cancel") == 1
    await broker.receive(connection, sign_envelope(private_key=key, message_type=MessageType.TASK_RESULT, device_id="device-A", session_id="session-A", task_id=task.task_id, payload={"receipt": {"status": "completed"}, "result": "AFTER"}))
    assert task.status == TaskStatus.COMPLETED
    assert task.stop_requested is True
    assert task.result == "AFTER"


@pytest.mark.asyncio
async def test_thread_history_survives_broker_restart_and_late_signed_receipt(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.device_control.protocol import payload_digest
    from app.device_control.receipt_archive import ReceiptArchive, receipt_digest
    from app.device_control.receipt_models import DeviceTaskReceiptModel

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}")
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    key, server_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    broker = DeviceBroker(server_private_key=server_key, receipt_archive=archive)
    connection = DeviceConnection("device-A", "old-session", "token", key.public_key(), Socket(), capabilities=frozenset({"local.files.write"}), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(connection)
    task = await broker.send_task(
        device_id="device-A",
        operation="local.files.write",
        path="/workspace/12345678-1234-4234-8234-123456789abc/report.txt",
        run_id="run-A",
        tool_call_id="call-A",
        payload_extra={"thread_id": "thread-A", "arguments": {"path": "/workspace/12345678-1234-4234-8234-123456789abc/report.txt", "content": "AFTER"}},
    )
    await broker.receive(
        connection,
        sign_envelope(private_key=key, message_type=MessageType.CONSENT_REQUIRED, device_id="device-A", session_id="old-session", task_id=task.task_id, payload={"payload": task.payload, "request_hash": payload_digest(task.payload)}),
    )
    await broker.cancel_task(task.task_id)
    await broker.detach("device-A", "old-session")
    original = await archive.get(task.task_id, owner_id="account-A")
    restarted = DeviceBroker(server_private_key=server_key, receipt_archive=archive)
    page = await restarted.list_thread_tasks("thread-A", owner_id="account-A", limit=1, offset=0)
    assert page["tasks"][0]["status"] == "result_not_verified"
    assert page["tasks"][0]["stop_requested"] is True
    assert page["tasks"][0]["receipt_pending"] is True
    assert page["tasks"][0]["recovery_status"] == "cancel_requested"
    assert page["tasks"][0]["logical_target"] == "/workspace/12345678-1234-4234-8234-123456789abc/report.txt"
    assert await restarted.list_thread_tasks("thread-A", owner_id="account-B", limit=1, offset=0) == {"tasks": [], "has_more": False, "next_offset": None}
    assert "AFTER" not in json.dumps(page)
    assert "signature" not in json.dumps(page)
    current = DeviceConnection("device-A", "new-session", "new-token", key.public_key(), Socket(), owner_id="account-A", server_origin="https://fixture.invalid")
    await restarted.attach(current)
    receipt = {"task_id": task.task_id, "run_id": "run-A", "capability": "local.files.write", "request_hash": payload_digest(task.payload), "payload_hash": payload_digest(task.payload), "status": "completed", "consent_decision": "approved"}
    upload = {"receipt_id": "receipt-A", "binding": original["binding"], "task": original["task"], "receipt": receipt}
    upload["receipt_hash"] = receipt_digest(upload)
    for _ in range(2):
        await restarted.receive(current, sign_envelope(private_key=key, message_type=MessageType.RECEIPT_UPLOAD, device_id="device-A", session_id="new-session", task_id=task.task_id, payload=upload))
    page = await restarted.list_thread_tasks("thread-A", owner_id="account-A", limit=1, offset=0)
    recovered = page["tasks"][0]
    assert recovered["status"] == "completed"
    assert recovered["stop_requested"] is True
    assert recovered["receipt_pending"] is False
    assert recovered["receipt"] == receipt
    assert recovered["run_id"] == "run-A"
    assert not restarted.tasks
    assert not [frame for frame in current.websocket.frames if frame["type"] == "task"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_replay_rejection_does_not_invent_a_failure_for_the_original_write():
    from app.device_control.protocol import payload_digest

    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker()
    connection = DeviceConnection("device-A", "session-A", "token", key.public_key(), Socket(), capabilities=frozenset({"local.files.write"}))
    await broker.attach(connection)
    task = await broker.send_task(device_id="device-A", operation="local.files.write", path="/workspace/12345678-1234-4234-8234-123456789abc/report.txt", run_id="run-A", tool_call_id="call-A")
    marker = {"error_code": "TASK_REPLAYED", "message": "task id was already admitted"}
    await broker.receive(connection, sign_envelope(private_key=key, message_type=MessageType.ERROR, device_id="device-A", session_id="session-A", task_id=task.task_id, payload=marker))
    assert task.status == TaskStatus.RESULT_NOT_VERIFIED
    assert task.receipt is None
    receipt = {"task_id": task.task_id, "run_id": "run-A", "capability": "local.files.write", "request_hash": payload_digest(task.payload), "payload_hash": payload_digest(task.payload), "status": "completed", "consent_decision": "approved"}
    await broker.receive(connection, sign_envelope(private_key=key, message_type=MessageType.TASK_RESULT, device_id="device-A", session_id="session-A", task_id=task.task_id, payload={"receipt": receipt, "result": {"written": True}}))
    assert task.status == TaskStatus.COMPLETED
    await broker.receive(connection, sign_envelope(private_key=key, message_type=MessageType.ERROR, device_id="device-A", session_id="session-A", task_id=task.task_id, payload=marker))
    assert task.status == TaskStatus.COMPLETED
    assert task.receipt == receipt


@pytest.mark.asyncio
@pytest.mark.parametrize("pause_at", ["admission", "observation"])
@pytest.mark.parametrize("cancel_via", ["awaiter", "broker"])
async def test_cancellation_during_persistence_never_dispatches_and_survives_restart(tmp_path, pause_at, cancel_via):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.device_control.receipt_archive import ReceiptArchive
    from app.device_control.receipt_models import DeviceTaskReceiptModel

    entered, release = asyncio.Event(), asyncio.Event()

    class PausedArchive(ReceiptArchive):
        async def admit(self, binding, task, **kwargs):
            await super().admit(binding, task, **kwargs)
            if pause_at == "admission":
                entered.set()
                await release.wait()

        async def observe(self, task_id, **kwargs):
            await super().observe(task_id, **kwargs)
            if pause_at == "observation" and kwargs["status"] == "sent":
                entered.set()
                await release.wait()

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cancel-admission.db'}")
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = PausedArchive(async_sessionmaker(engine, expire_on_commit=False))
    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker(receipt_archive=archive)
    connection = DeviceConnection("device-A", "session-A", "token", key.public_key(), Socket(), capabilities=frozenset({"local.files.write"}), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(connection)
    pending = asyncio.create_task(
        broker.send_task(device_id="device-A", operation="local.files.write", path="/workspace/12345678-1234-4234-8234-123456789abc/report.txt", run_id="run-A", tool_call_id="call-A", payload_extra={"thread_id": "thread-A"})
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        if cancel_via == "awaiter":
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            await broker.cancel_task(next(iter(broker.tasks)))
            release.set()
            await pending
        assert not [frame for frame in connection.websocket.frames if frame["type"] == "task"]
        restarted = DeviceBroker(receipt_archive=archive)
        item = (await restarted.list_thread_tasks("thread-A", owner_id="account-A"))["tasks"][0]
        assert item["status"] == "cancelled"
        assert item["stop_requested"] is True
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()


@pytest.mark.asyncio
async def test_stop_signal_reaches_runtime_before_database_observation_waits(tmp_path):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.device_control.receipt_archive import ReceiptArchive
    from app.device_control.receipt_models import DeviceTaskReceiptModel

    entered, release = asyncio.Event(), asyncio.Event()

    class SlowObservation(ReceiptArchive):
        async def observe(self, task_id, **kwargs):
            if kwargs["status"] == "cancel_requested":
                entered.set()
                await release.wait()
            await super().observe(task_id, **kwargs)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'slow-observation.db'}")
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = SlowObservation(async_sessionmaker(engine, expire_on_commit=False))
    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker(receipt_archive=archive)
    connection = DeviceConnection("device-A", "session-A", "token", key.public_key(), Socket(), owner_id="account-A", server_origin="https://fixture.invalid")
    await broker.attach(connection)
    task = await broker.send_echo_task(device_id="device-A", run_id="run-A", tool_call_id="call-A", value="BEFORE")
    stopping = asyncio.create_task(broker.cancel_task(task.task_id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert [frame["type"] for frame in connection.websocket.frames].count("task_cancel") == 1
    finally:
        release.set()
        await stopping
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("unrecognized_status", ["pending_sync", ["completed"]])
async def test_unknown_receipt_status_never_becomes_tool_success(unrecognized_status):
    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker()
    connection = DeviceConnection("device-A", "session-A", "token", key.public_key(), Socket())
    await broker.attach(connection)
    task = await broker.send_echo_task(device_id="device-A", run_id="run-A", tool_call_id="call-A", value="BEFORE")
    await broker.receive(
        connection, sign_envelope(private_key=key, message_type=MessageType.TASK_RESULT, device_id="device-A", session_id="session-A", task_id=task.task_id, payload={"result": "AFTER", "receipt": {"status": unrecognized_status}})
    )
    assert task.status == TaskStatus.RESULT_NOT_VERIFIED
    assert task.error_code == "RESULT_UNCERTAIN"


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["detach", "invalidate"])
async def test_connection_cleanup_does_not_hold_attachment_or_iterate_live_tasks_during_storage(transition):
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingArchive:
        async def admit(self, binding, task, **kwargs):
            pass

        async def observe(self, task_id, **kwargs):
            if kwargs["status"] == "device_offline":
                entered.set()
                await release.wait()

    class TrackingSocket(Socket):
        closed = False

        async def close(self, **kwargs):
            self.closed = True

    key = Ed25519PrivateKey.generate()
    broker = DeviceBroker(receipt_archive=BlockingArchive())
    socket = TrackingSocket()
    first = DeviceConnection("device-A", "session-A", "token", key.public_key(), socket, owner_id="account-A")
    second = DeviceConnection("device-B", "session-B", "token", key.public_key(), Socket(), owner_id="account-B")
    await broker.attach(first)
    await broker.attach(second)
    await broker.send_echo_task(device_id="device-A", run_id="run-A", tool_call_id="call-A", value="BEFORE")
    pending = asyncio.create_task(broker.detach("device-A", "session-A") if transition == "detach" else broker.invalidate("device-A", reason="revoked"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        await broker.send_echo_task(device_id="device-B", run_id="run-B", tool_call_id="call-B", value="AFTER")
        third = DeviceConnection("device-C", "session-C", "token", key.public_key(), Socket())
        await asyncio.wait_for(broker.attach(third), timeout=2)
        if transition == "invalidate":
            assert socket.closed is True
        release.set()
        await pending
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
