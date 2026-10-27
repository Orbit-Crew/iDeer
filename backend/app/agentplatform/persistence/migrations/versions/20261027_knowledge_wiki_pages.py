"""add controlled knowledge wiki pages (#118)

Revision: 20261027_knowledge_wiki_pages
Revises: 20261027_knowledge_graph_artifacts

One wiki page row per (frozen revision, document): the server-orchestrated
page with its document-source binding, or the fixed category of the
per-page skip or failure. Rows are keyed by revision so two revisions'
wikis stay isolated, and the frozen manifest hash travels with every row so
a read can always name the version it came from.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_knowledge_wiki_pages"
down_revision: str | Sequence[str] | None = "20261027_knowledge_graph_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("knowledge_wiki_pages"):
        op.create_table(
            "knowledge_wiki_pages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("knowledge_base_id", sa.String(36), nullable=False),
            sa.Column("revision_id", sa.String(36), nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("manifest_hash", sa.String(64), nullable=False),
            sa.Column("document_id", sa.String(36), nullable=False),
            sa.Column("document_filename", sa.String(255), nullable=False, server_default=""),
            sa.Column("document_content_hash", sa.String(64), nullable=False),
            sa.Column("title", sa.String(255), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("error_message", sa.String(255), nullable=True),
            sa.Column("generated_by", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.resource_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["revision_id"], ["knowledge_base_revisions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["generated_by"], ["users_ext.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("revision_id", "document_id", name="uq_knowledge_wiki_revision_document"),
            sa.CheckConstraint("status in ('completed','skipped','failed')", name="ck_knowledge_wiki_pages_status"),
        )
        op.create_index("ix_knowledge_wiki_revision", "knowledge_wiki_pages", ["revision_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_wiki_revision", table_name="knowledge_wiki_pages")
    op.drop_table("knowledge_wiki_pages")
