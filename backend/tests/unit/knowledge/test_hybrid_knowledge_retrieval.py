"""Hybrid device/server retrieval semantics for canonical Runs (#114).

Web and Desktop drive the same Server authorization and Runtime chain: one
frozen scope holds provider datasets and device-local datasets side by side.
Every result and receipt names its KB/revision source and its engine, raw
scores are never compared across engines, and a failed local leg must never
read as "no material": with other authorized sources the answer proceeds
marked incomplete, while a run whose authorized material is local-only pauses
instead of answering.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from agentplatform_extension.evidence import (
    AuthorizationContext,
    RunEvidenceBinding,
    bind_run_evidence,
    current_run_evidence,
)
from agentplatform_extension.knowledge.runtime_adapter import KnowledgeRuntimeAdapter
from agentplatform_extension.knowledge.scope import KnowledgeScope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeBase, KnowledgeRevision
from app.agentplatform.knowledge.scope import calculate_effective_knowledge_scope
from app.agentplatform.resource_models import Resource, ResourceDependency, ResourceVersion
from app.agentplatform.resources.service import ResourceAction, ResourceActor, ResourceService
from app.gateway.canonical_agent_run_preparation import prepare_canonical_agent_run
from app.gateway.hybrid_knowledge import (
    ENGINE_LOCAL_DEVICE,
    ENGINE_SERVER_PROVIDER,
    RESULT_SOURCE_UNAVAILABLE,
    RESULT_STATUS_PAUSED_LOCAL_REQUIRED,
    local_retrieval_pause_result,
    local_source_unavailable_result,
    requires_local_material,
    source_attribution,
)
from deerflow.persistence.base import Base

DEVICE_ID = "device-114"
GUIDE = b"hybrid retrieval answer: the launch code is ALPHA-7\n"
DEVICE_DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[tuple[AsyncSession, async_sessionmaker]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'hybrid-retrieval.db'}")
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


async def _seed_kb_with_dependency(session: AsyncSession, agent: Resource, slug: str) -> Resource:
    kb = await _seed_resource(session, resource_type="knowledge_base", slug=slug)
    session.add(ResourceDependency(id=str(uuid.uuid4()), source_resource_id=agent.id, target_resource_id=kb.id, dependency_mode="live"))
    return kb


async def _register_local_revision(session: AsyncSession, kb: Resource, *, device_id: str = DEVICE_ID) -> KnowledgeRevision:
    """Register one local import through the real #112 service."""

    actor = _actor(str(kb.owner_id))
    service = KnowledgeLocalImportService(session, actor)
    payload = await service.register_local_import(
        kb.id,
        documents=[{
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
            "size_bytes": len(GUIDE),
            "mime_type": "text/plain",
        }],
        device_id=device_id,
    )
    await session.commit()
    revision = await session.get(KnowledgeRevision, str(payload["id"]))
    assert revision is not None
    return revision


def _provider_revision(session: AsyncSession, kb: Resource, *, revision_no: int = 1) -> KnowledgeRevision:
    entry = {
        "document_id": "doc-server",
        "content_hash": hashlib.sha256(b"server bytes").hexdigest(),
        "filename": "policy.txt",
        "size_bytes": 12,
        "mime_type": "text/plain",
        "metadata": {},
    }
    row = KnowledgeRevision(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_no=revision_no,
        status="published",
        manifest_hash=hashlib.sha256(str(entry).encode()).hexdigest(),
        manifest_json=[entry],
        provider_doc_map_json={"doc-server": "provider-doc-1"},
        document_count=1,
        provider_dataset_id="published-dataset-114",
        publish_attempt=1,
        created_by=kb.owner_id,
    )
    session.add(row)
    return row


# --- Slice A: per-source attribution without cross-engine score mixing --------


def _mixed_scope() -> KnowledgeScope:
    return KnowledgeScope.from_bindings(
        {"server-docs": "published-dataset-114", "device-docs": "local:revision-114"},
        ready_document_ids={
            "published-dataset-114": ["provider-doc-1"],
            "local:revision-114": [DEVICE_DOCUMENT_ID],
        },
        revision_metadata={
            "published-dataset-114": {
                "knowledge_base_id": "kb-server",
                "revision_id": "revision-server-1",
                "revision_no": 3,
                "manifest_hash": "a" * 64,
                "configuration_source": "frozen_run_revision",
                "documents": {
                    "provider-doc-1": {
                        "logical_document_id": "doc-server",
                        "display_name": "policy.txt",
                        "content_hash": "b" * 64,
                    }
                },
            },
            "local:revision-114": {
                "knowledge_base_id": "kb-device",
                "revision_id": "revision-114",
                "revision_no": 1,
                "manifest_hash": "c" * 64,
                "configuration_source": "frozen_run_revision",
                "origin": "local_import",
                "device_id": DEVICE_ID,
                "documents": {
                    DEVICE_DOCUMENT_ID: {
                        "logical_document_id": DEVICE_DOCUMENT_ID,
                        "display_name": "guide.txt",
                        "content_hash": "d" * 64,
                    }
                },
            },
        },
    )


