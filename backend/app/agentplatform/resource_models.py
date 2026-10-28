"""AgentPlatform resource-governance persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ResourceType(StrEnum):
    SKILL = "skill"
    AGENT = "agent"
    WORKFLOW = "workflow"
    KNOWLEDGE_BASE = "knowledge_base"


class ResourceLifecycleStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class ResourceStorageKind(StrEnum):
    FILESYSTEM = "filesystem"
    DATABASE = "database"


class ResourceProvenance(StrEnum):
    USER = "user"
    BUNDLED = "bundled"


class ResourceMetadata(Base):
    """Governance metadata for a canonical Skill/Workflow/Agent/Tool resource."""

    __tablename__ = "resource_metadata"

    id = Column(String(64), primary_key=True)
    resource_type = Column(String(32), nullable=False)
    resource_id = Column(String(255), nullable=False)
    owner_id = Column(String(64), ForeignKey("users_ext.id"), nullable=False)
    department_id = Column(String(64), ForeignKey("departments.id"), nullable=True)
    visibility = Column(String(32), nullable=False, default="private", server_default="private")
    imported_from = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    is_favorited = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, nullable=False, default=_now, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "owner_id", name="uq_resource_type_id_owner"),
        CheckConstraint("resource_type IN ('tool', 'skill', 'workflow', 'agent')", name="ck_resource_type"),
        CheckConstraint("visibility IN ('private', 'department', 'public')", name="ck_visibility"),
        CheckConstraint("version >= 1", name="ck_version_positive"),
        Index("ix_resource_metadata_owner", "owner_id"),
        Index("ix_resource_metadata_dept", "department_id"),
    )


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="RESTRICT"), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private", server_default="private")
    scope_department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False, default=ResourceLifecycleStatus.ACTIVE, server_default="active")
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    storage_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provenance: Mapped[str] = mapped_column(String(16), nullable=False, default=ResourceProvenance.USER, server_default="user")
    system_owned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    authz_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("type", "owner_id", "slug", name="uq_resources_type_owner_slug"),
        CheckConstraint("type IN ('skill', 'agent', 'workflow', 'knowledge_base')", name="ck_resources_type"),
        CheckConstraint("visibility IN ('private', 'department', 'public')", name="ck_resources_visibility"),
        CheckConstraint("lifecycle_status IN ('active', 'archived', 'suspended')", name="ck_resources_lifecycle"),
        CheckConstraint("storage_kind IN ('filesystem', 'database')", name="ck_resources_storage_kind"),
        CheckConstraint("provenance IN ('user', 'bundled')", name="ck_resources_provenance"),
        CheckConstraint("latest_version >= 0", name="ck_resources_latest_version"),
        CheckConstraint("draft_revision >= 0", name="ck_resources_draft_revision"),
        CheckConstraint("authz_revision >= 1", name="ck_resources_authz_revision"),
        Index("ix_resources_owner", "owner_id"),
        Index("ix_resources_visibility_scope", "visibility", "scope_department_id"),
        Index("ix_resources_type_lifecycle", "type", "lifecycle_status"),
    )


class ResourceVersion(Base):
    __tablename__ = "resource_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scan_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="RESTRICT"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    source_resource_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("resource_id", "version", name="uq_resource_versions_resource_version"),
        CheckConstraint("version >= 1", name="ck_resource_versions_version"),
        CheckConstraint("source_version IS NULL OR source_version >= 1", name="ck_resource_versions_source_version"),
        Index("ix_resource_versions_hash", "content_hash"),
    )


class ResourceDependency(Base):
    __tablename__ = "resource_dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    target_resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    dependency_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_resource_id", "target_resource_id", name="uq_resource_dependencies_edge"),
        CheckConstraint("source_resource_id <> target_resource_id", name="ck_resource_dependencies_not_self"),
        Index("ix_resource_dependencies_target", "target_resource_id"),
    )


class RunResourceSnapshot(Base):
    __tablename__ = "run_resource_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    root_resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authz_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_role: Mapped[str] = mapped_column(String(16), nullable=False, default="resolved", server_default="resolved")
    knowledge_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    knowledge_revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_dataset_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retrieval_profile_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_profile_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieval_profile_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding_profile_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("run_id", "resource_id", name="uq_run_resource_snapshots_run_resource"),
        CheckConstraint("version >= 1", name="ck_run_resource_snapshots_version"),
        CheckConstraint("authz_revision >= 1", name="ck_run_resource_snapshots_authz_revision"),
        CheckConstraint("selection_role IN ('root', 'resolved', 'preferred')", name="ck_run_resource_snapshots_selection_role"),
        Index("ix_run_resource_snapshots_resource", "resource_id", "run_id"),
    )


class ResourceFavorite(Base):
    __tablename__ = "resource_favorites"

    user_id: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="CASCADE"), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())


class ResourceNotification(Base):
    __tablename__ = "resource_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (Index("ix_resource_notifications_recipient_created", "recipient_id", "created_at"),)


class ResourceDraft(Base):
    __tablename__ = "resource_drafts"

    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    modified_by: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now())

    __table_args__ = (CheckConstraint("revision >= 1", name="ck_resource_drafts_revision"),)


class SkillTriggerPreferenceRow(Base):
    """Per-user Skill trigger preference (#121).

    One row per (user, skill) describing how the Server may auto-select that
    Skill for the user's Runs: enabled, keywords, always-inject, the applicable
    Agent allowlist, and the priority tiebreaker. A preference is inert user
    metadata — it never grants edit rights on the Skill's content and never
    bypasses the Run closure's visibility/published validation; matching rides
    the existing single preferred-Skill run-snapshot seam.
    """

    __tablename__ = "skill_trigger_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="CASCADE"), primary_key=True)
    skill_resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    always_inject: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applicable_agent_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now())

    __table_args__ = (CheckConstraint("priority BETWEEN -1000 AND 1000", name="ck_skill_trigger_preferences_priority"),)


class SkillScriptAuthorizationRow(Base):
    """One content-bound Skill script authorization (#122).

    Custom Skill scripts are off by default; this row is the remembered
    approval. Its identity hashes the owning account, the execution target
    and device binding, the Skill, the script path, the exact script SHA-256,
    and the declared-environment fingerprint — so changed content or a
    changed scope is a different row (re-authorization), while a prose-only
    version bump with unchanged bytes and declaration stays covered. The row
    never grants edit rights on the Skill and never bypasses Run-closure
    visibility; directory grants, sharing, and built-in identity do not
    create or replace it.
    """

    __tablename__ = "skill_script_authorizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users_ext.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    execution_target: Mapped[str] = mapped_column(String(16), nullable=False, default="server")
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    skill_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skill_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    script_path: Mapped[str] = mapped_column(String(512), nullable=False)
    script_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requirements_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("execution_target IN ('server', 'user_device')", name="ck_skill_script_authorizations_target"),
        UniqueConstraint("user_id", "execution_target", "device_id", "skill_resource_id", "script_path", name="uq_skill_script_authorizations_binding"),
    )
