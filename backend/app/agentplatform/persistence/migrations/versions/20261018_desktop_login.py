"""Add initiator-bound Desktop login approvals.

Revision ID: 20261018_desktop_login
Revises: 20261001_rejoin_upstream_line
"""

import sqlalchemy as sa
from alembic import op

revision = "20261018_desktop_login"
down_revision = "20261001_rejoin_upstream_line"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("device_control_desktop_logins"):
        return
    op.create_table(
        "device_control_desktop_logins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("initiator_digest", sa.String(64), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("existing_device_id", sa.String(36), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users_ext.id", ondelete="CASCADE"), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_control_desktop_logins_expires_at", "device_control_desktop_logins", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_device_control_desktop_logins_expires_at", table_name="device_control_desktop_logins")
    op.drop_table("device_control_desktop_logins")
