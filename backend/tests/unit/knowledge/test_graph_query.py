"""Scoped graph QA and relation retrieval inside one frozen revision (#117).

The query/ask surface rides the same resource-visibility authorization as
knowledge retrieval itself: an invisible KB reads as not-found no matter
what labels a caller sends, and the selected document scope is validated
against the frozen manifest instead of trusted. Entity and relation results
carry their document sources, and an ask whose selected material is missing,
drifted, or partially failed refuses with a structured record — the model is
never invoked over a gapped scope, so no unfounded conclusion can form.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.graph_generation import (
    GRAPH_CONTENT_DRIFTED,
    GRAPH_DEVICE_UNAVAILABLE,
    GRAPH_MODEL_OUTPUT_INVALID,
    GRAPH_MODEL_UNAVAILABLE,
    KnowledgeGraphGenerationService,
)
from app.agentplatform.knowledge.graph_query import (
    MAX_SCOPED_ANSWER_CHARS,
    KnowledgeGraphQueryService,
)
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeRevision
from app.agentplatform.resource_models import Resource, ResourceVersion
from app.agentplatform.resources.service import (
    ResourceAction,
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourceService,
)
from deerflow.persistence.base import Base

DEVICE_ID = "device-117"
GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()
POLICY = "乙组件的检修手册由检修班组维护。\n".encode()


def _actor(user_id: str = "owner", department_id: str | None = None) -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=department_id,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[tuple[AsyncSession, async_sessionmaker, Path]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-query.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory, tmp_path
    await engine.dispose()


async def _seed_resource(session: AsyncSession, *, slug: str, owner_id: str = "owner") -> Resource:
    resource = await ResourceService(session, _actor(owner_id)).create_resource(
        resource_type="knowledge_base",
        slug=slug,
        display_name=slug,
        storage_kind="database",
    )
    resource.latest_version = 1
    resource.draft_revision = 1
    session.add(
        ResourceVersion(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            version=1,
            content_hash=hashlib.sha256(slug.encode()).hexdigest(),
            storage_key=f"knowledge_bases/{resource.id}",
            scan_result={},
            content={"description": slug},
            created_by=resource.owner_id,
        )
    )
    return resource


async def _register_local_revision(session: AsyncSession, kb: Resource, entries: list[dict]) -> KnowledgeRevision:
    payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
        kb.id,
        documents=entries,
        device_id=DEVICE_ID,
    )
    await session.commit()
    revision = await session.get(KnowledgeRevision, str(payload["id"]))
    assert revision is not None
    return revision


def _entries(*contents: bytes) -> list[dict]:
    names = ["guide.txt", "policy.txt"]
    return [
        {
            "filename": names[index],
            "content_hash": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "mime_type": "text/plain",
        }
        for index, content in enumerate(contents)
    ]


def _one(filename: str, content: bytes) -> list[dict]:
    return [
        {
            "filename": filename,
            "content_hash": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "mime_type": "text/plain",
        }
    ]


class FakeConnection:
    def __init__(self, owner_id: str = "owner") -> None:
        self.device_id = DEVICE_ID
        self.owner_id = owner_id
        self.tasks_allowed = True
        self.capabilities = {"local.knowledge.search", "local.knowledge.material"}


class FakeBroker:
    """Device broker stand-in: serves frozen documents by document_id."""

    def __init__(self, *, documents: dict[str, str] | None = None, online: bool = True) -> None:
        from app.device_control.broker import TaskStatus

        self._completed = TaskStatus.COMPLETED
        self.documents = documents or {}
        self.connections: dict[str, FakeConnection] = {DEVICE_ID: FakeConnection()} if online else {}

    async def send_task(self, *, payload_extra=None, **kwargs):
        entry = payload_extra["arguments"]["documents"][0]
        text = self.documents.get(entry["document_id"])
        if text is None:
            result = {"document_id": entry["document_id"], "missing": True, "reason": "content_drift"}
        else:
            result = {
                "document_id": entry["document_id"],
                "filename": entry["filename"],
                "content_hash": entry["content_hash"],
                "text": text,
            }
        return SimpleNamespace(task_id=str(uuid.uuid4()), status=self._completed, receipt=None, tool_call_id="", error_code=None, result=result)

    def get_task(self, task_id):
        raise AssertionError("fake broker tasks settle immediately")


def _fixed_generator():
    async def generate(document_text: str) -> dict:
        if "乙组件" in document_text and "甲零件" in document_text:
            return {
                "entities": [
                    {"name": "甲零件", "type": "零件"},
                    {"name": "乙组件", "type": "组件"},
                ],
                "relations": [{"source": "甲零件", "target": "乙组件", "relation": "属于"}],
            }
        return {"entities": [{"name": "检修班组", "type": "组织"}], "relations": []}

    return generate


def _fixed_answerer(calls: list | None = None):
    async def answer(question: str, documents: list[tuple[str, str, str]]) -> str:
        if calls is not None:
            calls.append({"question": question, "documents": [(name, digest) for name, digest, _text in documents]})
        return f"依据 {('、'.join(name for name, _digest, _text in documents))}：甲零件属于乙组件。"

    return answer


async def _generate(session: AsyncSession, kb: Resource, revision: KnowledgeRevision, *, broker: FakeBroker) -> None:
    service = KnowledgeGraphGenerationService(
        session,
        _actor(str(kb.owner_id)),
        generator=_fixed_generator(),
        broker_factory=lambda: broker,
    )
    await service.generate(kb.id, revision.id)
    await session.commit()


def _query_service(session: AsyncSession, *, answerer=None, broker: FakeBroker | None = None) -> KnowledgeGraphQueryService:
    return KnowledgeGraphQueryService(
        session,
        _actor(),
        answerer=answerer or _fixed_answerer(),
        broker_factory=lambda: broker if broker is not None else FakeBroker(),
    )


def _ids_by_name(revision: KnowledgeRevision) -> dict[str, str]:
    return {str(entry.get("filename")): str(entry["document_id"]) for entry in revision.manifest_json}


# --- Scope narrowing and sourcing (T117-01) ----------------------------------


@pytest.mark.anyio
async def test_query_narrows_to_the_selected_documents_and_expands_with_the_scope(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="narrow-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE, POLICY))
    ids = _ids_by_name(revision)
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode(), ids["policy.txt"]: POLICY.decode()}))

    narrow = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"]])
    assert [entity["name"] for entity in narrow["entities"]] == ["甲零件", "乙组件"]
    assert [relation["relation"] for relation in narrow["relations"]] == ["属于"]
    assert [row["document_id"] for row in narrow["scope"]] == [ids["guide.txt"]]

    widened = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"], ids["policy.txt"]])
    assert sorted(entity["name"] for entity in widened["entities"]) == ["乙组件", "检修班组", "甲零件"]
    assert [row["document_id"] for row in widened["scope"]] == [ids["guide.txt"], ids["policy.txt"]]


@pytest.mark.anyio
async def test_query_results_and_scope_carry_frozen_document_sources(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="sourced-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE, POLICY))
    ids = _ids_by_name(revision)
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode(), ids["policy.txt"]: POLICY.decode()}))

    result = await _query_service(session).query(kb.id, revision.id, [ids["policy.txt"]], "检修班组")

    assert result["knowledge_base_id"] == kb.id
    assert result["revision_id"] == revision.id
    assert result["manifest_hash"] == revision.manifest_hash
    policy_hash = hashlib.sha256(POLICY).hexdigest()
    # The scope echoes exactly the selected documents, with their frozen digests.
    assert result["scope"] == [
        {"document_id": ids["policy.txt"], "filename": "policy.txt", "content_hash": policy_hash, "status": "completed", "error_code": None},
    ]
    assert result["entities"] == [{"name": "检修班组", "type": "组织", "document_id": ids["policy.txt"], "filename": "policy.txt", "content_hash": policy_hash}]
    assert result["relations"] == []


@pytest.mark.anyio
async def test_query_text_filters_across_names_types_and_relation_endpoints(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="filter-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE, POLICY))
    ids = _ids_by_name(revision)
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode(), ids["policy.txt"]: POLICY.decode()}))

    by_relation = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"]], "属于")
    assert [relation["relation"] for relation in by_relation["relations"]] == ["属于"]
    assert by_relation["entities"] == []

    by_endpoint = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"]], "甲零件")
    assert [entity["name"] for entity in by_endpoint["entities"]] == ["甲零件"]
    assert [relation["source"] for relation in by_endpoint["relations"]] == ["甲零件"]

    everything = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"], ids["policy.txt"]], "")
    assert len(everything["entities"]) == 3


# --- Permission parity with knowledge retrieval (T117-02) ---------------------


@pytest.mark.anyio
async def test_invisible_kb_reads_as_not_found_for_query_and_ask(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="hidden-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)

    stranger = KnowledgeGraphQueryService(session, _actor("stranger"), answerer=_fixed_answerer(), broker_factory=lambda: FakeBroker())
    with pytest.raises(ResourceNotFound):
        await stranger.query(kb.id, revision.id, [ids["guide.txt"]])
    with pytest.raises(ResourceNotFound):
        await stranger.ask(kb.id, revision.id, [ids["guide.txt"]], "乙组件由什么构成？")


@pytest.mark.anyio
async def test_department_member_with_visibility_reads_like_retrieval(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="department-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()}))

    resource = await session.get(Resource, kb.id)
    resource.visibility = "department"
    resource.scope_department_id = "dept-117"
    await session.commit()

    member = KnowledgeGraphQueryService(
        session,
        _actor("colleague", department_id="dept-117"),
        answerer=_fixed_answerer(),
        broker_factory=lambda: FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()}),
    )
    view = await member.query(kb.id, revision.id, [ids["guide.txt"]])
    assert [entity["name"] for entity in view["entities"]] == ["甲零件", "乙组件"]
    # Reading the stored graph is read parity; but the device-local material
    # is owner-scoped like every local leg: the member's ask honestly reports
    # the unavailable material instead of answering over it.
    answered = await member.ask(kb.id, revision.id, [ids["guide.txt"]], "乙组件由什么构成？")
    assert answered["answer_available"] is False
    assert answered["status"] == "failed"
    assert answered["scope"][0]["error_code"] == GRAPH_DEVICE_UNAVAILABLE


# --- Scope validation (T117-02) -----------------------------------------------


@pytest.mark.anyio
async def test_documents_outside_the_frozen_revision_are_refused(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="scope-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)
    other = await _register_local_revision(session, kb, _one("policy.txt", POLICY))
    other_ids = _ids_by_name(other)

    service = _query_service(session)
    with pytest.raises(ResourceConflict):
        await service.query(kb.id, revision.id, [str(uuid.uuid4())])
    # A real document of the same KB but frozen into another revision is
    # still outside this revision's scope.
    with pytest.raises(ResourceConflict):
        await service.query(kb.id, revision.id, [other_ids["policy.txt"]])
    with pytest.raises(ResourceConflict):
        await service.ask(kb.id, revision.id, [ids["guide.txt"], other_ids["policy.txt"]], "问题")
    with pytest.raises(ResourceConflict):
        await service.query(kb.id, revision.id, [])
    with pytest.raises(ResourceConflict):
        await service.ask(kb.id, revision.id, [ids["guide.txt"]], "")


@pytest.mark.anyio
async def test_revision_without_frozen_documents_is_a_conflict(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="empty-kb")
    empty = KnowledgeRevision(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_no=1,
        status="published",
        manifest_hash="e" * 64,
        manifest_json=[],
        provider_doc_map_json={},
        document_count=0,
        created_by=kb.owner_id,
    )
    session.add(empty)
    await session.commit()
    with pytest.raises(ResourceConflict):
        await _query_service(session).query(kb.id, empty.id, [str(uuid.uuid4())])


# --- Revision isolation and version change (T117-04) --------------------------


@pytest.mark.anyio
async def test_queries_stay_bound_to_the_frozen_revision_after_a_new_version(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="versions-kb")
    first = await _register_local_revision(session, kb, _entries(GUIDE))
    first_ids = _ids_by_name(first)
    await _generate(session, kb, first, broker=FakeBroker(documents={first_ids["guide.txt"]: GUIDE.decode()}))

    second = await _register_local_revision(session, kb, _one("policy.txt", POLICY))
    second_ids = _ids_by_name(second)
    await _generate(session, kb, second, broker=FakeBroker(documents={second_ids["policy.txt"]: POLICY.decode()}))

    before = await _query_service(session).query(kb.id, first.id, [first_ids["guide.txt"]])
    after = await _query_service(session).query(kb.id, first.id, [first_ids["guide.txt"]])

    assert before == after
    assert after["revision_id"] == first.id and after["revision_no"] == first.revision_no
    assert after["manifest_hash"] == first.manifest_hash != second.manifest_hash
    assert [entity["name"] for entity in after["entities"]] == ["甲零件", "乙组件"]
    # The newer revision's graph never bleeds into the original scope.
    with pytest.raises(ResourceConflict):
        await _query_service(session).query(kb.id, first.id, [second_ids["policy.txt"]])


# --- Scoped QA (T117-01/T117-03) ----------------------------------------------


@pytest.mark.anyio
async def test_ask_answers_from_exactly_the_selected_material_with_sources(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="ask-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE, POLICY))
    ids = _ids_by_name(revision)
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode(), ids["policy.txt"]: POLICY.decode()}))

    calls: list = []
    service = _query_service(session, answerer=_fixed_answerer(calls), broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()}))
    result = await service.ask(kb.id, revision.id, [ids["guide.txt"]], "乙组件由什么构成？")

    assert result["answer_available"] is True
    assert result["answer"] == "依据 guide.txt：甲零件属于乙组件。"
    assert result["status"] == "completed"
    assert result["error_code"] is None
    # The model saw exactly the selected frozen document, nothing else.
    assert calls == [{"question": "乙组件由什么构成？", "documents": [("guide.txt", hashlib.sha256(GUIDE).hexdigest())]}]
    assert [row["document_id"] for row in result["scope"]] == [ids["guide.txt"]]


@pytest.mark.anyio
async def test_ask_refuses_to_answer_when_selected_material_is_partially_missing(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="partial-ask-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE, POLICY))
    ids = _ids_by_name(revision)
    # The device only still holds guide.txt at its frozen digest.
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()}))

    calls: list = []
    service = _query_service(session, answerer=_fixed_answerer(calls), broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()}))
    result = await service.ask(kb.id, revision.id, [ids["guide.txt"], ids["policy.txt"]], "检修手册由谁维护？")

    # A gapped scope never reaches the model: no unfounded conclusion forms.
    assert calls == []
    assert result["answer"] is None
    assert result["answer_available"] is False
    assert result["status"] == "partial"
    scope = {row["filename"]: row for row in result["scope"]}
    assert scope["policy.txt"]["status"] == "failed"
    assert scope["policy.txt"]["error_code"] == GRAPH_CONTENT_DRIFTED
    assert scope["guide.txt"]["status"] == "completed"


@pytest.mark.anyio
async def test_ask_reports_a_fully_unavailable_device_as_a_structured_failure(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="offline-ask-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)

    service = _query_service(session, broker=FakeBroker(online=False))
    result = await service.ask(kb.id, revision.id, [ids["guide.txt"]], "问题")

    assert result["answer_available"] is False
    assert result["status"] == "failed"
    assert result["scope"][0]["error_code"] == GRAPH_DEVICE_UNAVAILABLE


@pytest.mark.anyio
async def test_ask_model_failures_are_structured_instead_of_fabricated(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="model-fail-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)

    async def invalid(question: str, documents: list) -> str:
        raise ValueError("model output was not an answer")

    broker = FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()})
    result = await _query_service(session, answerer=invalid, broker=broker).ask(kb.id, revision.id, [ids["guide.txt"]], "问题")
    assert result["answer"] is None and result["answer_available"] is False
    assert result["status"] == "failed" and result["error_code"] == GRAPH_MODEL_OUTPUT_INVALID

    async def broken(question: str, documents: list) -> str:
        raise RuntimeError("provider down")

    result = await _query_service(session, answerer=broken, broker=broker).ask(kb.id, revision.id, [ids["guide.txt"]], "问题")
    assert result["answer"] is None and result["answer_available"] is False
    assert result["status"] == "failed" and result["error_code"] == GRAPH_MODEL_UNAVAILABLE


@pytest.mark.anyio
async def test_ask_overlong_answer_is_rejected_rather_than_truncated(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="overrun-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)

    async def overrun(question: str, documents: list) -> str:
        return "长" * (MAX_SCOPED_ANSWER_CHARS + 1)

    result = await _query_service(session, answerer=overrun, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()})).ask(kb.id, revision.id, [ids["guide.txt"]], "问题")
    assert result["answer"] is None
    assert result["error_code"] == GRAPH_MODEL_OUTPUT_INVALID


# --- Un-generated graphs read honestly ----------------------------------------


@pytest.mark.anyio
async def test_query_before_generation_reports_not_generated_without_rows(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="pending-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE))
    ids = _ids_by_name(revision)

    result = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"]])

    assert result["status"] == "not_generated"
    assert result["entities"] == [] and result["relations"] == []
    assert result["scope"][0]["status"] == "not_generated"


@pytest.mark.anyio
async def test_query_over_a_partial_graph_skips_failed_documents(store) -> None:
    session, _factory, _tmp = store
    kb = await _seed_resource(session, slug="partial-graph-kb")
    revision = await _register_local_revision(session, kb, _entries(GUIDE, POLICY))
    ids = _ids_by_name(revision)
    await _generate(session, kb, revision, broker=FakeBroker(documents={ids["guide.txt"]: GUIDE.decode()}))

    result = await _query_service(session).query(kb.id, revision.id, [ids["guide.txt"], ids["policy.txt"]])

    assert result["status"] == "partial"
    assert [entity["name"] for entity in result["entities"]] == ["甲零件", "乙组件"]
    scope = {row["filename"]: row for row in result["scope"]}
    assert scope["policy.txt"]["status"] == "failed"
    assert scope["policy.txt"]["error_code"] == GRAPH_CONTENT_DRIFTED
