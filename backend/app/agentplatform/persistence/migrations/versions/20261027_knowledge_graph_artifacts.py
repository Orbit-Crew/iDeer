"""add controlled knowledge graph artifacts (#116)

Revision: 20261027_knowledge_graph_artifacts
Revises: 20261024_task_history

One controlled-graph artifact row per (frozen revision, document): the
server-orchestrated extraction result with its document-source binding, or
the fixed category of the per-document failure. Rows are keyed by revision
so two revisions' graphs stay isolated.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_knowledge_graph_artifacts"
down_revision: str | Sequence[str] | None = "20261024_task_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("knowledge_graph_artifacts"):
        op.create_table(
            "knowledge_graph_artifacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("knowledge_base_id", sa.String(36), nullable=False),
            sa.Column("revision_id", sa.String(36), nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("manifest_hash", sa.String(64), nullable=False),
            sa.Column("document_id", sa.String(36), nullable=False),
            sa.Column("document_filename", sa.String(255), nullable=False, server_default=""),
            sa.Column("document_content_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
            sa.Column("entities_json", sa.JSON(), nullable=False),
            sa.Column("relations_json", sa.JSON(), nullable=False),
            sa.Column("entity_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("relation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("error_message", sa.String(255), nullable=True),
            sa.Column("generated_by", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.resource_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["revision_id"], ["knowledge_base_revisions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["generated_by"], ["users_ext.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("revision_id", "document_id", name="uq_knowledge_graph_revision_document"),
            sa.CheckConstraint("status in ('completed','failed')", name="ck_knowledge_graph_artifacts_status"),
        )
        op.create_index("ix_knowledge_graph_revision", "knowledge_graph_artifacts", ["revision_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_graph_revision", table_name="knowledge_graph_artifacts")
    op.drop_table("knowledge_graph_artifacts")