def _binding():
    return RunEvidenceBinding([], AuthorizationContext("caller", "agent", "policy"), run_id="run-114")


def _provider_chunks() -> dict:
    return {"chunks": [{
        "document_id": "provider-doc-1",
        "document_keyword": "policy.txt",
        "content": "server policy line",
        "similarity": 0.87,
        "chunk_id": "chunk-1",
    }]}


def _device_chunks() -> dict:
    return {"chunks": [{
        "document_id": DEVICE_DOCUMENT_ID,
        "document_keyword": "guide.txt",
        "content": "the launch code is ALPHA-7",
        "position": {"logical_path": "workspace/guide.txt", "line": 1},
    }]}


@pytest.mark.anyio
async def test_receipts_name_the_engine_and_kb_revision_source() -> None:
    """Every authorized result names its source: engine, KB, revision (#114)."""

    async def provider_search(query, *, dataset_ids, document_ids=None, retrieval_profile=None):
        return _provider_chunks()

    async def local_search(query, dataset_id):
        return _device_chunks()

    with bind_run_evidence(_binding()):
        adapter = KnowledgeRuntimeAdapter(_mixed_scope(), provider_search, local_search=local_search)
        server_result = await adapter.search_knowledge("launch", logical_kb="server-docs")
        device_result = await adapter.search_knowledge("launch", logical_kb="device-docs")
        evidence = current_run_evidence()

    assert evidence is not None and len(evidence.retrieval_receipts) == 2
    by_engine = {receipt["engine"]: receipt for receipt in evidence.retrieval_receipts}
    assert set(by_engine) == {ENGINE_SERVER_PROVIDER, ENGINE_LOCAL_DEVICE}

    server_receipt = by_engine[ENGINE_SERVER_PROVIDER]
    assert server_receipt["knowledge_base_id"] == "kb-server"
    assert server_receipt["revision_id"] == "revision-server-1"
    assert server_receipt["revision_no"] == 3
    device_receipt = by_engine[ENGINE_LOCAL_DEVICE]
    assert device_receipt["knowledge_base_id"] == "kb-device"
    assert device_receipt["revision_id"] == "revision-114"

    # The model-facing projections carry the same source labels, so a hybrid
    # answer can attribute each citation to its KB/revision and engine.
    server_chunk = server_result["chunks"][0]
    assert server_chunk["source"] == {
        "knowledge_base_id": "kb-server",
        "revision_id": "revision-server-1",
        "revision_no": 3,
        "engine": ENGINE_SERVER_PROVIDER,
    }
    device_chunk = device_result["chunks"][0]
    assert device_chunk["source"] == {
        "knowledge_base_id": "kb-device",
        "revision_id": "revision-114",
        "revision_no": 1,
        "engine": ENGINE_LOCAL_DEVICE,
    }


@pytest.mark.anyio
async def test_raw_scores_are_never_merged_across_engines() -> None:
    """Scores stay engine-local: the device engine has no comparable score."""

    async def provider_search(query, *, dataset_ids, document_ids=None, retrieval_profile=None):
        return _provider_chunks()

    async def local_search(query, dataset_id):
        return _device_chunks()

    with bind_run_evidence(_binding()):
        adapter = KnowledgeRuntimeAdapter(_mixed_scope(), provider_search, local_search=local_search)
        await adapter.search_knowledge("launch", logical_kb="server-docs")
        device_result = await adapter.search_knowledge("launch", logical_kb="device-docs")
        evidence = current_run_evidence()

    device_chunk = device_result["chunks"][0]
    # The device engine returns text matches, not similarities: nothing may
    # fabricate a score that would rank it against the provider's scale.
    assert "similarity" not in device_chunk
    device_receipt = next(
        receipt
        for receipt in (evidence.retrieval_receipts if evidence is not None else [])
        if receipt["engine"] == ENGINE_LOCAL_DEVICE
    )
    assert device_receipt["items"][0]["score"] is None
    assert device_receipt["items"][0]["engine"] == ENGINE_LOCAL_DEVICE


