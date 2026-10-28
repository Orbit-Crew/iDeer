"""add canonical connector identities (#123)

Revision ID: 20261027_connectors
Revises: 20261027_skill_script_auth
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261027_connectors"
down_revision: str | None = "20261027_skill_script_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the owner-scoped canonical connector identity table (#123).

    Identity only: the runnable binding (command, environment, credentials)
    never reaches the Server, so the table has no column for it.
    """

    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names()) if bind is not None else set()
    if "connectors" in existing:
        return
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users_ext.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_connectors_owner_slug"),
    )
    op.create_index("ix_connectors_owner_id", "connectors", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_connectors_owner_id", table_name="connectors")
    op.drop_table("connectors")
