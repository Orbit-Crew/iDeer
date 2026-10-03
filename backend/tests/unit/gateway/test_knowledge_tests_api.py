"""Retrieval test, evaluation, and policy endpoints follow Resource Governance
and the canonical API (M6 ticket 01; facade seam per 2026-10-03 ticket 03).

The endpoints are thin: they resolve the request into an actor plus an intent
and delegate to the injected :class:`KnowledgeFacade` seam, which owns
retrieval wiring, commits, and audit. These tests inject a facade bound to
their own engine instead of patching route module globals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.models import KnowledgeDocument, KnowledgeRevision
from app.agentplatform.knowledge.provider import ProviderIngestionResult
from app.agentplatform.knowledge.revisions import KnowledgeRevisionService, execute_publish
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resource_models import Resource
from app.agentplatform.resources.actors import actor_from_user, role_permissions
from app.agentplatform.resources.service import ResourceActor, ResourceService
from app.gateway.routers import knowledge_tests
from deerflow.community.ragflow.client import RAGFlowConnectionError
from deerflow.persistence.base import Base

_SETTINGS = SimpleNamespace(page_size=8, similarity_threshold=0.2, vector_similarity_weight=0.3, top_k=256, timeout=30.0)


class _FakePublishProvider:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.docs: dict[str, list[dict]] = {}

    async def create_dataset(self, *, name: str, embedding_model: str | None = None) -> str:
        dataset_id = f"published-dataset-{len(self.created) + 1}"
        self.created.append(dataset_id)
        self.docs[dataset_id] = []
        return dataset_id

    async def ingest(self, *, dataset_id: str, filename: str, mime_type: str, content: bytes, provider_document_id: str | None = None, rebuild: bool = False) -> ProviderIngestionResult:
        document_id = f"provider-doc-{len(self.docs[dataset_id]) + 1}"
        self.docs[dataset_id].append({"id": document_id, "name": filename})
        return ProviderIngestionResult(document_id, "processing")

    async def get_status(self, *, dataset_id: str, provider_document_id: str) -> str:
        return "ready"

    async def delete_document(self, *, dataset_id: str, provider_document_id: str) -> None:
        return None

    async def list_dataset_documents(self, *, dataset_id: str) -> list[dict]:
        return list(self.docs.get(dataset_id, []))


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple]:
    monkeypatch.setattr("app.agentplatform.knowledge.revisions.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retrieval-tests-api.db'}")
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

    def make_facade(*, search=None, settings_factory=lambda: _SETTINGS) -> KnowledgeFacade:
        return KnowledgeFacade(factory, audit=audit, search=search, settings_factory=settings_factory)

    yield factory, make_facade, current_user, audit_calls, tmp_path
    await engine.dispose()


def _chunk_result(chunks: list[dict]) -> dict:
    return {"chunks": chunks, "total": len(chunks)}


def _search_recorder(result) -> tuple[list[dict], object]:
    calls: list[dict] = []

    async def search(query: str, *, settings, dataset_id: str, document_ids: list[str], applied: dict) -> dict:
        calls.append({"query": query, "dataset_id": dataset_id, "document_ids": list(document_ids), "applied": dict(applied)})
        if isinstance(result, Exception):
            raise result
        return result

    return calls, search


class _FailingStorageService:
    def __init__(self, session, actor) -> None:
        pass

    async def execute(self, *args, **kwargs) -> dict:
        from sqlalchemy.exc import OperationalError

        raise OperationalError("INSERT failed", {}, Exception("disk full"))


class _RefusingStorageFacade(KnowledgeFacade):
    def _retrieval_tests(self, session, actor):
        return _FailingStorageService(session, actor)


def _actor(user_id: str, *, permissions=None) -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset(permissions or role_permissions("user")),
    )


async def _seed_kb(factory, user, slug: str = "retrieval-api") -> Resource:
    async with factory() as session:
        resource = await ResourceService(session, actor_from_user(user)).create_resource(
            resource_type="knowledge_base",
            slug=slug,
            display_name=slug,
            storage_kind="database",
        )
        await session.commit()
        return resource


async def _seed_document(factory, tmp_path, kb_id: str, owner_id: str, filename: str) -> None:
    import hashlib

    async with factory() as session:
        document_id = str(uuid.uuid4())
        path = tmp_path / "knowledge-documents" / kb_id / f"{document_id}-{filename}"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"content of {filename}".encode()
        path.write_bytes(content)
        session.add(
            KnowledgeDocument(
                id=document_id,
                resource_id=kb_id,
                original_filename=filename,
                size_bytes=len(content),
                mime_type="text/plain",
                content_hash=hashlib.sha256(content).hexdigest(),
                storage_key=path.relative_to(tmp_path).as_posix(),
                metadata_json={},
                status="ready",
                created_by=owner_id,
            )
        )
        await session.commit()
        return SimpleNamespace(id=document_id)


async def _publish_revision(factory: async_sessionmaker, tmp_path, kb: Resource, owner_id: str, *, documents: int = 1) -> KnowledgeRevision:
    for index in range(documents):
        await _seed_document(factory, tmp_path, kb.id, owner_id, f"guide-{index}.txt")
    async with factory() as session:
        service = KnowledgeRevisionService(session, _actor(owner_id))
        candidate = await service.create_revision(kb.id)
        provider = _FakePublishProvider()
        await service.publish_revision(kb.id, str(candidate["id"]), provider=provider)
        await session.commit()
        revision_id = str(candidate["id"])
    await execute_publish(factory, resource_id=kb.id, revision_id=revision_id, actor_id=owner_id, provider=provider, poll_interval=0, parse_timeout=5)
    async with factory() as session:
        revision = await session.get(KnowledgeRevision, revision_id)
        assert revision is not None and revision.status == "published", (revision.status if revision else None, revision.failure_code if revision else None, revision.failure_message if revision else None)
        return revision


async def _noop_audit(*args, **kwargs) -> None:
    return None


@pytest.mark.asyncio
async def test_retrieval_test_execute_lists_and_replays_archives(env) -> None:
    factory, make_facade, current_user, audit_calls, tmp_path = env
    kb = await _seed_kb(factory, current_user)
    revision = await _publish_revision(factory, tmp_path, kb, current_user.id)
    provider_document_id = next(iter(revision.provider_doc_map_json.values()))
    calls, search = _search_recorder(_chunk_result([{"document_id": provider_document_id, "document_keyword": "guide-0.txt", "content": "Retry with backoff.", "similarity": 0.9, "page": 2}]))
    knowledge = make_facade(search=search)

    created = await knowledge_tests.create_retrieval_test(
        kb.id,
        knowledge_tests.RetrievalTestCreateRequest(revision_id=revision.id, query="What is the retry policy?", top_k=5),
        current_user,
        knowledge=knowledge,
    )
    assert created["result_status"] == "success"
    assert created["requested_top_k"] == 5
    assert created["revision_no"] == revision.revision_no
    assert created["manifest_hash"] == revision.manifest_hash
    assert created["retrieval_profile"] == {}
    assert created["applied_parameters"]["page_size"] == 5
    assert created["items"][0]["rank"] == 1
    assert calls[0]["dataset_id"] == revision.provider_dataset_id
    assert calls[0]["document_ids"] == sorted(revision.provider_doc_map_json.values())
    # Audit trail carries identity only, never the question text.
    assert audit_calls[-1][1] == "knowledge_retrieval_test_executed"
    assert "query" not in (audit_calls[-1][4] or {})

    listed = await knowledge_tests.list_retrieval_tests(kb.id, 0, 20, current_user, knowledge=knowledge)
    assert listed["total"] == 1
    summary = listed["items"][0]
    assert summary["id"] == created["id"]
    assert "items" not in summary and "applied_parameters" not in summary

    replayed = await knowledge_tests.get_retrieval_test(kb.id, str(created["id"]), current_user, knowledge=knowledge)
    assert replayed["items"][0]["content"] == "Retry with backoff."
    assert replayed["items"][0]["position"] == {"page": 2}
    assert len(calls) == 1  # replay reads the archive, no re-retrieval


@pytest.mark.asyncio
async def test_retrieval_test_request_rejects_unsupported_parameters() -> None:
    with pytest.raises(ValidationError):
        knowledge_tests.RetrievalTestCreateRequest(revision_id="r1", query="q", similarity_threshold=0.5)
    with pytest.raises(ValidationError):
        knowledge_tests.RetrievalTestCreateRequest(revision_id="r1", query="q", top_k=99)
    with pytest.raises(ValidationError):
        knowledge_tests.RetrievalTestCreateRequest(revision_id="r1", query="")


@pytest.mark.asyncio
async def test_retrieval_test_endpoint_distinct_safe_states(env) -> None:
    factory, make_facade, current_user, audit_calls, tmp_path = env
    kb = await _seed_kb(factory, current_user)
    revision = await _publish_revision(factory, tmp_path, kb, current_user.id)

    # Provider outage: the execution still archives as an explicit failure state.
    _, search = _search_recorder(RAGFlowConnectionError("internal detail"))
    knowledge = make_facade(search=search)
    failed = await knowledge_tests.create_retrieval_test(
        kb.id,
        knowledge_tests.RetrievalTestCreateRequest(revision_id=revision.id, query="anything"),
        current_user,
        knowledge=knowledge,
    )
    assert failed["result_status"] == "provider_error"
    assert failed["error_code"] == "connection_error"
    assert "internal detail" not in str(failed)

    # Retrieval tooling unconfigured: 503 with a distinct code.
    unconfigured = make_facade(settings_factory=lambda: None)
    with pytest.raises(HTTPException) as unavailable:
        await knowledge_tests.create_retrieval_test(
            kb.id,
            knowledge_tests.RetrievalTestCreateRequest(revision_id=revision.id, query="anything"),
            current_user,
            knowledge=unconfigured,
        )
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["code"] == "retrieval_test_unavailable"

    # Storage failure while archiving: 503 with a distinct storage code.
    refusing = _RefusingStorageFacade(factory, audit=_noop_audit)
    with pytest.raises(HTTPException) as storage:
        await knowledge_tests.create_retrieval_test(
            kb.id,
            knowledge_tests.RetrievalTestCreateRequest(revision_id=revision.id, query="anything"),
            current_user,
            knowledge=refusing,
        )
    assert storage.value.status_code == 503
    assert storage.value.detail["code"] == "retrieval_test_storage_unavailable"

    # A draft revision is not retrievable: 409, distinct from unknown (404).
    _, draft_search = _search_recorder(_chunk_result([]))
    draft_knowledge = make_facade(search=draft_search)
    await _seed_document(factory, tmp_path, kb.id, current_user.id, "draft-doc.txt")
    async with factory() as session:
        revision_service = KnowledgeRevisionService(session, _actor(current_user.id))
        candidate = await revision_service.create_revision(kb.id)
        await session.commit()
        draft_id = str(candidate["id"])
    with pytest.raises(HTTPException) as conflict:
        await knowledge_tests.create_retrieval_test(
            kb.id,
            knowledge_tests.RetrievalTestCreateRequest(revision_id=draft_id, query="anything"),
            current_user,
            knowledge=draft_knowledge,
        )
    assert conflict.value.status_code == 409

    # Unknown or invisible identifiers are uniformly 404.
    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)
    with pytest.raises(HTTPException) as hidden_list:
        await knowledge_tests.list_retrieval_tests(kb.id, 0, 20, intruder, knowledge=knowledge)
    assert hidden_list.value.status_code == 404
    with pytest.raises(HTTPException) as guessed_test:
        await knowledge_tests.get_retrieval_test(kb.id, str(uuid.uuid4()), current_user, knowledge=knowledge)
    assert guessed_test.value.status_code == 404
    with pytest.raises(HTTPException) as guessed_revision:
        await knowledge_tests.create_retrieval_test(
            kb.id,
            knowledge_tests.RetrievalTestCreateRequest(revision_id=str(uuid.uuid4()), query="anything"),
            current_user,
            knowledge=knowledge,
        )
    assert guessed_revision.value.status_code == 404


@pytest.mark.asyncio
async def test_evaluation_policy_classifies_missing_knowledge_base_as_404(env) -> None:
    """``ResourceNotFound`` semantics: a non-KB resource reads as 404, not 409."""
    factory, make_facade, current_user, _, _ = env
    knowledge = make_facade()
    async with factory() as session:
        workflow = await ResourceService(session, actor_from_user(current_user)).create_resource(
            resource_type="workflow",
            slug="plain-workflow",
            display_name="Plain Workflow",
            storage_kind="database",
        )
        await session.commit()
        workflow_id = workflow.id

    with pytest.raises(HTTPException) as hidden_get:
        await knowledge_tests.get_evaluation_policy(workflow_id, current_user, knowledge=knowledge)
    assert hidden_get.value.status_code == 404

    with pytest.raises(HTTPException) as hidden_put:
        await knowledge_tests.put_evaluation_policy(
            workflow_id,
            knowledge_tests.EvaluationPolicyRequest(
                profile_id="frozen",
                top_k=8,
                case_ids=[str(uuid.uuid4())],
                min_expected_hit_rate=0.5,
                min_recall_at_k=0.5,
                min_mrr_at_k=0.5,
            ),
            current_user,
            knowledge=knowledge,
        )
    assert hidden_put.value.status_code == 404


@pytest.mark.asyncio
async def test_evaluation_policy_round_trip_and_case_validation(env) -> None:
    factory, make_facade, current_user, _, tmp_path = env
    knowledge = make_facade()
    kb = await _seed_kb(factory, current_user, "policy-api")

    unconfigured = await knowledge_tests.get_evaluation_policy(kb.id, current_user, knowledge=knowledge)
    assert unconfigured == {"configured": False}

    document = await _seed_document(factory, tmp_path, kb.id, current_user.id, "policy-guide.txt")
    case = await knowledge.create_eval_case(actor_from_user(current_user), kb.id, question="retry?", expected_document_ids=[document.id], tags=[])

    saved = await knowledge_tests.put_evaluation_policy(
        kb.id,
        knowledge_tests.EvaluationPolicyRequest(
            profile_id="frozen",
            top_k=8,
            case_ids=[case["id"]],
            min_expected_hit_rate=0.5,
            min_recall_at_k=0.6,
            min_mrr_at_k=0.7,
        ),
        current_user,
        knowledge=knowledge,
    )
    assert saved["version"] == 1
    assert saved["case_ids"] == [case["id"]]

    reread = await knowledge_tests.get_evaluation_policy(kb.id, current_user, knowledge=knowledge)
    assert reread["version"] == 1
    assert reread["min_mrr_at_k"] == 0.7
    assert reread["case_ids"] == [case["id"]]

    with pytest.raises(HTTPException) as unknown_case:
        await knowledge_tests.put_evaluation_policy(
            kb.id,
            knowledge_tests.EvaluationPolicyRequest(
                profile_id="frozen",
                top_k=8,
                case_ids=[str(uuid.uuid4())],
                min_expected_hit_rate=0.5,
                min_recall_at_k=0.5,
                min_mrr_at_k=0.5,
            ),
            current_user,
            knowledge=knowledge,
        )
    assert unknown_case.value.status_code == 422
    assert unknown_case.value.detail["code"] == "invalid_evaluation"


@pytest.mark.asyncio
async def test_evaluation_endpoints_start_list_read_and_guard(env) -> None:
    factory, make_facade, current_user, audit_calls, tmp_path = env
    knowledge = make_facade()
    kb = await _seed_kb(factory, current_user, "evaluations-api")
    revision = await _publish_revision(factory, tmp_path, kb, current_user.id)
    document_id = next(iter(revision.provider_doc_map_json))
    case = await knowledge.create_eval_case(actor_from_user(current_user), kb.id, question="retry?", expected_document_ids=[document_id], tags=[])

    started = await knowledge_tests.create_evaluation(
        kb.id,
        knowledge_tests.EvaluationCreateRequest(revision_id=revision.id, top_k=8, case_ids=[case["id"]]),
        current_user,
        knowledge=knowledge,
    )
    assert started["status"] == "queued"
    assert audit_calls[-1] == ("owner", "knowledge_evaluation_started", "knowledge_base", kb.id, {"run_id": started["id"], "revision_id": revision.id})

    listed = await knowledge_tests.list_evaluations(kb.id, 0, 20, current_user, knowledge=knowledge)
    assert listed["total"] == 1
    detail = await knowledge_tests.get_evaluation(kb.id, started["id"], 0, 20, current_user, knowledge=knowledge)
    assert detail["id"] == started["id"]

    # A queued run cannot be retried: a client conflict, not a missing run.
    with pytest.raises(HTTPException) as conflict:
        await knowledge_tests.retry_evaluation(kb.id, started["id"], current_user, knowledge=knowledge)
    assert conflict.value.status_code == 409

    with pytest.raises(HTTPException) as guessed:
        await knowledge_tests.get_evaluation(kb.id, str(uuid.uuid4()), 0, 20, current_user, knowledge=knowledge)
    assert guessed.value.status_code == 404

    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)
    with pytest.raises(HTTPException) as hidden:
        await knowledge_tests.list_evaluations(kb.id, 0, 20, intruder, knowledge=knowledge)
    assert hidden.value.status_code == 404

    with pytest.raises(HTTPException) as invalid:
        await knowledge_tests.create_evaluation(
            kb.id,
            knowledge_tests.EvaluationCreateRequest(revision_id=revision.id, top_k=8, case_ids=[]),
            current_user,
            knowledge=knowledge,
        )
    assert invalid.value.status_code == 422
    assert invalid.value.detail["code"] == "invalid_evaluation"


@pytest.mark.asyncio
async def test_evaluation_comparison_endpoints_enqueue_and_read(env) -> None:
    factory, make_facade, current_user, audit_calls, tmp_path = env
    knowledge = make_facade()
    kb = await _seed_kb(factory, current_user, "comparisons-api")
    revision = await _publish_revision(factory, tmp_path, kb, current_user.id)
    document_id = next(iter(revision.provider_doc_map_json))
    case = await knowledge.create_eval_case(actor_from_user(current_user), kb.id, question="retry?", expected_document_ids=[document_id], tags=[])

    started = await knowledge_tests.create_evaluation_comparison(
        kb.id,
        knowledge_tests.EvaluationComparisonCreateRequest(
            left_revision_id=revision.id,
            left_profile_id="frozen",
            right_revision_id=revision.id,
            right_profile_id="configured",
            top_k=8,
            case_ids=[case["id"]],
        ),
        current_user,
        knowledge=knowledge,
    )
    assert started["status"] == "queued"
    assert started["left"]["status"] == "queued"
    assert audit_calls[-1][1] == "knowledge_evaluation_comparison_started"

    fetched = await knowledge_tests.get_evaluation_comparison(kb.id, started["id"], current_user, knowledge=knowledge)
    assert fetched["id"] == started["id"]
    assert fetched["left"]["id"] == started["left"]["id"]

    with pytest.raises(HTTPException) as guessed:
        await knowledge_tests.get_evaluation_comparison(kb.id, str(uuid.uuid4()), current_user, knowledge=knowledge)
    assert guessed.value.status_code == 404