# --- Slice B: partial-failure semantics ---------------------------------------


def test_mixed_scope_can_answer_partially_but_local_only_scope_must_pause() -> None:
    assert requires_local_material({"kb-a": "local:rev-1"}) is True
    assert requires_local_material({}) is False
    assert requires_local_material({"kb-a": "local:rev-1", "kb-b": "ds-1"}) is False
    assert requires_local_material({"kb-b": "ds-1"}) is False


def test_source_attribution_projects_frozen_identity() -> None:
    attribution = source_attribution("local:rev-9", {
        "knowledge_base_id": "kb-9",
        "revision_id": "rev-9",
        "revision_no": 2,
        "manifest_hash": "c" * 64,
        "origin": "local_import",
    })
    assert attribution == {
        "knowledge_base_id": "kb-9",
        "revision_id": "rev-9",
        "revision_no": 2,
        "manifest_hash": "c" * 64,
        "origin": "local_import",
        "engine": ENGINE_LOCAL_DEVICE,
    }
    provider = source_attribution("ds-1", {"knowledge_base_id": "kb-1", "revision_id": "r1", "revision_no": 1, "manifest_hash": "a" * 64})
    assert provider["engine"] == ENGINE_SERVER_PROVIDER
    assert provider["origin"] == "provider"


@pytest.mark.anyio
async def test_unavailable_local_source_is_recorded_as_source_failure_never_empty_hit() -> None:
    attribution = source_attribution("local:revision-114", {
        "knowledge_base_id": "kb-device",
        "revision_id": "revision-114",
        "revision_no": 1,
        "manifest_hash": "c" * 64,
        "origin": "local_import",
    })

    async def provider_search(query, *, dataset_ids, document_ids=None, retrieval_profile=None):
        return _provider_chunks()

    async def local_search(query, dataset_id):
        return local_source_unavailable_result(attribution, "KNOWLEDGE_DEVICE_UNAVAILABLE")

    with bind_run_evidence(_binding()):
        adapter = KnowledgeRuntimeAdapter(_mixed_scope(), provider_search, local_search=local_search)
        failure_result = await adapter.search_knowledge("launch", logical_kb="device-docs")
        evidence = current_run_evidence()

    receipt = next(
        receipt
        for receipt in (evidence.retrieval_receipts if evidence is not None else [])
        if receipt["logical_knowledge_base"] == "device-docs"
    )
    # A failed local leg is a structured source failure, never an empty hit:
    # "no material" is exactly what it must not be able to impersonate.
    assert receipt["result_status"] == RESULT_SOURCE_UNAVAILABLE
    assert receipt["engine"] == ENGINE_LOCAL_DEVICE
    assert isinstance(failure_result, str)
    assert "kb-device" in failure_result
    assert "KNOWLEDGE_DEVICE_UNAVAILABLE" in failure_result
    assert "incomplete" in failure_result.lower()
    assert "no relevant content" not in failure_result.lower()


@pytest.mark.anyio
async def test_local_required_failure_pauses_instead_of_answering() -> None:
    attribution = source_attribution("local:revision-114", {
        "knowledge_base_id": "kb-device",
        "revision_id": "revision-114",
        "revision_no": 1,
        "manifest_hash": "c" * 64,
        "origin": "local_import",
    })

    async def provider_search(query, *, dataset_ids, document_ids=None, retrieval_profile=None):
        return {"chunks": []}

    async def local_search(query, dataset_id):
        return local_retrieval_pause_result(attribution, "DEVICE_DISCONNECTED")

    scope = KnowledgeScope.from_bindings(
        {"device-docs": "local:revision-114"},
        ready_document_ids={"local:revision-114": ["doc-a"]},
        revision_metadata={"local:revision-114": {"knowledge_base_id": "kb-device", "revision_id": "revision-114", "revision_no": 1, "manifest_hash": "c" * 64}},
    )
    with bind_run_evidence(_binding()):
        adapter = KnowledgeRuntimeAdapter(scope, provider_search, local_search=local_search)
        pause_result = await adapter.search_knowledge("launch", logical_kb="device-docs")
        evidence = current_run_evidence()

    receipt = (evidence.retrieval_receipts if evidence is not None else [{}])[0]
    assert receipt["result_status"] == RESULT_STATUS_PAUSED_LOCAL_REQUIRED
    assert isinstance(pause_result, str)
    assert "paused" in pause_result.lower()
    assert "DEVICE_DISCONNECTED" in pause_result
    assert "no relevant content" not in pause_result.lower()


