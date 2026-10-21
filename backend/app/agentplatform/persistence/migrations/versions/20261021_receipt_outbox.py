"""Persist original local-task dispatch and unique receipt confirmations.

Revision ID: 20261021_receipt_outbox
Revises: 20261018_desktop_login
"""

import sqlalchemy as sa
from alembic import op

revision = "20261021_receipt_outbox"
down_revision = "20261018_desktop_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("device_control_task_receipts"):
        return
    op.create_table(
        "device_control_task_receipts",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("binding", sa.JSON(), nullable=False),
        sa.Column("task", sa.JSON(), nullable=False),
        sa.Column("receipt_id", sa.String(36), nullable=True, unique=True),
        sa.Column("receipt_hash", sa.String(64), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("acknowledgment", sa.Text(), nullable=True),
    )
    op.create_index("ix_device_control_task_receipts_owner_id", "device_control_task_receipts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_device_control_task_receipts_owner_id", table_name="device_control_task_receipts")
    op.drop_table("device_control_task_receipts")
