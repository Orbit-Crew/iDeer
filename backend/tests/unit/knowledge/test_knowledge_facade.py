"""The knowledge facade is the single seam between HTTP routes and the
knowledge domain: callers pass an actor and an intent, while service
construction, provider passing, commits, and audit stay behind the seam."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.models import KnowledgeDocument
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resources.actors import actor_from_user
from app.agentplatform.resources.service import ResourceNotFound, ResourceService
from deerflow.persistence.base import Base


class FakeUpload:
    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain") -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self.closed = False

    async def read(self, size: int) -> bytes:
        if not self._content:
            return b""
        chunk, self._content = self._content[:size], self._content[size:]
        return chunk

    async def close(self) -> None:
        self.closed = True


@pytest_asyncio.fixture
async def env(tmp_path) -> AsyncIterator[tuple]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'facade.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner = UserModel(id="owner", username="owner@test.com", role=UserRole.USER, department_id="dept-a", disabled=False)
    async with factory() as session:
        session.add(owner)
        await session.commit()
    audit_calls: list[tuple] = []

    async def audit(actor_id, action, resource_type=None, resource_id=None, detail=None, ip_address=None) -> None:
        audit_calls.append((actor_id, action, resource_type, resource_id, detail))

    facade = KnowledgeFacade(factory, audit=audit)
    yield factory, facade, owner, audit_calls
    await engine.dispose()


async def _seed_kb(factory, owner, slug: str = "seam") -> str:
    async with factory() as session:
        resource = await ResourceService(session, actor_from_user(owner)).create_resource(
            resource_type="knowledge_base",
            slug=slug,
            display_name=slug,
            storage_kind="database",
        )
        await session.commit()
        return resource.id


@pytest.mark.asyncio
async def test_upload_document_persists_commits_and_audits(env, tmp_path, monkeypatch) -> None:
    factory, facade, owner, audit_calls = env
    monkeypatch.setattr("app.agentplatform.knowledge.documents.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    kb_id = await _seed_kb(factory, owner)
    upload = FakeUpload("guide.txt", b"hello knowledge")

    document = await facade.upload_document(actor_from_user(owner), kb_id, upload)

    assert document["name"] == "guide.txt"
    assert document["status"] == "uploaded"
    async with factory() as session:
        row = await session.get(KnowledgeDocument, document["id"])
    assert row is not None, "facade must commit the upload"
    assert upload.closed is True
    assert audit_calls == [
        (
            "owner",
            "knowledge_document_uploaded",
            "knowledge_document",
            document["id"],
            {"resource_id": kb_id, "content_hash": document["content_hash"], "size": document["size"]},
        )
    ]


@pytest.mark.asyncio
async def test_update_and_delete_document_intents_audit_exact_payloads(env, tmp_path, monkeypatch) -> None:
    factory, facade, owner, audit_calls = env
    monkeypatch.setattr("app.agentplatform.knowledge.documents.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    kb_id = await _seed_kb(factory, owner)
    document = await facade.upload_document(actor_from_user(owner), kb_id, FakeUpload("guide.txt", b"hello"))

    updated = await facade.update_document(actor_from_user(owner), kb_id, document["id"], title="Guide", metadata=None)
    assert updated["name"] == "Guide"
    assert audit_calls[-1] == ("owner", "knowledge_document_updated", "knowledge_document", document["id"], {"resource_id": kb_id, "changed_title": True, "changed_metadata": False})

    deleted = await facade.request_document_delete(actor_from_user(owner), kb_id, document["id"])
    assert deleted["status"] == "deleting"
    assert audit_calls[-1] == ("owner", "knowledge_document_delete_requested", "knowledge_document", document["id"], {"resource_id": kb_id, "status": "deleting", "failure_code": None})

    retried = await facade.request_document_rebuild(actor_from_user(owner), kb_id, document["id"])
    assert retried["status"] == "rebuild_requested"
    assert audit_calls[-1][:4] == ("owner", "knowledge_document_rebuild_requested", "knowledge_document", document["id"])


@pytest.mark.asyncio
async def test_document_intents_enforce_the_visibility_guard(env, tmp_path, monkeypatch) -> None:
    factory, facade, owner, audit_calls = env
    monkeypatch.setattr("app.agentplatform.knowledge.documents.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    kb_id = await _seed_kb(factory, owner)
    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)

    with pytest.raises(ResourceNotFound):
        await facade.list_documents(actor_from_user(intruder), kb_id)
    with pytest.raises(ResourceNotFound):
        await facade.upload_document(actor_from_user(intruder), kb_id, FakeUpload("guide.txt", b"x"))
    assert audit_calls == [], "rejected intents never reach the audit sink"


@pytest.mark.asyncio
async def test_eval_case_intents_commit_and_audit(env) -> None:
    factory, facade, owner, audit_calls = env
    kb_id = await _seed_kb(factory, owner)
    async with factory() as session:
        document_id = str(uuid.uuid4())
        session.add(
            KnowledgeDocument(
                id=document_id,
                resource_id=kb_id,
                original_filename="guide.txt",
                size_bytes=8,
                mime_type="text/plain",
                content_hash="0" * 64,
                storage_key=f"knowledge-documents/{kb_id}/{document_id}-guide.txt",
                metadata_json={},
                status="ready",
                created_by=owner.id,
            )
        )
        await session.commit()

    created = await facade.create_eval_case(actor_from_user(owner), kb_id, question="What is the retry policy?", expected_document_ids=[document_id], tags=["regression"])
    assert created["version_no"] == 1
    assert audit_calls[-1] == (
        "owner",
        "eval_case_created",
        "knowledge_eval_case",
        created["id"],
        {"resource_id": kb_id, "version_no": 1, "content_hash": created["content_hash"], "expected_document_count": 1},
    )

    updated = await facade.update_eval_case(actor_from_user(owner), kb_id, created["id"], question=None, expected_document_ids=None, tags=["regression", "smoke"])
    assert updated["version_no"] == 2
    assert audit_calls[-1] == ("owner", "eval_case_updated", "knowledge_eval_case", created["id"], {"resource_id": kb_id, "version_no": 2, "content_hash": updated["content_hash"]})

    await facade.delete_eval_case(actor_from_user(owner), kb_id, created["id"])
    assert audit_calls[-1] == ("owner", "eval_case_deleted", "knowledge_eval_case", created["id"], {"resource_id": kb_id})

    listed = await facade.list_eval_cases(actor_from_user(owner), kb_id)
    assert listed == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_read_intents_return_payloads_without_auditing(env) -> None:
    factory, facade, owner, audit_calls = env
    kb_id = await _seed_kb(factory, owner)

    listed = await facade.list_documents(actor_from_user(owner), kb_id)
    assert listed == {"items": [], "total": 0}
    initialized = await facade.request_initialization(actor_from_user(owner), kb_id)
    assert initialized == {"resource_id": kb_id, "status": "initializing", "error": None}
    assert audit_calls[-1] == ("owner", "knowledge_initialization_requested", "knowledge_base", kb_id, {"status": "initializing"})

    audit_calls.clear()
    assert await facade.list_eval_cases(actor_from_user(owner), kb_id) == {"items": [], "total": 0}
    assert await facade.list_documents(actor_from_user(owner), kb_id) == {"items": [], "total": 0}
    assert audit_calls == [], "read intents do not audit"