# --- Slice C: the run-preparation closure serves both entries -----------------


class _FakeBroker:
    """Broker double: online/offline device, completed or failed task."""

    def __init__(self, *, online: bool, outcome: str) -> None:
        self.connections = {} if not online else {
            DEVICE_ID: SimpleNamespace(tasks_allowed=True, owner_id="owner", capabilities={"local.knowledge.search"}),
        }
        self._outcome = outcome
        self.sent: list[dict] = []

    def _status(self):
        from app.device_control.broker import TaskStatus

        return {
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
            "pending": TaskStatus.SENT,
        }[self._outcome]

    @staticmethod
    def _echoed_chunks(kwargs: dict) -> dict:
        # The unique Runtime re-validates against the frozen manifest and can
        # only ever report frozen document identities back.
        frozen = (kwargs.get("payload_extra", {}).get("arguments", {}).get("documents") or [{}])[0]
        return {"chunks": [{
            "document_id": frozen.get("document_id", ""),
            "document_keyword": frozen.get("filename", "guide.txt"),
            "content": "the launch code is ALPHA-7",
            "position": {"logical_path": "workspace/guide.txt", "line": 1},
        }]}

    def _record(self, task_id: str, kwargs: dict | None = None) -> SimpleNamespace:
        completed = self._outcome == "completed"
        return SimpleNamespace(
            task_id=task_id,
            status=self._status(),
            result=self._echoed_chunks(kwargs or {}) if completed else None,
            receipt=None,
            error_code="DEVICE_DISCONNECTED" if self._outcome == "failed" else None,
        )

    async def send_task(self, **kwargs):
        self.sent.append(kwargs)
        return self._record("task-114", kwargs)

    def get_task(self, task_id):
        return self._record(task_id, self.sent[-1] if self.sent else None)


class _ToolConfig:
    datasets = None


class _AppConfig:
    def get_tool_config(self, name):
        return _ToolConfig()


async def _prepare_hybrid_run(
    session_factory: async_sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    broker: _FakeBroker,
    provider_kb: bool,
) -> dict:
    """Prepare one run over a device KB (+ optional server KB) and capture the closure."""

    from app.agentplatform.rbac_models import UserModel

    async with session_factory() as session:
        session.add(UserModel(id="owner", username="owner@test.com", role="user", department_id=None, disabled=False))
        await session.commit()
        agent = await ResourceService(session, _actor("owner")).create_resource(
            resource_type="agent",
            slug="helper",
            display_name="helper",
            storage_kind="filesystem",
        )
        device_kb = await _seed_kb_with_dependency(session, agent, "kb-device-114")
        revision = await _register_local_revision(session, device_kb)
        await KnowledgeLocalImportService(session, _actor(str(device_kb.owner_id))).activate_local_revision(device_kb.id, revision.id)
        if provider_kb:
            server_kb = await _seed_kb_with_dependency(session, agent, "kb-server-114")
            server_revision = _provider_revision(session, server_kb)
            await session.commit()
            kb_row = await session.get(KnowledgeBase, server_kb.id)
            assert kb_row is not None
            kb_row.active_revision_id = server_revision.id
        agent_id = agent.id
        await session.commit()

    monkeypatch.setattr("deerflow.persistence.engine.get_session_factory", lambda: session_factory)
    monkeypatch.setattr("app.gateway.audit.get_session_factory", lambda: session_factory)
    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _AppConfig())
    monkeypatch.setattr("app.device_control.broker.get_device_broker", lambda: broker)
    captured: dict = {}

    def fake_build(definition, skills, *, runner_tool_groups=None, knowledge_scope=None, local_knowledge_search=None, **kwargs):
        captured["scope"] = knowledge_scope
        captured["local_search"] = local_knowledge_search
        return lambda config, app_config=None: SimpleNamespace(graph=None)

    monkeypatch.setattr("app.agentplatform.runtime_adapter.build_canonical_agent_factory", fake_build)

    from app.agentplatform.resources.publisher import ResourcePublisher
    from app.agentplatform.resources.storage import ResourceStorage

    source = tmp_path / "agent-source-114"
    source.mkdir(exist_ok=True)
    (source / "config.yaml").write_text("name: helper\n")
    (source / "SOUL.md").write_text("frozen soul\n")
    async with session_factory() as session:
        service = ResourceService(session, _actor("owner"))
        resource = await session.get(Resource, agent_id)
        assert resource is not None
        publisher = ResourcePublisher(service, ResourceStorage(tmp_path))
        draft = await publisher.save_filesystem_draft(resource.id, source_dir=source, expected_revision=0)
        await publisher.publish_filesystem(resource.id, expected_draft_revision=draft.revision, scan_result={})
        await session.commit()

    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="owner")))
    await prepare_canonical_agent_run(agent_id, request, "run-114")
    assert captured["local_search"] is not None
    assert captured["scope"] is not None
    return captured


