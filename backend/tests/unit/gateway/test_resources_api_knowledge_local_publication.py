"""Explicit server-side publication of local knowledge (#115).

The Desktop publishes one frozen local-import revision to an independent
server copy: the destination is previewed before anything uploads, an
unconfirmed call never creates anything, the copy carries a managed origin
provenance while the device KB stays private, failures are visible states
instead of silent replacements, and team access only opens through the
existing visibility application flow. Tests inject a facade bound to their
own engine (the #112 pattern) and drive the real publish build executor.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit tables
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.models import KnowledgeBase, KnowledgeDocument, KnowledgeRevision
from app.agentplatform.knowledge.provider import KnowledgeProviderError, ProviderIngestionResult
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resource_models import Resource
from app.agentplatform.resources.actors import actor_from_user
from app.agentplatform.resources.service import ResourceConflict, ResourceService
from app.gateway.canonical_agent_run_preparation import build_frozen_knowledge_bindings
from app.gateway.routers import resources
from deerflow.persistence.base import Base

DEVICE_ID = "device-115"
MARKER = b"# team marker T115-02\npublished bytes\n"


class FakeUpload:
    """Minimal multipart upload stand-in for the platform document upload."""

    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain") -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self, size: int = -1) -> bytes:
        data, self._content = self._content, b""
        return data

    async def close(self) -> None:
        return None


class FakePublishProvider:
    """Controllable provider: creates datasets and ingests frozen bytes."""

    def __init__(self, *, fail_ingest_on_call: int | None = None) -> None:
        self.fail_ingest_on_call = fail_ingest_on_call
        self.ingest_calls: list[dict] = []
        self.dataset_documents: dict[str, list[dict]] = {}

    async def create_dataset(self, *, name: str, embedding_model: str | None = None) -> str:
        dataset_id = f"copy-dataset-{len(self.dataset_documents) + 1}"
        self.dataset_documents[dataset_id] = []
        return dataset_id

    async def ingest(
        self,
        *,
        dataset_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
        provider_document_id: str | None = None,
        rebuild: bool = False,
    ) -> ProviderIngestionResult:
        self.ingest_calls.append({"dataset_id": dataset_id, "filename": filename})
        if self.fail_ingest_on_call is not None and len(self.ingest_calls) >= self.fail_ingest_on_call:
            raise KnowledgeProviderError("parse_failed", "internal parse detail")
        document_id = provider_document_id or f"copy-doc-{len(self.ingest_calls)}"
        self.dataset_documents.setdefault(dataset_id, []).append({"id": document_id, "name": filename, "content_hash": hashlib.sha256(content).hexdigest()})
        return ProviderIngestionResult(document_id, "processing")

    async def get_status(self, *, dataset_id: str, provider_document_id: str) -> str:
        return "ready"

    async def delete_document(self, *, dataset_id: str, provider_document_id: str) -> None:
        return None

    async def list_dataset_documents(self, *, dataset_id: str) -> list[dict]:
        return list(self.dataset_documents.get(dataset_id, []))


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple]:
    monkeypatch.setattr("app.agentplatform.knowledge.revisions.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    monkeypatch.setattr("app.agentplatform.knowledge.documents.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'local-publication-api.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner = UserModel(id="owner", username="owner@test.com", role=UserRole.USER, department_id="dept-a", disabled=False)
    teammate = UserModel(id="teammate", username="teammate@test.com", role=UserRole.USER, department_id="dept-a", disabled=False)
    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)
    admin = UserModel(id="admin", username="admin@test.com", role=UserRole.SUPER_ADMIN, department_id=None, disabled=False)
    async with factory() as session:
        session.add_all([owner, teammate, intruder, admin])
        await session.commit()
    audit_calls: list[tuple] = []

    async def audit(actor_id, action, resource_type=None, resource_id=None, detail=None, ip_address=None) -> None:
        audit_calls.append((actor_id, action, resource_type, resource_id, detail))

    knowledge = KnowledgeFacade(factory, audit=audit, provider_factory=lambda: object())
    yield factory, knowledge, owner, teammate, intruder, admin, audit_calls, tmp_path
    await engine.dispose()


def local_document(filename: str, content: bytes) -> dict:
    return {"filename": filename, "content_hash": hashlib.sha256(content).hexdigest(), "size_bytes": len(content), "mime_type": "text/markdown" if filename.endswith(".md") else "text/plain"}


async def _seed_kb(factory, user, slug: str) -> str:
    async with factory() as session:
        resource = await ResourceService(session, actor_from_user(user)).create_resource(
            resource_type="knowledge_base",
            slug=slug,
            display_name=slug.capitalize(),
            storage_kind="database",
        )
        await session.commit()
        return resource.id


async def _register_import(factory, knowledge, owner, kb_id: str, documents: list[tuple[str, bytes]]) -> dict:
    request = resources.LocalImportRequest(
        documents=[local_document(name, content) for name, content in documents],
        device_id=DEVICE_ID,
    )
    return await resources.register_knowledge_local_import(kb_id, request, owner, knowledge=knowledge)


async def _upload_to_copy(factory, knowledge, owner, copy_id: str, documents: list[tuple[str, bytes]]) -> None:
    for name, content in documents:
        await knowledge.upload_document(actor_from_user(owner), copy_id, FakeUpload(name, content))


async def _mark_ready(factory, resource_id: str) -> None:
    """The platform ingestion worker promotes uploads to ready; mirrored here."""
    async with factory() as session:
        rows = await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.resource_id == resource_id))
        for document in rows.scalars():
            document.status = "ready"
        await session.commit()


async def _run_builds(scheduled: list, provider: FakePublishProvider) -> None:
    """Await each scheduled build with the test's controllable provider."""
    for func, args, kwargs in scheduled:
        call_kwargs = {key: value for key, value in kwargs.items() if key != "provider"}
        await func(*args, provider=provider, **call_kwargs)


