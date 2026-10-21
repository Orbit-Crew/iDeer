"""Issue101 receipt acknowledgment survives broker/DB process restarts."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.device_control.protocol import ProtocolError
from app.device_control.receipt_archive import ReceiptArchive, receipt_digest

BINDING = {"server_origin": "https://fixture.invalid", "user_id": "account-A", "device_id": "device-A", "device_public_key": "public-device", "broker_public_key": "public-broker"}
TASK = {"task_id": "task-101", "run_id": "run-101", "tool_call_id": "call-101", "capability": "local.files.read", "request_hash": "a" * 64, "original_session_id": "session-original", "task_signature": "signature-original"}
RECEIPT = {"task_id": "task-101", "run_id": "run-101", "capability": "local.files.read", "request_hash": "a" * 64, "payload_hash": "a" * 64, "status": "completed", "policy_decision": "allow", "policy_version": "1", "result_hash": "b" * 64}


@pytest.mark.asyncio
async def test_idempotent_receipt_after_restart_is_unique_and_owner_bound(tmp_path):
    from app.device_control.receipt_models import DeviceTaskReceiptModel

    url = f"sqlite+aiosqlite:///{tmp_path / 'receipts.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as db:
        await db.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    await archive.admit(BINDING, TASK)
    item = {"receipt_id": "receipt-101", "binding": BINDING, "task": TASK, "receipt": RECEIPT}
    item["receipt_hash"] = receipt_digest(item)
    first = await archive.accept(BINDING, item)
    await engine.dispose()
    engine = create_async_engine(url)
    restarted = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    assert await restarted.accept(BINDING, item) == first
    stored = await restarted.get("task-101", owner_id="account-A")
    assert stored["acknowledgment"] == first["acknowledgment"]
    assert stored["evidence"]["tool_call_id"] == "call-101"
    assert stored["evidence"]["local_execution_receipt"]["status"] == "completed"
    with pytest.raises(ProtocolError, match="ownership"):
        await restarted.accept({**BINDING, "user_id": "account-B"}, item)
    assert await restarted.get("task-101", owner_id="account-B") is None
    conflicting = {**item, "receipt": {**RECEIPT, "status": "failed"}}
    conflicting["receipt_hash"] = receipt_digest({key: value for key, value in conflicting.items() if key != "receipt_hash"})
    with pytest.raises(ProtocolError, match="conflict"):
        await restarted.accept(BINDING, conflicting)
    assert (await restarted.get("task-101", owner_id="account-A"))["receipt"]["status"] == "completed"
    await engine.dispose()
