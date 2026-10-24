"""Persist Thread-bound local task lifecycle separately from signed dispatch identity.

Revision ID: 20261024_task_history
Revises: 20261021_receipt_outbox
"""

import sqlalchemy as sa
from alembic import op

revision = "20261024_task_history"
down_revision = "20261021_receipt_outbox"
branch_labels = None
depends_on = None

_TABLE = "device_control_task_receipts"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    columns = [
        sa.Column("thread_id", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'result_not_verified'")),
        sa.Column("stop_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recovery_status", sa.String(32), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("observed_receipt", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]
    missing = [column for column in columns if column.name not in present]
    if missing:
        # SQLite cannot ADD a nonconstant CURRENT_TIMESTAMP default to a
        # populated table. Batch recreation preserves existing evidence.
        recreate = "always" if bind.dialect.name == "sqlite" else "auto"
        with op.batch_alter_table(_TABLE, recreate=recreate) as batch:
            for column in missing:
                batch.add_column(column)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    if "ix_device_task_thread_history" not in indexes:
        op.create_index("ix_device_task_thread_history", _TABLE, ["owner_id", "thread_id", "created_at", "task_id"])
    if not inspector.has_table("runs"):
        return
    receipts = sa.table(_TABLE, sa.column("task_id"), sa.column("owner_id"), sa.column("task", sa.JSON), sa.column("thread_id"))
    runs = sa.table("runs", sa.column("run_id"), sa.column("thread_id"), sa.column("user_id"))
    for row in bind.execute(sa.select(receipts.c.task_id, receipts.c.owner_id, receipts.c.task).where(receipts.c.thread_id == "")).mappings():
        task = row["task"]
        if not isinstance(task, dict):
            continue
        thread_id = bind.execute(sa.select(runs.c.thread_id).where(runs.c.run_id == task.get("run_id"), runs.c.user_id == row["owner_id"])).scalar_one_or_none()
        if thread_id:
            bind.execute(sa.update(receipts).where(receipts.c.task_id == row["task_id"]).values(thread_id=thread_id))


def downgrade() -> None:
    op.drop_index("ix_device_task_thread_history", table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        for name in ("updated_at", "created_at", "observed_receipt", "error_code", "recovery_status", "stop_requested", "status", "thread_id"):
            batch.drop_column(name)
