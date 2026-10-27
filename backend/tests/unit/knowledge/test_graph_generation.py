"""Controlled knowledge-graph generation for one frozen revision (#116).

The Server orchestrates every model call; a device never bulk-uploads its
library — material for a device-local revision is requested per document
through the frozen-identity dispatch (#113 idioms), re-validated
content-addressed on both ends, and only the requested document's text is
returned. Entities, relations, and document sources stay bound to the
KB/Revision identity and its permissions, another account cannot see them,
revision graphs are isolated from each other, and a failed document is a
structured per-document failure instead of a silent gap.
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
    GRAPH_MATERIAL_REJECTED,
    GRAPH_MODEL_OUTPUT_INVALID,
    KnowledgeGraphGenerationService,
    normalize_model_graph,
)
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeDocument, KnowledgeRevision
from app.agentplatform.resource_models import Resource, ResourceVersion
from app.agentplatform.resources.service import (
    ResourceAction,
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourcePermissionDenied,
    ResourceService,
)
from deerflow.persistence.base import Base

DEVICE_ID = "device-116"
GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()
POLICY = "乙组件的检修手册由检修班组维护。\n".encode()


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[tuple[AsyncSession, async_sessionmaker, Path]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-generation.db'}")
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


async def _register_local_revision(session: AsyncSession, kb: Resource, entries: list[dict], *, device_id: str = DEVICE_ID) -> KnowledgeRevision:
    actor = _actor(str(kb.owner_id))
    payload = await KnowledgeLocalImportService(session, actor).register_local_import(
        kb.id,
        documents=entries,
        device_id=device_id,
    )
    await session.commit()
    revision = await session.get(KnowledgeRevision, str(payload["id"]))
    assert revision is not None
    return revision


async def _seed_provider_revision(session: AsyncSession, kb: Resource, base_dir: Path) -> KnowledgeRevision:
    """One server-owned provider document with platform-stored material."""

    document_id = str(uuid.uuid4())
    storage_key = f"knowledge-documents/{kb.id}/{document_id}-policy.txt"
    destination = base_dir / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(POLICY)
    session.add(
        KnowledgeDocument(
            id=document_id,
            resource_id=kb.id,
            original_filename="policy.txt",
            title=None,
            size_bytes=len(POLICY),
            mime_type="text/plain",
            content_hash=hashlib.sha256(POLICY).hexdigest(),
            storage_key=storage_key,
            source="upload",
            metadata_json={},
            status="ready",
            created_by=kb.owner_id,
        )
    )
    entry = {
        "document_id": document_id,
        "content_hash": hashlib.sha256(POLICY).hexdigest(),
        "filename": "policy.txt",
        "size_bytes": len(POLICY),
        "mime_type": "text/plain",
        "metadata": {},
    }
    revision = KnowledgeRevision(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_no=1,
        status="published",
        manifest_hash=hashlib.sha256(str(entry).encode()).hexdigest(),
        manifest_json=[entry],
        provider_doc_map_json={document_id: "provider-doc-116"},
        document_count=1,
        provider_dataset_id="dataset-116",
        publish_attempt=1,
        created_by=kb.owner_id,
    )
    session.add(revision)
    await session.commit()
    return revision


class FakeConnection:
    def __init__(self, device_id: str, owner_id: str = "owner", capabilities: set[str] | None = None) -> None:
        self.device_id = device_id
        self.owner_id = owner_id
        self.tasks_allowed = True
        self.capabilities = capabilities if capabilities is not None else {"local.knowledge.search", "local.knowledge.material"}


class FakeBroker:
    """Device broker stand-in: records dispatched material tasks."""

    def __init__(self, *, documents: dict[str, str] | None = None, online: bool = True, owner_id: str = "owner", missing_reason: str = "content_drift") -> None:
        from app.device_control.broker import TaskStatus

        self._completed = TaskStatus.COMPLETED
        self._failed = TaskStatus.FAILED
        self.missing_reason = missing_reason
        self.connections: dict[str, FakeConnection] = {}
        if online:
            self.connections[DEVICE_ID] = FakeConnection(DEVICE_ID, owner_id=owner_id)
        self.documents = documents or {}
        self.dispatched: list[dict] = []

    async def send_task(self, *, device_id, operation, path, run_id, tool_call_id, payload_extra=None, **kwargs):
        assert operation == "local.knowledge.material"
        arguments = (payload_extra or {})["arguments"]
        self.dispatched.append(dict(device_id=device_id, owner_id=self.connections[device_id].owner_id if device_id in self.connections else None, arguments=arguments))
        requested = arguments["documents"]
        assert len(requested) == 1, "material dispatch must request exactly one document"
        entry = requested[0]
        text = self.documents.get(entry["document_id"])
        if text is None:
            # Device contract: a missing/drifted document is a COMPLETED
            # answer carrying a structured missing reason.
            result = {"document_id": entry["document_id"], "missing": True, "reason": self.missing_reason}
        else:
            result = {
                "document_id": entry["document_id"],
                "filename": entry["filename"],
                "content_hash": entry["content_hash"],
                "text": text,
            }
        return SimpleNamespace(
            task_id=str(uuid.uuid4()),
            status=self._completed,
            receipt=None,
            tool_call_id="",
            error_code=None,
            result=result,
        )

    def get_task(self, task_id):
        raise AssertionError("fake broker tasks settle immediately")


def _fixed_generator():
    """The server-driven model call stand-in: deterministic per material.

    The real implementation prompts a model; the fixed stand-in keeps the
    acceptance material checkable without model credentials. The
    representative relation comes from the fixed document content, not from
    this file.
    """

    async def generate(document_text: str) -> dict:
        if "乙组件" in document_text and "甲零件" in document_text:
            return {
                "entities": [
                    {"name": "甲零件", "type": "零件"},
                    {"name": "乙组件", "type": "组件"},
                ],
                "relations": [
                    {"source": "甲零件", "target": "乙组件", "relation": "属于"},
                ],
            }
        return {"entities": [{"name": "检修班组", "type": "组织"}], "relations": []}

    return generate


def _local_entries() -> list[dict]:
    return [
        {
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
            "size_bytes": len(GUIDE),
            "mime_type": "text/plain",
        }
    ]


async def _local_service(session, factory, *, broker=None, generator=None, user_id="owner") -> KnowledgeGraphGenerationService:
    return KnowledgeGraphGenerationService(
        session,
        _actor(user_id),
        generator=generator or _fixed_generator(),
        broker_factory=lambda: broker if broker is not None else FakeBroker(documents={}),
    )


# --- Slice A: server-orchestrated generation over authorized material only ----


@pytest.mark.anyio
async def test_generation_is_server_orchestrated_and_requests_one_document_at_a_time(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="graph-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)

    result = await service.generate(kb.id, revision.id)

    assert result["status"] == "completed"
    assert result["generated"] == 1 and result["failed"] == 0
    # One broker task per frozen document, carrying frozen identity fields
    # only: the device never uploads its library, it answers the request.
    assert len(broker.dispatched) == 1
    dispatched = broker.dispatched[0]
    assert dispatched["device_id"] == DEVICE_ID
    arguments = dispatched["arguments"]
    assert set(arguments) == {"revision_id", "manifest_hash", "documents"}
    assert arguments["revision_id"] == revision.id
    assert arguments["manifest_hash"] == revision.manifest_hash
    assert arguments["documents"] == [
        {
            "document_id": document_id,
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
        }
    ]


@pytest.mark.anyio
async def test_provider_material_comes_from_platform_storage_without_device_dispatch(store, monkeypatch) -> None:
    session, factory, tmp_path = store
    kb = await _seed_resource(session, slug="provider-kb")
    monkeypatch.setattr("app.agentplatform.knowledge.graph_generation.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    revision = await _seed_provider_revision(session, kb, tmp_path)

    def _fail_broker():
        raise AssertionError("provider material must never touch the device broker")

    service = KnowledgeGraphGenerationService(session, _actor(), generator=_fixed_generator(), broker_factory=_fail_broker)
    result = await service.generate(kb.id, revision.id)

    assert result["status"] == "completed"
    assert result["documents"][0]["filename"] == "policy.txt"


# --- Slice B: graph data is bound to KB/Revision and its permissions ----------


@pytest.mark.anyio
async def test_view_projects_entities_relations_and_sources_with_frozen_bindings(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="bound-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)
    await service.generate(kb.id, revision.id)

    viewer = KnowledgeGraphGenerationService(session, _actor(), generator=_fixed_generator(), broker_factory=lambda: FakeBroker())
    view = await viewer.view(kb.id, revision.id)

    assert view["knowledge_base_id"] == kb.id
    assert view["revision_id"] == revision.id
    assert view["revision_no"] == revision.revision_no
    assert view["manifest_hash"] == revision.manifest_hash
    assert view["status"] == "completed"
    # The representative relation is verifiable against the fixed material.
    assert {"name": "甲零件", "type": "零件", "document_id": document_id, "filename": "guide.txt"} in view["entities"]
    assert {"name": "乙组件", "type": "组件", "document_id": document_id, "filename": "guide.txt"} in view["entities"]
    assert {
        "source": "甲零件",
        "target": "乙组件",
        "relation": "属于",
        "document_id": document_id,
        "filename": "guide.txt",
    } in view["relations"]
    assert view["sources"] == [
        {
            "document_id": document_id,
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
            "status": "completed",
            "error_code": None,
        }
    ]


@pytest.mark.anyio
async def test_graphs_are_isolated_between_revisions(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="isolation-kb")
    first = await _register_local_revision(session, kb, _local_entries())
    second_entries = [
        {
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(POLICY).hexdigest(),
            "size_bytes": len(POLICY),
            "mime_type": "text/plain",
        }
    ]
    second = await _register_local_revision(session, kb, second_entries)

    async def give(document_text: str) -> dict:
        return {"entities": [{"name": "孤立实体", "type": "测试"}], "relations": []}

    first_generation = KnowledgeGraphGenerationService(
        session,
        _actor(),
        generator=give,
        broker_factory=lambda: FakeBroker(documents={first.manifest_json[0]["document_id"]: GUIDE.decode()}),
    )
    await first_generation.generate(kb.id, first.id)
    second_generation = KnowledgeGraphGenerationService(
        session,
        _actor(),
        generator=give,
        broker_factory=lambda: FakeBroker(documents={second.manifest_json[0]["document_id"]: POLICY.decode()}),
    )
    await second_generation.generate(kb.id, second.id)

    viewer = KnowledgeGraphGenerationService(session, _actor(), generator=give, broker_factory=lambda: FakeBroker())
    first_view = await viewer.view(kb.id, first.id)
    second_view = await viewer.view(kb.id, second.id)
    assert [entity["name"] for entity in first_view["entities"]] == ["孤立实体"]
    assert [entity["name"] for entity in second_view["entities"]] == ["孤立实体"]
    # Same entity label in both graphs, but bound to different frozen
    # revisions and documents: no cross-revision drift.
    assert first_view["revision_id"] != second_view["revision_id"]
    assert first_view["manifest_hash"] != second_view["manifest_hash"]
    assert first_view["entities"][0]["document_id"] == first.manifest_json[0]["document_id"]
    assert second_view["entities"][0]["document_id"] == second.manifest_json[0]["document_id"]


@pytest.mark.anyio
async def test_other_account_cannot_view_or_generate(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="private-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    service = await _local_service(session, factory, broker=FakeBroker(documents={document_id: GUIDE.decode()}))
    await service.generate(kb.id, revision.id)
    await session.commit()

    outsider = KnowledgeGraphGenerationService(session, _actor("stranger"), generator=_fixed_generator(), broker_factory=lambda: FakeBroker())
    with pytest.raises(ResourceNotFound):
        await outsider.view(kb.id, revision.id)
    with pytest.raises(ResourceNotFound):
        await outsider.generate(kb.id, revision.id)


def _department_reader() -> ResourceActor:
    return ResourceActor(
        user_id="reader",
        department_id="dept-116",
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


@pytest.mark.anyio
async def test_department_visibility_can_view_but_not_generate(store) -> None:
    """Department-visible KB: members read the graph; generation stays owner-only."""

    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="shared-kb")
    kb.visibility = "department"
    kb.scope_department_id = "dept-116"
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    service = await _local_service(session, factory, broker=FakeBroker(documents={document_id: GUIDE.decode()}))
    await service.generate(kb.id, revision.id)
    await session.commit()

    reader_service = KnowledgeGraphGenerationService(session, _department_reader(), generator=_fixed_generator(), broker_factory=lambda: FakeBroker())
    view = await reader_service.view(kb.id, revision.id)
    assert view["status"] == "completed"
    with pytest.raises(ResourcePermissionDenied):
        await reader_service.generate(kb.id, revision.id)


@pytest.mark.anyio
async def test_view_before_generation_reports_not_generated(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="fresh-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory)

    view = await service.view(kb.id, revision.id)
    assert view["status"] == "not_generated"
    assert view["entities"] == [] and view["relations"] == []
    # The frozen documents stay listed: the entry shows what a generation
    # would cover, and none of it pretends to be generated.
    assert [row["status"] for row in view["documents"]] == ["not_generated"]
    assert view["sources"] == [
        {
            "document_id": revision.manifest_json[0]["document_id"],
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
            "status": "not_generated",
            "error_code": None,
        }
    ]


# --- Slice C: honest failures -------------------------------------------------


@pytest.mark.anyio
async def test_device_material_drift_is_a_structured_failure_and_successes_survive(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="partial-kb")
    entries = _local_entries() + [
        {
            "filename": "policy.txt",
            "content_hash": hashlib.sha256(POLICY).hexdigest(),
            "size_bytes": len(POLICY),
            "mime_type": "text/plain",
        }
    ]
    revision = await _register_local_revision(session, kb, entries)
    document_ids = {entry["filename"]: entry["document_id"] for entry in revision.manifest_json}
    # Only the first document still matches its frozen digest on the device.
    broker = FakeBroker(documents={document_ids["guide.txt"]: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)

    result = await service.generate(kb.id, revision.id)

    assert result["status"] == "partial"
    assert result["generated"] == 1 and result["failed"] == 1
    statuses = {row["filename"]: row for row in result["documents"]}
    assert statuses["guide.txt"]["status"] == "completed"
    assert statuses["policy.txt"]["status"] == "failed"
    assert statuses["policy.txt"]["error_code"] == GRAPH_CONTENT_DRIFTED

    view = await service.view(kb.id, revision.id)
    assert view["status"] == "partial"
    # The successful source stays verifiable; the failed one names its cause.
    assert {source["filename"]: source["status"] for source in view["sources"]} == {"guide.txt": "completed", "policy.txt": "failed"}
    assert all(entity["document_id"] == document_ids["guide.txt"] for entity in view["entities"])


@pytest.mark.anyio
async def test_device_offline_is_a_structured_failure(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="offline-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory, broker=FakeBroker(online=False))

    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["documents"][0]["error_code"] == GRAPH_DEVICE_UNAVAILABLE


@pytest.mark.anyio
async def test_returned_material_must_match_the_frozen_digest(store) -> None:
    """A buggy or compromised device cannot inject substitute material."""

    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="reject-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: "被替换的内容".encode().decode()})
    service = await _local_service(session, factory, broker=broker)

    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["documents"][0]["error_code"] == GRAPH_MATERIAL_REJECTED


@pytest.mark.anyio
async def test_all_failures_report_failed_not_completed(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="allfail-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory, broker=FakeBroker(documents={}))

    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"


@pytest.mark.anyio
async def test_invalid_model_output_is_a_document_failure(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="model-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]

    async def bad_model(document_text: str) -> dict:
        return {"unrelated": True}

    service = await _local_service(
        session,
        factory,
        broker=FakeBroker(documents={document_id: GUIDE.decode()}),
        generator=bad_model,
    )
    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["documents"][0]["error_code"] == GRAPH_MODEL_OUTPUT_INVALID


@pytest.mark.anyio
async def test_empty_revision_is_refused(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="empty-kb")
    row = KnowledgeRevision(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_no=1,
        status="draft",
        manifest_hash=hashlib.sha256(b"empty").hexdigest(),
        manifest_json=[],
        provider_doc_map_json={},
        document_count=0,
        created_by=kb.owner_id,
    )
    session.add(row)
    await session.commit()
    service = await _local_service(session, factory)
    with pytest.raises(ResourceConflict):
        await service.generate(kb.id, row.id)


@pytest.mark.anyio
async def test_regeneration_replaces_previous_artifacts(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="regen-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)
    first = await service.generate(kb.id, revision.id)
    second = await service.generate(kb.id, revision.id)
    assert first["status"] == second["status"] == "completed"
    view = await service.view(kb.id, revision.id)
    assert len(view["documents"]) == 1
    assert len(view["entities"]) == 2 and len(view["relations"]) == 1


@pytest.mark.anyio
async def test_revision_of_another_kb_is_invisible(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="kb-a")
    other = await _seed_resource(session, slug="kb-b")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory)
    with pytest.raises(ResourceNotFound):
        await service.generate(other.id, revision.id)
    with pytest.raises(ResourceNotFound):
        await service.view(other.id, revision.id)


# --- Slice D: model output normalization contract ------------------------------


def test_normalize_model_graph_accepts_and_binds_shape() -> None:
    normalized = normalize_model_graph(
        {
            "entities": [
                {"name": "甲零件", "type": "零件"},
                {"name": "甲零件", "type": "零件"},  # duplicate dropped
            ],
            "relations": [
                {"source": "甲零件", "target": "乙组件", "relation": "属于"},  # unknown target dropped
                {"source": "甲零件", "target": "甲零件", "relation": "包含"},
            ],
        }
    )
    assert normalized["entities"] == [{"name": "甲零件", "type": "零件"}]
    assert normalized["relations"] == [{"source": "甲零件", "target": "甲零件", "relation": "包含"}]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "entities",
        [],
        {},
        {"entities": "nope", "relations": []},
        {"entities": [{"type": "零件"}], "relations": []},
        {"entities": [{"name": ""}], "relations": []},
        {"entities": [{"name": "甲"}], "relations": [{"source": "甲", "relation": "属于"}]},
        {"entities": [{"name": "甲"}], "relations": [{"source": "甲", "target": "甲"}]},
        {"entities": [{"name": "甲"}], "relations": [{"source": "甲", "target": "甲", "relation": ""}]},
    ],
)
def test_normalize_model_graph_rejects_malformed_output(raw) -> None:
    with pytest.raises(ValueError):
        normalize_model_graph(raw)


def test_normalize_model_graph_enforces_bounds() -> None:
    entities = [{"name": f"实体{index}", "type": "测试"} for index in range(500)]
    normalized = normalize_model_graph({"entities": entities, "relations": []})
    assert len(normalized["entities"]) == 200