def _local_dataset_tokens(scope: KnowledgeScope) -> list[str]:
    return [token for _logical, token in scope.bindings if token.startswith("local:")]  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_closure_dispatches_to_device_and_delivers_validated_chunks(store, tmp_path, monkeypatch) -> None:
    session, factory = store
    broker = _FakeBroker(online=True, outcome="completed")
    captured = await _prepare_hybrid_run(factory, tmp_path, monkeypatch, broker=broker, provider_kb=True)

    local_datasets = _local_dataset_tokens(captured["scope"])
    assert len(local_datasets) == 1

    result = await captured["local_search"]("launch code", local_datasets[0])
    assert broker.sent and broker.sent[0]["operation"] == "local.knowledge.search"
    assert result["chunks"] and result["chunks"][0]["content"] == "the launch code is ALPHA-7"


@pytest.mark.asyncio
async def test_device_unavailable_in_hybrid_scope_reports_incomplete_source(store, tmp_path, monkeypatch) -> None:
    session, factory = store
    broker = _FakeBroker(online=False, outcome="failed")
    captured = await _prepare_hybrid_run(factory, tmp_path, monkeypatch, broker=broker, provider_kb=True)

    local_datasets = _local_dataset_tokens(captured["scope"])
    assert requires_local_material(dict(captured["scope"].bindings)) is False

    result = await captured["local_search"]("launch code", local_datasets[0])
    assert isinstance(result, dict)
    assert result["source_failure"]["engine"] == ENGINE_LOCAL_DEVICE
    assert result["source_failure"]["error_code"] == "KNOWLEDGE_DEVICE_UNAVAILABLE"
    assert result["incomplete"] is True
    assert "pause" not in result


@pytest.mark.asyncio
async def test_mid_disconnect_failure_is_structured_not_raised(store, tmp_path, monkeypatch) -> None:
    session, factory = store
    broker = _FakeBroker(online=True, outcome="failed")
    captured = await _prepare_hybrid_run(factory, tmp_path, monkeypatch, broker=broker, provider_kb=True)

    local_datasets = _local_dataset_tokens(captured["scope"])
    result = await captured["local_search"]("launch code", local_datasets[0])
    assert result["source_failure"]["error_code"] == "DEVICE_DISCONNECTED"
    assert result["incomplete"] is True


@pytest.mark.asyncio
async def test_local_only_run_pauses_when_the_device_is_unavailable(store, tmp_path, monkeypatch) -> None:
    session, factory = store
    broker = _FakeBroker(online=False, outcome="failed")
    captured = await _prepare_hybrid_run(factory, tmp_path, monkeypatch, broker=broker, provider_kb=False)

    local_datasets = _local_dataset_tokens(captured["scope"])
    assert requires_local_material(dict(captured["scope"].bindings)) is True

    result = await captured["local_search"]("launch code", local_datasets[0])
    assert isinstance(result, dict)
    assert result["pause"] == {"reason": "local_knowledge_required", "error_code": "KNOWLEDGE_DEVICE_UNAVAILABLE"}
    assert result["incomplete"] is True


# --- Slice D: hybrid selection can only narrow the frozen scope ---------------


def test_runtime_restriction_cannot_add_unknown_knowledge_bases() -> None:
    bindings = {"kb-a": "ds-a", "kb-b": "local:rev-b"}
    # A Web/Desktop selection naming an unbound KB must stay ignored: hybrid
    # selection narrows the frozen closure, it never widens it.
    assert calculate_effective_knowledge_scope(
        bindings,
        caller_allowed={"kb-a", "kb-b"},
        runtime_allowed={"kb-a", "kb-not-mine"},
    ) == {"kb-a": "ds-a"}
    assert calculate_effective_knowledge_scope(
        bindings,
        caller_allowed={"kb-a", "kb-b"},
        runtime_allowed=set(),
    ) == {}