@pytest.mark.asyncio
async def test_preview_and_unconfirmed_confirm_upload_nothing(env) -> None:
    """T115-01: the destination is explained first; an unconfirmed call never uploads."""
    factory, knowledge, owner, *_ = env
    kb_id = await _seed_kb(factory, owner, "preview")
    revision = await _register_import(factory, knowledge, owner, kb_id, [("marked.md", MARKER)])

    preview = await resources.preview_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert preview["source"]["manifest_hash"] == revision["manifest_hash"]
    assert preview["documents"][0]["filename"] == "marked.md"
    assert preview["documents"][0]["content_hash"] == hashlib.sha256(MARKER).hexdigest()
    assert preview["destination"]["kind"] == "server_copy"
    assert preview["destination"]["visibility"] == "private"
    assert preview["upload_policy"]["requires_explicit_confirmation"] is True

    async with factory() as session:
        before = list((await session.execute(select(Resource))).scalars())

    with pytest.raises(HTTPException) as refusal:
        await resources.confirm_knowledge_local_publication(kb_id, str(revision["id"]), resources.LocalPublicationConfirmRequest(confirmed=False), owner, knowledge=knowledge)
    assert refusal.value.status_code == 409
    assert "LOCAL_PUBLISH_CONFIRMATION_REQUIRED" in str(refusal.value.detail)

    async with factory() as session:
        after = list((await session.execute(select(Resource))).scalars())
    # No copy was created, nothing was uploaded, and no fake success state exists.
    assert [resource.id for resource in after] == [resource.id for resource in before]
    status = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert status["status"] == "none"
    assert status["copy"] is None


