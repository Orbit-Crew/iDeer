"""Receipt schema upgrades an existing Desktop login deployment."""

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _get_head_revision


@pytest.mark.asyncio
async def test_receipt_migration_upgrades_desktop_login_and_preserves_confirmed_evidence(tmp_path):
    db = tmp_path / "receipts.db"
    engine = sa.create_engine(f"sqlite:///{db}")
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    cfg = _get_alembic_config(async_engine)
    await asyncio.to_thread(command.upgrade, cfg, "20261018_desktop_login")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert _get_head_revision() == "20261027_connectors"
    with engine.begin() as connection:
        assert sa.inspect(connection).has_table("device_control_task_receipts")
        connection.execute(
            sa.text("INSERT INTO device_control_task_receipts (task_id,owner_id,binding,task,receipt_id,receipt_hash,receipt,evidence,acknowledgment) VALUES ('task-101','owner-A','{}','{}','receipt-101','fixed-hash','{}','{}','ack-101')")
        )
    await asyncio.to_thread(command.upgrade, cfg, "head")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT acknowledgment FROM device_control_task_receipts WHERE task_id='task-101'")).scalar_one() == "ack-101"
    engine.dispose()
    await async_engine.dispose()
