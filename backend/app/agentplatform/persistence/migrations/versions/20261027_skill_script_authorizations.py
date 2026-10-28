"""add skill script authorizations (#122)

Revision ID: 20261027_skill_script_auth
Revises: 20261027_skill_trigger_pref
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261027_skill_script_auth"
down_revision: str | None = "20261027_skill_trigger_pref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the content-bound skill_script_authorizations table (#122)."""

    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names()) if bind is not None else set()
    if "skill_script_authorizations" in existing:
        return
    op.create_table(
        "skill_script_authorizations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("skill_resource_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("execution_target", sa.String(length=16), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("skill_version", sa.Integer(), nullable=False),
        sa.Column("skill_content_hash", sa.String(length=64), nullable=False),
        sa.Column("script_path", sa.String(length=512), nullable=False),
        sa.Column("script_sha256", sa.String(length=64), nullable=False),
        sa.Column("requirements_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["skill_resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users_ext.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "execution_target IN ('server', 'user_device')",
            name="ck_skill_script_authorizations_target",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "execution_target",
            "device_id",
            "skill_resource_id",
            "script_path",
            name="uq_skill_script_authorizations_binding",
        ),
    )
    op.create_index(
        "ix_skill_script_authorizations_user_id",
        "skill_script_authorizations",
        ["user_id"],
    )
    op.create_index(
        "ix_skill_script_authorizations_skill_resource_id",
        "skill_script_authorizations",
        ["skill_resource_id"],
    )


def downgrade() -> None:
    op.drop_table("skill_script_authorizations")
