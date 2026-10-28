"""Frozen local-knowledge retrieval for Desktop device KBs (#113).

A locally imported KnowledgeBase revision (#112) never reaches a provider.
Runs may still search it when the frozen closure anchors it, the run caller
owns the KB, and the manifest names exactly one importing device: the scope
then binds the KB to a device-local dataset token, retrieval is re-validated
on that device through the unique Runtime, and every result flows through the
existing retrieval-receipt pipeline without device paths or provider IDs.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from agentplatform_extension.evidence import (
    AuthorizationContext,
    RunEvidenceBinding,
    bind_run_evidence,
    current_run_evidence,
)
from agentplatform_extension.knowledge.runtime_adapter import KnowledgeAccessDenied, KnowledgeRuntimeAdapter
from agentplatform_extension.knowledge.scope import KnowledgeScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeRevision
from app.agentplatform.resource_models import Resource, ResourceDependency, ResourceVersion
from app.agentplatform.resources.service import (
    ResourceAction,
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourceService,
)
from app.gateway.canonical_agent_run_preparation import build_frozen_knowledge_bindings
from deerflow.persistence.base import Base

DEVICE_ID = "device-113"
GUIDE = b"frozen retrieval answer: the launch code is ALPHA-7\n"


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[tuple[AsyncSession, async_sessionmaker]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'local-retrieval.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


async def _seed_resource(session: AsyncSession, *, resource_type: str, slug: str) -> Resource:
    resource = await ResourceService(session, _actor()).create_resource(
        resource_type=resource_type,
        slug=slug,
        display_name=slug,
        storage_kind="database" if resource_type == "knowledge_base" else "filesystem",
    )
    resource.latest_version = 1
    resource.draft_revision = 1
    session.add(
        ResourceVersion(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            version=1,
            content_hash=hashlib.sha256(slug.encode()).hexdigest(),
            storage_key=f"{resource_type}s/{resource.id}",
            scan_result={},
            content={"description": slug},
            created_by=resource.owner_id,
        )
    )
    return resource


async def _seed_agent_with_kb(session: AsyncSession, *, mode: str = "live", slug: str = "kb-local") -> tuple[Resource, Resource]:
    agent = await _seed_resource(session, resource_type="agent", slug="helper")
    kb = await _seed_resource(session, resource_type="knowledge_base", slug=slug)
    options: dict = {"dependency_mode": mode}
    if mode == "pinned":
        options["revision_id"] = "pending"
    session.add(ResourceDependency(id=str(uuid.uuid4()), source_resource_id=agent.id, target_resource_id=kb.id, **options))
    await session.commit()
    return agent, kb


async def _register_local_revision(session: AsyncSession, kb: Resource, *, device_id: str = DEVICE_ID) -> KnowledgeRevision:
    """Register one local import through the real #112 service."""
    actor = _actor(str(kb.owner_id))
    service = KnowledgeLocalImportService(session, actor)
    payload = await service.register_local_import(
        kb.id,
        documents=[
            {
                "filename": "guide.txt",
                "content_hash": hashlib.sha256(GUIDE).hexdigest(),
                "size_bytes": len(GUIDE),
                "mime_type": "text/plain",
            }
        ],
        device_id=device_id,
    )
    await session.commit()
    revision = await session.get(KnowledgeRevision, str(payload["id"]))
    assert revision is not None
    return revision


async def _set_dependency_revision(session: AsyncSession, agent: Resource, kb: Resource, revision_id: str) -> None:
    edge = (
        await session.execute(
            select(ResourceDependency).where(
                ResourceDependency.source_resource_id == agent.id,
                ResourceDependency.target_resource_id == kb.id,
            )
        )
    ).scalar_one()
    edge.dependency_mode = "pinned"
    edge.revision_id = revision_id
    await session.commit()


# --- Slice A: the frozen revision anchor -------------------------------------


