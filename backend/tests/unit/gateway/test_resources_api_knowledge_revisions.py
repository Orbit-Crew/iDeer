"""Knowledge revision candidate endpoints follow Resource Governance (M4 ticket 01).

The revision endpoints are thin: they resolve the request into an actor plus
an intent and delegate to the injected :class:`KnowledgeFacade` seam, which
owns provider acquisition, commits, and audit. These tests inject a facade
bound to their own engine instead of patching route module globals.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.models import KnowledgeDocument
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resource_models import Resource
from app.agentplatform.resources.actors import actor_from_user
from app.agentplatform.resources.service import ResourceService
from app.gateway.routers import resources
from deerflow.persistence.base import Base


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple]:
    monkeypatch.setattr("app.agentplatform.knowledge.revisions.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'revisions-api.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    current_user = UserModel(
        id="owner",
        username="owner@test.com",
        role=UserRole.USER,
        department_id="dept-a",
        disabled=False,
    )
    async with factory() as session:
        session.add(current_user)
        await session.commit()
    audit_calls: list[tuple] = []

    async def audit(actor_id, action, resource_type=None, resource_id=None, detail=None, ip_address=None) -> None:
        audit_calls.append((actor_id, action, resource_type, resource_id, detail))

    def make_facade(*, provider_factory) -> KnowledgeFacade:
        return KnowledgeFacade(factory, audit=audit, provider_factory=provider_factory)

    yield factory, make_facade, current_user, audit_calls, tmp_path
    await engine.dispose()


def _seed_ready_document(session, tmp_path: Path, kb, filename: str, content: bytes) -> KnowledgeDocument:
    document_id = str(uuid.uuid4())
    path = tmp_path / "knowledge-documents" / kb.id / f"{document_id}-{filename}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    row = KnowledgeDocument(
        id=document_id,
        resource_id=kb.id,
        original_filename=filename,
        size_bytes=len(content),
        mime_type="text/plain",
        content_hash=hashlib.sha256(content).hexdigest(),
        storage_key=path.relative_to(tmp_path).as_posix(),
        metadata_json={},
        provider_document_id="provider-doc-1",
        status="ready",
        created_by=kb.owner_id,
    )
    session.add(row)
    return row


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


@pytest.mark.asyncio
async def test_revision_create_list_detail_and_audit(env) -> None:
    factory, make_facade, current_user, audit_calls, tmp_path = env
    knowledge = make_facade(provider_factory=lambda: None)
    kb_id = await _seed_kb(factory, current_user, "revisions")
    async with factory() as session:
        kb = await session.get(Resource, kb_id)
        _seed_ready_document(session, tmp_path, kb, "guide.txt", b"knowledge bytes")
        await session.commit()

    revision = await resources.create_knowledge_revision(kb_id, current_user, knowledge=knowledge)
    assert revision["status"] == "draft"
    assert revision["document_count"] == 1
    assert revision["resource_id"] == kb_id
    assert "provider_dataset_id" not in revision
    assert "provider_type" not in revision
    assert audit_calls[-1][1] == "knowledge_revision_created"
    assert audit_calls[-1][3] == revision["id"]

    listed = await resources.list_knowledge_revisions(kb_id, current_user, knowledge=knowledge)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == revision["id"]

    detail = await resources.get_knowledge_revision(kb_id, str(revision["id"]), current_user, knowledge=knowledge)
    assert detail["documents"][0]["filename"] == "guide.txt"
    assert detail["documents"][0]["content_hash"] == hashlib.sha256(b"knowledge bytes").hexdigest()


@pytest.mark.asyncio
async def test_revision_endpoints_enforce_governance(env) -> None:
    factory, make_facade, current_user, _, tmp_path = env
    knowledge = make_facade(provider_factory=lambda: None)
    kb_id = await _seed_kb(factory, current_user, "private")
    async with factory() as session:
        kb = await session.get(Resource, kb_id)
        _seed_ready_document(session, tmp_path, kb, "guide.txt", b"bytes")
        await session.commit()
    revision = await resources.create_knowledge_revision(kb_id, current_user, knowledge=knowledge)

    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)

    with pytest.raises(HTTPException) as hidden:
        await resources.list_knowledge_revisions(kb_id, intruder, knowledge=knowledge)
    assert hidden.value.status_code == 404

    with pytest.raises(HTTPException) as forbidden:
        await resources.create_knowledge_revision(kb_id, intruder, knowledge=knowledge)
    assert forbidden.value.status_code in {403, 404}

    with pytest.raises(HTTPException) as scoped:
        await resources.get_knowledge_revision(str(uuid.uuid4()), str(revision["id"]), current_user, knowledge=knowledge)
    assert scoped.value.status_code == 404


@pytest.mark.asyncio
async def test_publish_endpoint_transitions_and_schedules_build(env) -> None:
    factory, make_facade, current_user, audit_calls, tmp_path = env
    knowledge = make_facade(provider_factory=lambda: object())
    kb_id = await _seed_kb(factory, current_user, "publish")
    async with factory() as session:
        kb = await session.get(Resource, kb_id)
        _seed_ready_document(session, tmp_path, kb, "guide.txt", b"bytes")
        await session.commit()
    revision = await resources.create_knowledge_revision(kb_id, current_user, knowledge=knowledge)

    background = BackgroundTasks()
    payload = await resources.publish_knowledge_revision(kb_id, str(revision["id"]), background, current_user, knowledge=knowledge)
    assert payload["status"] == "indexing"
    assert len(background.tasks) == 1
    assert audit_calls[-1][1] == "knowledge_revision_publish_requested"

    with pytest.raises(HTTPException) as duplicate:
        await resources.publish_knowledge_revision(kb_id, str(revision["id"]), BackgroundTasks(), current_user, knowledge=knowledge)
    assert duplicate.value.status_code == 409


@pytest.mark.asyncio
async def test_prepare_endpoint_is_separate_from_publish_and_does_not_require_eval(env, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, make_facade, current_user, _, tmp_path = env
    monkeypatch.setenv("IDEER_KNOWLEDGE_EVAL_REQUIRED", "1")
    knowledge = make_facade(provider_factory=lambda: object())
    kb_id = await _seed_kb(factory, current_user, "prepare")
    async with factory() as session:
        kb = await session.get(Resource, kb_id)
        _seed_ready_document(session, tmp_path, kb, "guide.txt", b"bytes")
        await session.commit()
    revision = await resources.create_knowledge_revision(kb_id, current_user, knowledge=knowledge)

    background = BackgroundTasks()
    payload = await resources.prepare_knowledge_revision(kb_id, str(revision["id"]), background, current_user, knowledge=knowledge)

    assert payload["status"] == "indexing"
    assert len(background.tasks) == 1
    assert payload["resource_id"] == kb_id


@pytest.mark.asyncio
async def test_publish_endpoint_reports_unavailable_without_provider(env) -> None:
    """No configured knowledge provider is a 503, not a client conflict."""
    factory, make_facade, current_user, _, tmp_path = env
    knowledge = make_facade(provider_factory=lambda: None)
    kb_id = await _seed_kb(factory, current_user, "noprov")
    async with factory() as session:
        kb = await session.get(Resource, kb_id)
        _seed_ready_document(session, tmp_path, kb, "guide.txt", b"bytes")
        await session.commit()
    revision = await resources.create_knowledge_revision(kb_id, current_user, knowledge=knowledge)

    with pytest.raises(HTTPException) as unavailable:
        await resources.publish_knowledge_revision(kb_id, str(revision["id"]), BackgroundTasks(), current_user, knowledge=knowledge)
    assert unavailable.value.status_code == 503
