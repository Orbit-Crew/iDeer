"""The caller-authorized knowledge scope view behind one Agent (#114).

Web chat must let the caller see and select the KB sources a Run will search
— server provider KBs and the caller's own online-device KBs alike — through
the same authorization the Run itself applies: the frozen closure bindings.
The view can therefore only ever project what `build_frozen_knowledge_bindings`
binds for this caller; another user's KB or an unanchored local KB stays out,
and selection itself can only narrow the scope, never widen it.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeBase, KnowledgeRevision
from app.agentplatform.rbac_models import UserModel
from app.agentplatform.resource_models import Resource, ResourceDependency, ResourceVersion
from app.agentplatform.resources.service import ResourceAction, ResourceActor, ResourceNotFound, ResourceService
from app.gateway.hybrid_knowledge import knowledge_scope_view
from deerflow.persistence.base import Base

DEVICE_ID = "device-114"


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[tuple]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-scope.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(UserModel(id="owner", username="owner@test.com", role="user", department_id="dept-a", disabled=False))
        session.add(UserModel(id="teammate", username="mate@test.com", role="user", department_id="dept-a", disabled=False))
        session.add(UserModel(id="stranger", username="str@test.com", role="user", department_id=None, disabled=False))
        await session.commit()
    yield factory
    await engine.dispose()


def _actor(user_id: str) -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


async def _seed_resource(session, *, resource_type: str, slug: str, owner: str) -> Resource:
    resource = await ResourceService(session, _actor(owner)).create_resource(
        resource_type=resource_type,
        slug=slug,
        display_name=slug.replace("-", " ").capitalize(),
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


async def _seed_agent(session, owner: str, *, kbs: list[Resource]) -> Resource:
    agent = await _seed_resource(session, resource_type="agent", slug="helper", owner=owner)
    agent.visibility = "public"
    for kb in kbs:
        session.add(ResourceDependency(id=str(uuid.uuid4()), source_resource_id=agent.id, target_resource_id=kb.id, dependency_mode="live"))
    await session.commit()
    return agent


async def _register_local_revision(session, kb: Resource, *, device_id: str | None = DEVICE_ID) -> KnowledgeRevision:
    service = KnowledgeLocalImportService(session, _actor(str(kb.owner_id)))
    payload = await service.register_local_import(
        kb.id,
        documents=[{
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(b"guide bytes\n").hexdigest(),
            "size_bytes": 12,
            "mime_type": "text/plain",
        }],
        device_id=device_id,
    )
    await session.commit()
    revision = await session.get(KnowledgeRevision, str(payload["id"]))
    assert revision is not None
    return revision


class _Broker:
    def __init__(self, online: bool) -> None:
        self.connections = {} if not online else {
            DEVICE_ID: SimpleNamespace(tasks_allowed=True, owner_id="owner", capabilities={"local.knowledge.search"}),
        }


async def _seed_hybrid_agent(factory, *, device_online: bool = True, monkeypatch: pytest.MonkeyPatch | None = None) -> str:
    async with factory() as session:
        device_kb = await _seed_resource(session, resource_type="knowledge_base", slug="kb-device", owner="owner")
        server_kb = await _seed_resource(session, resource_type="knowledge_base", slug="kb-server", owner="owner")
        # The Agent is public; a public source may only depend on public KBs.
        device_kb.visibility = "public"
        server_kb.visibility = "public"
        agent = await _seed_agent(session, "owner", kbs=[device_kb, server_kb])
        revision = await _register_local_revision(session, device_kb)
        await KnowledgeLocalImportService(session, _actor("owner")).activate_local_revision(device_kb.id, revision.id)

        entry = {
            "document_id": "doc-server",
            "content_hash": hashlib.sha256(b"server bytes").hexdigest(),
            "filename": "policy.txt",
            "size_bytes": 12,
            "mime_type": "text/plain",
            "metadata": {},
        }
        server_revision = KnowledgeRevision(
            id=str(uuid.uuid4()),
            knowledge_base_id=server_kb.id,
            revision_no=1,
            status="published",
            manifest_hash=hashlib.sha256(str(entry).encode()).hexdigest(),
            manifest_json=[entry],
            provider_doc_map_json={"doc-server": "provider-doc-1"},
            document_count=1,
            provider_dataset_id="published-dataset-114",
            publish_attempt=1,
            created_by=server_kb.owner_id,
        )
        session.add(server_revision)
        await session.commit()
        kb_row = await session.get(KnowledgeBase, server_kb.id)
        assert kb_row is not None
        kb_row.active_revision_id = server_revision.id
        await session.commit()
        return agent.id


@pytest.mark.asyncio
async def test_scope_view_projects_device_and_server_sources_with_online_state(env, monkeypatch) -> None:
    factory = env
    agent_id = await _seed_hybrid_agent(factory)
    monkeypatch.setattr("app.device_control.broker.get_device_broker", lambda: _Broker(online=True))

    async with factory() as session:
        view = await knowledge_scope_view(session, _actor("owner"), agent_id)

    assert view["agent_id"] == agent_id
    assert view["selection"] == "narrow_only"
    by_slug = {source["slug"]: source for source in view["sources"]}
    assert set(by_slug) == {"kb-device", "kb-server"}

    device = by_slug["kb-device"]
    assert device["origin"] == "local_import"
    assert device["device_id"] == DEVICE_ID
    assert device["device_online"] is True
    assert device["dataset"].startswith("local:")
    assert device["revision_no"] == 1

    server = by_slug["kb-server"]
    assert server["origin"] == "provider"
    assert server["dataset"] == "published-dataset-114"
    assert "device_id" not in server


@pytest.mark.asyncio
async def test_scope_view_marks_the_own_device_offline(env, monkeypatch) -> None:
    factory = env
    agent_id = await _seed_hybrid_agent(factory)
    monkeypatch.setattr("app.device_control.broker.get_device_broker", lambda: _Broker(online=False))

    async with factory() as session:
        view = await knowledge_scope_view(session, _actor("owner"), agent_id)

    device = next(source for source in view["sources"] if source["origin"] == "local_import")
    assert device["device_online"] is False


@pytest.mark.asyncio
async def test_unanchored_local_kb_stays_out_of_the_view(env, monkeypatch) -> None:
    factory = env
    async with factory() as session:
        orphan_kb = await _seed_resource(session, resource_type="knowledge_base", slug="kb-orphan", owner="owner")
        orphan_kb.visibility = "public"
        agent = await _seed_agent(session, "owner", kbs=[orphan_kb])
        # Registered but never anchored: no LIVE/PINNED revision resolves, so
        # the closure refuses the run — exactly like run preparation.
        await _register_local_revision(session, orphan_kb)
        agent_id = agent.id

    with pytest.raises(Exception) as conflict:
        async with factory() as session:
            await knowledge_scope_view(session, _actor("owner"), agent_id)
    assert type(conflict.value).__name__ == "ResourceConflict"


@pytest.mark.asyncio
async def test_another_users_local_kb_binds_nothing_for_a_teammate(env, monkeypatch) -> None:
    factory = env
    async with factory() as session:
        device_kb = await _seed_resource(session, resource_type="knowledge_base", slug="kb-device", owner="owner")
        server_kb = await _seed_resource(session, resource_type="knowledge_base", slug="kb-server", owner="owner")
        agent = await _seed_agent(session, "owner", kbs=[device_kb, server_kb])
        # The device KB is public, so the teammate's closure resolves — but a
        # device-local KB only ever binds for its owner.
        device_kb.visibility = "public"
        server_kb.visibility = "public"
        revision = await _register_local_revision(session, device_kb)
        await KnowledgeLocalImportService(session, _actor("owner")).activate_local_revision(device_kb.id, revision.id)

        entry = {
            "document_id": "doc-server",
            "content_hash": hashlib.sha256(b"server bytes").hexdigest(),
            "filename": "policy.txt",
            "size_bytes": 12,
            "mime_type": "text/plain",
            "metadata": {},
        }
        server_revision = KnowledgeRevision(
            id=str(uuid.uuid4()),
            knowledge_base_id=server_kb.id,
            revision_no=1,
            status="published",
            manifest_hash=hashlib.sha256(str(entry).encode()).hexdigest(),
            manifest_json=[entry],
            provider_doc_map_json={"doc-server": "provider-doc-1"},
            document_count=1,
            provider_dataset_id="published-dataset-114",
            publish_attempt=1,
            created_by=server_kb.owner_id,
        )
        session.add(server_revision)
        await session.commit()
        kb_row = await session.get(KnowledgeBase, server_kb.id)
        assert kb_row is not None
        kb_row.active_revision_id = server_revision.id
        agent_id = agent.id
        await session.commit()
    monkeypatch.setattr("app.device_control.broker.get_device_broker", lambda: _Broker(online=True))

    async with factory() as session:
        view = await knowledge_scope_view(session, _actor("teammate"), agent_id)
    # The teammate selects the same Agent but A's device KB stays out: only
    # what this caller's Run would actually bind is offered for selection.
    assert [source["slug"] for source in view["sources"]] == ["kb-server"]

    # A caller who cannot see the Agent at all reads not-found.
    async with factory() as session:
        stranger_agent = await _seed_resource(session, resource_type="agent", slug="str-agent", owner="stranger")
        with pytest.raises(ResourceNotFound):
            await knowledge_scope_view(session, _actor("teammate"), stranger_agent.id)