@pytest.mark.asyncio
async def test_activated_local_import_resolves_into_frozen_closure(store) -> None:
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    revision = await _register_local_revision(session, kb)

    await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).activate_local_revision(kb.id, revision.id)
    await session.commit()

    closure = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    kb_item = next(item for item in closure if item.resource.type == "knowledge_base")
    assert kb_item.knowledge_revision is not None and kb_item.knowledge_revision.id == revision.id

    snapshots = await ResourceService(session, _actor()).create_run_snapshot("run-113", agent.id, closure=closure)
    await session.commit()
    snapshot = next(item for item in snapshots if item.resource_id == kb.id)
    assert snapshot.knowledge_revision_id == revision.id
    assert snapshot.knowledge_revision_no == 1
    assert snapshot.manifest_hash == revision.manifest_hash
    # A device-local KB has no provider dataset: nothing pretend-published.
    assert snapshot.provider_dataset_id is None


@pytest.mark.asyncio
async def test_unactivated_local_import_rejects_the_run(store) -> None:
    """No frozen anchor means no run: draft content is never impersonated."""
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    await _register_local_revision(session, kb)

    with pytest.raises(ResourceConflict):
        await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)


@pytest.mark.asyncio
async def test_pinned_local_import_stays_fixed_when_activation_moves(store) -> None:
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session, mode="pinned")
    revision_one = await _register_local_revision(session, kb)
    await _set_dependency_revision(session, agent, kb, revision_one.id)
    revision_two = await _register_local_revision(session, kb)

    await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).activate_local_revision(kb.id, revision_two.id)
    await session.commit()

    closure = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    kb_item = next(item for item in closure if item.resource.type == "knowledge_base")
    assert kb_item.knowledge_revision is not None and kb_item.knowledge_revision.id == revision_one.id


@pytest.mark.asyncio
async def test_live_local_import_moves_only_new_runs(store) -> None:
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    revision_one = await _register_local_revision(session, kb)
    service = KnowledgeLocalImportService(session, _actor(str(kb.owner_id)))
    await service.activate_local_revision(kb.id, revision_one.id)
    await session.commit()

    closure_a = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    await ResourceService(session, _actor()).create_run_snapshot("run-a", agent.id, closure=closure_a)
    await session.commit()

    revision_two = await _register_local_revision(session, kb)
    await service.activate_local_revision(kb.id, revision_two.id)
    await session.commit()

    closure_b = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    kb_item_b = next(item for item in closure_b if item.resource.type == "knowledge_base")
    assert kb_item_b.knowledge_revision is not None and kb_item_b.knowledge_revision.id == revision_two.id

    from app.agentplatform.resource_models import RunResourceSnapshot

    run_a = (await session.execute(select(RunResourceSnapshot).where(RunResourceSnapshot.run_id == "run-a", RunResourceSnapshot.resource_id == kb.id))).scalar_one()
    assert run_a.knowledge_revision_id == revision_one.id


@pytest.mark.asyncio
async def test_activation_refuses_non_local_revisions(store) -> None:
    """Only device-local imports can anchor a KB without provider content."""
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    from datetime import UTC, datetime

    provider_revision = KnowledgeRevision(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_no=1,
        status="draft",
        manifest_hash=hashlib.sha256(b"provider").hexdigest(),
        manifest_json=[{"document_id": "doc-1", "content_hash": hashlib.sha256(b"provider").hexdigest(), "filename": "guide.txt", "size_bytes": 8, "mime_type": "text/plain", "metadata": {}}],
        provider_doc_map_json={"doc-1": "provider-doc-1"},
        document_count=1,
        provider_dataset_id="ds-1",
        created_by=kb.owner_id,
    )
    session.add(provider_revision)
    await session.commit()

    with pytest.raises(ResourceConflict):
        await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).activate_local_revision(kb.id, provider_revision.id)
    del agent, datetime, UTC


@pytest.mark.asyncio
async def test_activation_requires_the_kb_owner(store) -> None:
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    revision = await _register_local_revision(session, kb)

    other = ResourceActor(
        user_id="someone-else",
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )
    # Governance idiom: another user's private KB reads as not-found, so the
    # activation attempt cannot even confirm the resource exists.
    with pytest.raises(ResourceNotFound):
        await KnowledgeLocalImportService(session, other).activate_local_revision(kb.id, revision.id)
    del agent


# --- Slice B: effective scope bindings for device-local datasets --------------


def _resolved(closure_item: object) -> tuple[dict, dict, dict, dict]:
    bindings, documents, profiles, metadata = build_frozen_knowledge_bindings([closure_item], caller_user_id="owner")  # type: ignore[arg-type]
    return bindings, documents, profiles, metadata


