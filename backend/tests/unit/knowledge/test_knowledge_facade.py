"""The knowledge facade is the single seam between HTTP routes and the
knowledge domain: callers pass an actor and an intent, while service
construction, provider passing, commits, and audit stay behind the seam."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.models import KnowledgeDocument, KnowledgeRevision
from app.agentplatform.knowledge.provider import KnowledgeProviderUnavailable
from app.agentplatform.knowledge.retrieval_test import RetrievalTestStorageUnavailable
from app.agentplatform.knowledge.revisions import execute_publish
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resources.actors import actor_from_user
from app.agentplatform.resources.service import ResourceConflict, ResourceNotFound, ResourceService
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


async def _seed_document_row(factory, kb_id: str, owner_id: str) -> str:
    """Insert one ready KnowledgeDocument row so eval cases can reference it."""
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
                created_by=owner_id,
            )
        )
        await session.commit()
        return document_id


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


# ---------------------------------------------------------------------------
# Revision, retrieval-test, evaluation, and policy intents (ticket 03)
# ---------------------------------------------------------------------------


class _FakePublishProvider:
    """Minimal provider standing in for a configured RAGFlow deployment."""

    def __init__(self) -> None:
        self.created: list[str] = []

    async def create_dataset(self, *, name: str, embedding_model: str | None = None) -> str:
        dataset_id = f"dataset-{len(self.created) + 1}"
        self.created.append(dataset_id)
        return dataset_id


def _schedule_recorder() -> tuple[list[tuple], object]:
    scheduled: list[tuple] = []

    def schedule(func, *args, **kwargs) -> None:
        scheduled.append((func, args, kwargs))

    return scheduled, schedule


@pytest.mark.asyncio
async def test_policy_intents_read_and_version_with_commit(env) -> None:
    factory, facade, owner, audit_calls = env
    actor = actor_from_user(owner)
    kb_id = await _seed_kb(factory, owner)
    document_id = await _seed_document_row(factory, kb_id, owner.id)
    case = await facade.create_eval_case(actor, kb_id, question="retry?", expected_document_ids=[document_id], tags=[])
    audit_calls.clear()

    assert await facade.get_evaluation_policy(actor, kb_id) == {"configured": False}

    saved = await facade.put_evaluation_policy(
        actor,
        kb_id,
        profile_id="frozen",
        top_k=8,
        case_ids=[case["id"]],
        min_expected_hit_rate=0.5,
        min_recall_at_k=0.5,
        min_mrr_at_k=0.5,
    )
    assert saved["version"] == 1
    async with factory() as session:
        from app.agentplatform.knowledge.models import KnowledgeEvaluationPolicy

        row = await session.get(KnowledgeEvaluationPolicy, kb_id)
    assert row is not None, "policy intent must commit"
    assert row.top_k == 8

    reread = await facade.get_evaluation_policy(actor, kb_id)
    assert reread["version"] == 1 and reread["case_ids"] == [case["id"]]
    assert audit_calls == [], "policy intents do not audit"


@pytest.mark.asyncio
async def test_policy_intents_classify_non_knowledge_base_as_missing(env) -> None:
    """A non-KB resource reads as ResourceNotFound (404), not a conflict."""
    factory, facade, owner, _ = env
    actor = actor_from_user(owner)
    async with factory() as session:
        workflow = await ResourceService(session, actor).create_resource(
            resource_type="workflow",
            slug="plain-workflow",
            display_name="Plain Workflow",
            storage_kind="database",
        )
        await session.commit()
        workflow_id = workflow.id

    with pytest.raises(ResourceNotFound):
        await facade.get_evaluation_policy(actor, workflow_id)
    with pytest.raises(ResourceNotFound):
        await facade.put_evaluation_policy(
            actor,
            workflow_id,
            profile_id="frozen",
            top_k=8,
            case_ids=[],
            min_expected_hit_rate=0.5,
            min_recall_at_k=0.5,
            min_mrr_at_k=0.5,
        )


@pytest.mark.asyncio
async def test_revision_intents_commit_and_audit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agentplatform.knowledge.revisions.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'facade-revisions.db'}")
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

    facade = KnowledgeFacade(factory, audit=audit, provider_factory=lambda: object())
    kb_id = await _seed_kb(factory, owner)
    async with factory() as session:
        document_id = str(uuid.uuid4())
        path = tmp_path / "knowledge-documents" / kb_id / f"{document_id}-guide.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"knowledge bytes")
        session.add(
            KnowledgeDocument(
                id=document_id,
                resource_id=kb_id,
                original_filename="guide.txt",
                size_bytes=15,
                mime_type="text/plain",
                content_hash=hashlib.sha256(b"knowledge bytes").hexdigest(),
                storage_key=path.relative_to(tmp_path).as_posix(),
                metadata_json={},
                status="ready",
                created_by=owner.id,
            )
        )
        await session.commit()

    revision = await facade.create_revision(actor_from_user(owner), kb_id)
    assert revision["status"] == "draft" and revision["document_count"] == 1
    assert audit_calls[-1] == (
        "owner",
        "knowledge_revision_created",
        "knowledge_revision",
        revision["id"],
        {"resource_id": kb_id, "revision_no": 1, "manifest_hash": revision["manifest_hash"], "document_count": 1},
    )

    listed = await facade.list_revisions(actor_from_user(owner), kb_id)
    assert listed["total"] == 1
    detail = await facade.get_revision(actor_from_user(owner), kb_id, revision["id"])
    assert detail["documents"][0]["filename"] == "guide.txt"

    scheduled, schedule = _schedule_recorder()
    prepared = await facade.prepare_revision(actor_from_user(owner), kb_id, revision["id"], schedule=schedule)
    assert prepared["status"] == "indexing"
    assert len(scheduled) == 1
    assert scheduled[0][0] is execute_publish
    assert scheduled[0][2]["activate"] is False

    with pytest.raises(KnowledgeProviderUnavailable):
        await KnowledgeFacade(factory, audit=audit, provider_factory=lambda: None).publish_revision(
            actor_from_user(owner),
            kb_id,
            revision["id"],
            schedule=schedule,
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_retrieval_test_intent_archives_commits_and_audits(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agentplatform.knowledge.revisions.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'facade-retrieval.db'}")
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

    calls: list[dict] = []

    async def search(query, *, settings, dataset_id, document_ids, applied) -> dict:
        calls.append({"query": query, "dataset_id": dataset_id})
        return {"chunks": [], "total": 0}

    settings = SimpleNamespace(page_size=8, similarity_threshold=0.2, vector_similarity_weight=0.3, top_k=256, timeout=30.0)
    facade = KnowledgeFacade(factory, audit=audit, search=search, settings_factory=lambda: settings)
    kb_id = await _seed_kb(factory, owner)
    async with factory() as session:
        revision = KnowledgeRevision(
            id=str(uuid.uuid4()),
            knowledge_base_id=kb_id,
            revision_no=1,
            status="published",
            manifest_hash="a" * 64,
            manifest_json=[{"document_id": "doc-1"}],
            provider_doc_map_json={},
            provider_dataset_id="dataset-1",
            document_count=1,
            created_by=owner.id,
        )
        session.add(revision)
        await session.commit()
        revision_id = revision.id

    payload = await facade.create_retrieval_test(
        actor_from_user(owner),
        kb_id,
        revision_id=revision_id,
        query="What is the retry policy?",
        top_k=5,
        profile_id="frozen",
    )
    assert payload["result_status"] == "empty_hit"
    async with factory() as session:
        from app.agentplatform.knowledge.models import KnowledgeRetrievalTest

        row = await session.get(KnowledgeRetrievalTest, payload["id"])
    assert row is not None, "retrieval test intent must commit the archive"
    assert audit_calls[-1] == (
        "owner",
        "knowledge_retrieval_test_executed",
        "knowledge_base",
        kb_id,
        {"resource_id": kb_id, "revision_id": revision_id, "test_id": payload["id"], "result_status": "empty_hit"},
    )
    listed = await facade.list_retrieval_tests(actor_from_user(owner), kb_id, offset=0, limit=20)
    assert listed["total"] == 1
    assert (await facade.get_retrieval_test(actor_from_user(owner), kb_id, payload["id"]))["id"] == payload["id"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_retrieval_test_intent_reports_storage_refusal(tmp_path) -> None:
    """A storage failure while archiving classifies as a domain-level
    storage refusal the HTTP mapping turns into a 503."""

    class _RefusingService:
        def __init__(self, session, actor) -> None:
            pass

        async def execute(self, *args, **kwargs) -> dict:
            raise OperationalError("INSERT failed", {}, Exception("disk full"))

    class _RefusingFacade(KnowledgeFacade):
        def _retrieval_tests(self, session, actor):
            return _RefusingService(session, actor)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'facade-storage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner = UserModel(id="owner", username="owner@test.com", role=UserRole.USER, department_id="dept-a", disabled=False)
    async with factory() as session:
        session.add(owner)
        await session.commit()

    async def _noop_audit(*args, **kwargs) -> None:
        return None

    facade = _RefusingFacade(factory, audit=_noop_audit)
    kb_id = await _seed_kb(factory, owner)
    with pytest.raises(RetrievalTestStorageUnavailable):
        await facade.create_retrieval_test(
            actor_from_user(owner),
            kb_id,
            revision_id=str(uuid.uuid4()),
            query="anything",
            top_k=None,
            profile_id="frozen",
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_evaluation_intents_start_list_read_and_retry(env) -> None:
    factory, facade, owner, audit_calls = env
    owner_actor = actor_from_user(owner)
    kb_id = await _seed_kb(factory, owner)
    document_id = await _seed_document_row(factory, kb_id, owner.id)
    async with factory() as session:
        revision_id = str(uuid.uuid4())
        session.add(
            KnowledgeRevision(
                id=revision_id,
                knowledge_base_id=kb_id,
                revision_no=1,
                status="published",
                manifest_hash="a" * 64,
                manifest_json=[{"document_id": document_id}],
                provider_doc_map_json={},
                provider_dataset_id="dataset-1",
                document_count=1,
                created_by=owner.id,
            )
        )
        await session.commit()
    case = await facade.create_eval_case(owner_actor, kb_id, question="retry?", expected_document_ids=[document_id], tags=[])

    started = await facade.create_evaluation(owner_actor, kb_id, revision_id=revision_id, profile_id="frozen", top_k=8, case_ids=[case["id"]])
    assert started["status"] == "queued"
    assert audit_calls[-1] == ("owner", "knowledge_evaluation_started", "knowledge_base", kb_id, {"run_id": started["id"], "revision_id": revision_id})

    listed = await facade.list_evaluations(owner_actor, kb_id, offset=0, limit=20)
    assert listed["total"] == 1
    detail = await facade.get_evaluation(owner_actor, kb_id, started["id"], result_offset=0, result_limit=20)
    assert detail["id"] == started["id"]

    with pytest.raises(ResourceConflict):
        await facade.retry_evaluation(owner_actor, kb_id, started["id"])

    comparison = await facade.create_evaluation_comparison(
        owner_actor,
        kb_id,
        left_revision_id=revision_id,
        left_profile_id="frozen",
        right_revision_id=revision_id,
        right_profile_id="configured",
        top_k=8,
        case_ids=[case["id"]],
    )
    assert comparison["status"] == "queued"
    assert audit_calls[-1] == ("owner", "knowledge_evaluation_comparison_started", "knowledge_base", kb_id, {"comparison_id": comparison["id"]})
    fetched = await facade.get_evaluation_comparison(owner_actor, kb_id, comparison["id"])
    assert fetched["id"] == comparison["id"]
