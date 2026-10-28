"""add skill trigger preferences (#121)

Revision ID: 20261027_skill_trigger_pref
Revises: 20261027_knowledge_wiki_pages
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261027_skill_trigger_pref"
down_revision: str | None = "20261027_knowledge_wiki_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the per-user skill_trigger_preferences table (#121)."""

    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names()) if bind is not None else set()
    if "skill_trigger_preferences" in existing:
        return
    op.create_table(
        "skill_trigger_preferences",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("skill_resource_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("always_inject", sa.Boolean(), nullable=False),
        sa.Column("applicable_agent_ids", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["skill_resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users_ext.id"], ondelete="CASCADE"),
        sa.CheckConstraint("priority BETWEEN -1000 AND 1000", name="ck_skill_trigger_preferences_priority"),
        sa.PrimaryKeyConstraint("user_id", "skill_resource_id"),
    )


def downgrade() -> None:
    op.drop_table("skill_trigger_preferences")
