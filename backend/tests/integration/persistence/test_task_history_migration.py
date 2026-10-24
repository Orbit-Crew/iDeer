"""Issue 104 upgrades existing receipt evidence without changing signed identity."""

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.device_control.receipt_archive import ReceiptArchive
from deerflow.persistence.bootstrap import _get_alembic_config
from deerflow.persistence.run.model import RunRow


@pytest.mark.asyncio
async def test_task_history_migration_backfills_only_owner_matched_original_runs(tmp_path):
    database = tmp_path / "history-upgrade.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    cfg = _get_alembic_config(engine)
    await asyncio.to_thread(command.upgrade, cfg, "20261021_receipt_outbox")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(RunRow(run_id="original-run", thread_id="original-thread", user_id="owner-A", status="interrupted"))
        await session.commit()
    old_receipts = sa.table(
        "device_control_task_receipts",
        sa.column("task_id"),
        sa.column("owner_id"),
        sa.column("binding", sa.JSON),
        sa.column("task", sa.JSON),
        sa.column("receipt", sa.JSON),
        sa.column("receipt_hash"),
        sa.column("receipt_id"),
        sa.column("acknowledgment"),
    )
    signed_task = {"task_id": "task-A", "run_id": "original-run", "tool_call_id": "call-A", "capability": "local.files.write", "request_hash": "a" * 64, "task_signature": "unchanged"}
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(old_receipts),
            [
                {
                    "task_id": "task-A",
                    "owner_id": "owner-A",
                    "binding": {"device_id": "device-A"},
                    "task": signed_task,
                    "receipt": {"status": "completed", "task_id": "task-A"},
                    "receipt_hash": "b" * 64,
                    "receipt_id": "receipt-A",
                    "acknowledgment": "ack-A",
                },
                {"task_id": "task-B", "owner_id": "owner-B", "binding": {"device_id": "device-B"}, "task": {**signed_task, "task_id": "task-B"}, "receipt": None, "receipt_hash": None, "receipt_id": None, "acknowledgment": None},
            ],
        )
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with engine.connect() as connection:
        columns = await connection.run_sync(lambda db: {column["name"] for column in sa.inspect(db).get_columns("device_control_task_receipts")})
    assert {"thread_id", "status", "stop_requested", "recovery_status", "observed_receipt", "created_at", "updated_at"} <= columns
    archive = ReceiptArchive(factory)
    original = await archive.get("task-A", owner_id="owner-A")
    assert original["task"] == signed_task
    assert original["acknowledgment"] == "ack-A"
    tasks = await archive.list_by_thread("original-thread", owner_id="owner-A", limit=50, offset=0)
    assert tasks["tasks"][0]["status"] == "completed"
    assert tasks["tasks"][0]["receipt_pending"] is False
    assert (await archive.list_by_thread("original-thread", owner_id="owner-B", limit=50, offset=0))["tasks"] == []
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await engine.dispose()