@pytest.mark.asyncio
async def test_confirmed_publication_builds_independent_provenanced_copy(env) -> None:
    """T115-02: confirm -> content upload -> governed copy; team reaches the server copy."""
    factory, knowledge, owner, teammate, intruder, admin, audit_calls, _ = env
    kb_id = await _seed_kb(factory, owner, "team")
    revision = await _register_import(factory, knowledge, owner, kb_id, [("marked.md", MARKER)])
    # The frozen local revision anchors the device KB (the #113 LIVE pointer).
    await resources.activate_knowledge_local_revision(kb_id, str(revision["id"]), owner, knowledge=knowledge)

    confirmed = await resources.confirm_knowledge_local_publication(kb_id, str(revision["id"]), resources.LocalPublicationConfirmRequest(confirmed=True), owner, knowledge=knowledge)
    assert confirmed["status"] == "awaiting_content"
    copy_id = confirmed["copy"]["resource_id"]
    assert confirmed["copy"]["visibility"] == "private"
    assert confirmed["copy"]["resource_id"] != kb_id

    await _upload_to_copy(factory, knowledge, owner, copy_id, [("marked.md", MARKER)])
    await _mark_ready(factory, copy_id)

    # Drive the facade directly so the scheduled build executor is awaitable.
    scheduled: list = []
    publication = await knowledge.complete_local_publication(actor_from_user(owner), kb_id, str(revision["id"]), schedule=lambda func, *args, **kwargs: scheduled.append((func, args, kwargs)))
    assert publication["status"] == "publishing"
    assert publication["missing_documents"] == []
    assert scheduled, "the standard provider build must be scheduled"
    await _run_builds(scheduled, FakePublishProvider())

    status = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert status["status"] == "published"
    assert status["revision"]["provider_dataset_id"].startswith("copy-dataset-")
    assert status["copy"]["visibility"] == "private"

    async with factory() as session:
        copy = await session.get(Resource, copy_id)
        source_kb = await session.get(KnowledgeBase, kb_id)
        copy_revision = (await session.execute(select(KnowledgeRevision).where(KnowledgeRevision.knowledge_base_id == copy_id))).scalar_one()
        source_revision = await session.get(KnowledgeRevision, str(revision["id"]))
        assert copy.owner_id == owner.id and copy.visibility == "private"
        # The device KB keeps its private local identity: pointer and draft status
        # survive the publication unchanged (no silent replacement of the frozen view).
        assert source_kb.active_revision_id == str(revision["id"])
        assert source_revision.status == "draft"
        entries = list(copy_revision.manifest_json or [])
        assert copy_revision.status == "published"
        assert entries[0]["metadata"]["origin"] == "local_publication"
        provenance = entries[0]["metadata"]["published_from"]
        assert provenance["source_knowledge_base_id"] == kb_id
        assert provenance["source_revision_id"] == str(revision["id"])
        assert provenance["source_manifest_hash"] == revision["manifest_hash"]

    # Governance reuse: the published copy qualifies for the visibility flow,
    # while the device KB (draft-only revisions) can never expand.
    async with factory() as session:
        service = ResourceService(session, actor_from_user(owner))
        application = await service.request_visibility(copy_id, target_visibility="public", scope_department_id=None, reason="team onboarding")
        await session.commit()
        assert application.status == "pending"
        reviewer = ResourceService(session, actor_from_user(admin))
        await reviewer.review_visibility_application(str(application.id), approve=True, comment="ok")
        await session.commit()

    async with factory() as session:
        copy = await session.get(Resource, copy_id)
        assert copy.visibility == "public"

    # The teammate now resolves the SERVER copy through the provider dataset,
    # never through the owner's device.
    async with factory() as session:
        copy = await session.get(Resource, copy_id)
        copy_revision = (await session.execute(select(KnowledgeRevision).where(KnowledgeRevision.knowledge_base_id == copy_id))).scalar_one()
        source_resource = await session.get(Resource, kb_id)
        source_revision_row = await session.get(KnowledgeRevision, str(revision["id"]))
        team_bindings, _, _, team_metadata = build_frozen_knowledge_bindings([SimpleNamespace(resource=copy, knowledge_revision=copy_revision)], caller_user_id="teammate")
        assert set(team_bindings.values()) == {status["revision"]["provider_dataset_id"]}
        assert team_metadata[status["revision"]["provider_dataset_id"]].get("origin") != "local_import"
        # The device-local revision binds nothing for a non-owner caller: no
        # local dataset, no dispatch to the owner's device.
        local_bindings, _, _, local_metadata = build_frozen_knowledge_bindings([SimpleNamespace(resource=source_resource, knowledge_revision=source_revision_row)], caller_user_id="teammate")
        assert local_bindings == {} and local_metadata == {}

    # Permission failures stay explicit at the HTTP boundary too.
    with pytest.raises(HTTPException) as forbidden:
        await resources.confirm_knowledge_local_publication(kb_id, str(revision["id"]), resources.LocalPublicationConfirmRequest(confirmed=True), intruder, knowledge=knowledge)
    assert forbidden.value.status_code in {403, 404}
    audited = {call[1] for call in audit_calls}
    assert "knowledge_local_publication_confirmed" in audited
    assert "knowledge_local_publication_completed" in audited