@pytest.mark.asyncio
async def test_owned_local_import_freezes_device_dataset_binding(store) -> None:
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    revision = await _register_local_revision(session, kb)
    await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).activate_local_revision(kb.id, revision.id)
    await session.commit()

    closure = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    bindings, ready, profiles, metadata = build_frozen_knowledge_bindings(closure, caller_user_id=str(kb.owner_id))

    dataset = f"local:{revision.id}"
    assert bindings == {kb.id: dataset}
    document_id = revision.manifest_json[0]["document_id"]
    assert ready == {dataset: [document_id]}
    assert profiles == {}
    entry = metadata[dataset]
    assert entry["knowledge_base_id"] == kb.id
    assert entry["revision_id"] == revision.id
    assert entry["revision_no"] == 1
    assert entry["manifest_hash"] == revision.manifest_hash
    assert entry["configuration_source"] == "frozen_run_revision"
    assert entry["origin"] == "local_import"
    assert entry["device_id"] == DEVICE_ID
    assert entry["documents"] == {
        document_id: {
            "logical_document_id": document_id,
            "display_name": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
        }
    }


@pytest.mark.asyncio
async def test_foreign_local_kb_stays_invisible(store) -> None:
    """An unauthorized KB must not become model-visible through a local run."""
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    revision = await _register_local_revision(session, kb)
    await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).activate_local_revision(kb.id, revision.id)
    await session.commit()

    closure = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    kb_item = next(item for item in closure if item.resource.type == "knowledge_base")
    assert build_frozen_knowledge_bindings([kb_item], caller_user_id=str(kb.owner_id))[0] != {}
    bindings, ready, _profiles, metadata = build_frozen_knowledge_bindings([kb_item], caller_user_id="intruder")  # type: ignore[arg-type]
    assert bindings == {}
    assert ready == {}
    assert metadata == {}


@pytest.mark.asyncio
async def test_unbound_device_local_kb_stays_invisible(store) -> None:
    """Without one importing device the frozen KB cannot be routed anywhere."""
    session, _factory = store
    agent, kb = await _seed_agent_with_kb(session)
    # Registered with device_id=None: the manifest carries no device binding.
    orphan = await _register_local_revision(session, kb, device_id=None)
    await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).activate_local_revision(kb.id, orphan.id)
    await session.commit()

    closure = await ResourceService(session, _actor()).resolve_dependency_closure(agent.id)
    kb_item = next(item for item in closure if item.resource.type == "knowledge_base")
    bindings, ready, _profiles, metadata = build_frozen_knowledge_bindings([kb_item], caller_user_id=str(kb.owner_id))  # type: ignore[arg-type]
    assert bindings == {}
    assert ready == {}
    assert metadata == {}


# --- Slice B: adapter dispatch for device-local datasets ----------------------


def _local_scope() -> KnowledgeScope:
    document_id = "11111111-1111-4111-8111-111111111111"
    return KnowledgeScope.from_bindings(
        {"device-docs": f"local:{'revision-113'}"},
        ready_document_ids={f"local:{'revision-113'}": [document_id]},
        revision_metadata={
            f"local:{'revision-113'}": {
                "knowledge_base_id": "kb-113",
                "revision_id": "revision-113",
                "revision_no": 1,
                "manifest_hash": "c" * 64,
                "configuration_source": "frozen_run_revision",
                "origin": "local_import",
                "device_id": DEVICE_ID,
                "documents": {
                    document_id: {
                        "logical_document_id": document_id,
                        "display_name": "guide.txt",
                        "content_hash": "d" * 64,
                    }
                },
            }
        },
    )