@pytest.mark.asyncio
async def test_completion_enforces_exact_frozen_content_and_permissions(env) -> None:
    """T115-03/T115-04: partial or drifted uploads are explicit refusals, never a publish."""
    factory, knowledge, owner, teammate, intruder, *_ = env
    kb_id = await _seed_kb(factory, owner, "exact")
    revision = await _register_import(factory, knowledge, owner, kb_id, [("one.md", b"first\n"), ("two.md", b"second\n")])
    confirmed = await resources.confirm_knowledge_local_publication(kb_id, str(revision["id"]), resources.LocalPublicationConfirmRequest(confirmed=True), owner, knowledge=knowledge)
    copy_id = confirmed["copy"]["resource_id"]

    # Interrupted upload: one document missing -> explicit incomplete state.
    await _upload_to_copy(factory, knowledge, owner, copy_id, [("one.md", b"first\n")])
    await _mark_ready(factory, copy_id)
    scheduled: list = []
    with pytest.raises(HTTPException) as incomplete:
        await resources.complete_knowledge_local_publication(kb_id, str(revision["id"]), BackgroundTasks(), owner, knowledge=knowledge)
    assert incomplete.value.status_code == 409
    assert "LOCAL_PUBLISH_CONTENT_INCOMPLETE" in str(incomplete.value.detail)
    status = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert status["status"] == "awaiting_content"
    assert status["missing_documents"] == ["two.md"]

    # Content drift: an extra document that is not part of the frozen manifest.
    await _upload_to_copy(factory, knowledge, owner, copy_id, [("two.md", b"second\n"), ("stray.md", b"drift\n")])
    with pytest.raises(ResourceConflict) as drifted:
        await knowledge.complete_local_publication(actor_from_user(owner), kb_id, str(revision["id"]), schedule=lambda *args, **kwargs: None)
    assert "LOCAL_PUBLISH_CONTENT_DRIFTED" in str(drifted.value)

    # Retry after the interrupted upload: the same copy is reused, not duplicated.
    async with factory() as session:
        rows = await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.resource_id == copy_id))
        for document in rows.scalars():
            if document.original_filename == "stray.md":
                document.status = "deleted"
            else:
                document.status = "ready"
        await session.commit()
    publication = await knowledge.complete_local_publication(actor_from_user(owner), kb_id, str(revision["id"]), schedule=lambda func, *args, **kwargs: scheduled.append((func, args, kwargs)))
    assert publication["status"] == "publishing"
    assert publication["copy"]["resource_id"] == copy_id

    # A non-owner can neither confirm nor complete: the surface stays owner-bound.
    with pytest.raises(HTTPException) as teammate_view:
        await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), teammate, knowledge=knowledge)
    assert teammate_view.value.status_code in {403, 404}


@pytest.mark.asyncio
async def test_failed_build_is_visible_and_retry_never_replaces(env) -> None:
    """T115-04: build failure is a real state; retry republishes; no two-way sync."""
    factory, knowledge, owner, *_ = env
    kb_id = await _seed_kb(factory, owner, "retry")
    revision = await _register_import(factory, knowledge, owner, kb_id, [("marked.md", MARKER)])
    await resources.confirm_knowledge_local_publication(kb_id, str(revision["id"]), resources.LocalPublicationConfirmRequest(confirmed=True), owner, knowledge=knowledge)
    status = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    copy_id = status["copy"]["resource_id"]
    await _upload_to_copy(factory, knowledge, owner, copy_id, [("marked.md", MARKER)])
    await _mark_ready(factory, copy_id)

    failing = FakePublishProvider(fail_ingest_on_call=1)
    scheduled: list = []
    await knowledge.complete_local_publication(actor_from_user(owner), kb_id, str(revision["id"]), schedule=lambda func, *args, **kwargs: scheduled.append((func, args, kwargs)))
    await _run_builds(scheduled, failing)

    failed = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert failed["status"] == "failed"
    assert failed["revision"]["failure_code"] == "parse_failed"

    # Retry: the failed copy revision republishes through the same explicit gate.
    good = FakePublishProvider()
    scheduled.clear()
    retried = await knowledge.complete_local_publication(actor_from_user(owner), kb_id, str(revision["id"]), schedule=lambda func, *args, **kwargs: scheduled.append((func, args, kwargs)))
    await _run_builds(scheduled, good)
    assert retried["status"] == "publishing"
    retried = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert retried["status"] == "published"

    # No two-way sync: a later device import publishes only as a NEW copy and
    # the existing copy stays exactly as published.
    second = await _register_import(factory, knowledge, owner, kb_id, [("marked.md", b"# marker v2 CHANGED\n")])
    later = await resources.get_knowledge_local_publication(kb_id, str(second["id"]), owner, knowledge=knowledge)
    assert later["status"] == "none"
    unchanged = await resources.get_knowledge_local_publication(kb_id, str(revision["id"]), owner, knowledge=knowledge)
    assert unchanged["status"] == "published"
    assert unchanged["revision"]["id"] == retried["revision"]["id"]
    async with factory() as session:
        copies = list((await session.execute(select(Resource).where(Resource.type == "knowledge_base").order_by(Resource.created_at))).scalars())
        published_copy = await session.get(Resource, copy_id)
        assert published_copy.visibility == "private" or published_copy.visibility == "public"
        assert len(copies) == 2  # device KB + exactly one copy: second not auto-published