@pytest.mark.anyio
async def test_local_dataset_dispatches_to_the_device_and_records_receipt() -> None:
    captured: dict = {}

    async def local_search(query: str, dataset_id: str) -> dict:
        captured["query"] = query
        captured["dataset_id"] = dataset_id
        return {
            "chunks": [
                {
                    "document_id": "11111111-1111-4111-8111-111111111111",
                    "document_keyword": "guide.txt",
                    "content": "the launch code is ALPHA-7",
                    "position": {"logical_path": "workspace/guide.txt", "line": 1},
                }
            ]
        }

    binding = RunEvidenceBinding([], AuthorizationContext("caller", "agent", "policy"), run_id="run-113")
    with bind_run_evidence(binding):
        adapter = KnowledgeRuntimeAdapter(_local_scope(), lambda *a, **k: [], local_search=local_search)
        result = await adapter.search_knowledge("launch code", logical_kb="device-docs")
        evidence = current_run_evidence()

    assert captured == {"query": "launch code", "dataset_id": "local:revision-113"}
    delivered = result["chunks"][0]
    # The model-facing projection strips provider/dataset identities and
    # carries only citation handles; the frozen document identity survives
    # solely inside the receipt.
    assert all(key not in delivered for key in ("dataset_id", "chunk_id", "kb_id"))
    assert delivered["document"] == "guide.txt"
    assert delivered["content"] == "the launch code is ALPHA-7"
    assert delivered["citation_label"] == "guide.txt"
    assert str(delivered["citation"]).startswith("[citation:guide.txt](evidence://rr_")
    assert evidence is not None and len(evidence.retrieval_receipts) == 1
    receipt = evidence.retrieval_receipts[0]
    assert receipt["run_id"] == "run-113"
    assert receipt["knowledge_base_id"] == "kb-113"
    assert receipt["revision_id"] == "revision-113"
    assert receipt["manifest_hash"] == "c" * 64
    assert receipt["result_status"] == "success"
    item = receipt["items"][0]
    assert item["display_name"] == "guide.txt"
    assert item["content_hash"] == "d" * 64
    assert item["position"] == {"position": {"logical_path": "workspace/guide.txt", "line": 1}}


@pytest.mark.anyio
async def test_local_dataset_without_device_dispatch_is_denied() -> None:
    binding = RunEvidenceBinding([], AuthorizationContext("caller", "agent", "policy"), run_id="run-113")
    with bind_run_evidence(binding):
        adapter = KnowledgeRuntimeAdapter(_local_scope(), lambda *a, **k: [])
        with pytest.raises(KnowledgeAccessDenied):
            await adapter.search_knowledge("launch code", logical_kb="device-docs")
        evidence = current_run_evidence()

    assert evidence is not None
    assert [receipt["result_status"] for receipt in evidence.retrieval_receipts] == ["access_denied"]


# --- Slice B: frozen-manifest result validation -------------------------------


def _spec() -> dict:
    return {
        "device_id": DEVICE_ID,
        "revision_id": "revision-113",
        "manifest_hash": "c" * 64,
        "documents": [
            {"document_id": "doc-a", "filename": "guide.txt", "content_hash": "d" * 64},
            {"document_id": "doc-b", "filename": "notes.txt", "content_hash": "e" * 64},
        ],
    }


def test_results_outside_the_frozen_manifest_are_dropped() -> None:
    from app.gateway.local_knowledge import validate_local_search_result

    result = {
        "chunks": [
            {"document_id": "doc-a", "content": "frozen"},
            {"document_id": "injected", "content": "never forwarded"},
            {"document_id": "", "content": "anonymous"},
            "not-a-chunk",
        ],
        "missing": [{"document_id": "doc-b", "reason": "content_drift"}, {"document_id": "nope", "reason": "x"}],
    }
    validated = validate_local_search_result(result, _spec())
    assert [chunk["document_id"] for chunk in validated["chunks"]] == ["doc-a"]
    assert validated["missing"] == [{"document_id": "doc-b", "reason": "content_drift"}]


def test_unreported_documents_are_recorded_missing() -> None:
    from app.gateway.local_knowledge import validate_local_search_result

    validated = validate_local_search_result({"chunks": [{"document_id": "doc-a", "content": "frozen"}]}, _spec())
    assert validated["missing"] == [{"document_id": "doc-b", "reason": "no_match"}]
    assert validate_local_search_result(None, _spec())["chunks"] == []


def test_chunk_delivery_is_bounded_by_the_receipt_budget() -> None:
    from app.gateway.local_knowledge import MAX_DELIVERED_CHUNKS, validate_local_search_result

    spec = _spec()
    result = {"chunks": [{"document_id": "doc-a", "content": f"chunk-{index}"} for index in range(MAX_DELIVERED_CHUNKS + 5)]}
    validated = validate_local_search_result(result, spec)
    assert len(validated["chunks"]) == MAX_DELIVERED_CHUNKS
