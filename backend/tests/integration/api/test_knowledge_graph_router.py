"""HTTP contract of the controlled knowledge-graph surface (#116).

Generation and viewing ride the same resource authorization chain as every
knowledge intent: a hidden KnowledgeBase reads as 404, a non-modifiable one
answers 403 on generate while department members may still read the graph,
and the response carries the frozen revision identity, per-document status,
and source bindings verbatim from the stored artifacts.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeRevision
from app.agentplatform.rbac_models import UserModel
from app.agentplatform.resource_models import Resource, ResourceVersion
from app.agentplatform.resources.service import ResourceAction, ResourceActor, ResourceService
from app.gateway.authz import get_current_rbac_user
from app.gateway.knowledge_seam import knowledge_facade
from app.gateway.routers import resources
from deerflow.persistence.base import Base

DEVICE_ID = "device-116-router"
GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


def _fixed_generator():
    async def generate(document_text: str) -> dict:
        return {
            "entities": [
                {"name": "甲零件", "type": "零件"},
                {"name": "乙组件", "type": "组件"},
            ],
            "relations": [{"source": "甲零件", "target": "乙组件", "relation": "属于"}],
        }

    return generate


class FakeConnection:
    def __init__(self, owner_id: str) -> None:
        self.device_id = DEVICE_ID
        self.owner_id = owner_id
        self.tasks_allowed = True
        self.capabilities = {"local.knowledge.search", "local.knowledge.material"}


class FakeBroker:
    def __init__(self, *, documents: dict[str, str], owner_id: str = "owner", online: bool = True) -> None:
        from app.device_control.broker import TaskStatus

        self.connections = {DEVICE_ID: FakeConnection(owner_id)} if online else {}
        self.documents = documents
        self._completed = TaskStatus.COMPLETED

    async def send_task(self, *, payload_extra=None, **kwargs):
        entry = payload_extra["arguments"]["documents"][0]
        text = self.documents.get(entry["filename"])
        if text is None:
            result = {"document_id": entry["document_id"], "missing": True, "reason": "content_drift"}
        else:
            result = {"document_id": entry["document_id"], "filename": entry["filename"], "content_hash": entry["content_hash"], "text": text}
        return SimpleNamespace(task_id=str(uuid.uuid4()), status=self._completed, receipt=None, tool_call_id="", error_code=None, result=result)

    def get_task(self, task_id):
        raise AssertionError("fake broker tasks settle immediately")


class Harness:
    def __init__(self, tmp_path: Path, *, broker: FakeBroker) -> None:
        self.tmp_path = tmp_path
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-router.db'}")
        asyncio.run(self._create_schema())
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.broker = broker

    async def _create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    def facade(self) -> KnowledgeFacade:
        return KnowledgeFacade(
            self.factory,
            audit=_noop_audit,
            graph_generator=_fixed_generator(),
            graph_broker_factory=lambda: self.broker,
        )

    def client(self, *, user_id: str = "owner", role: str = "user", department_id: str | None = None) -> TestClient:
        app = FastAPI()
        app.include_router(resources.router)
        app.dependency_overrides[knowledge_facade] = self.facade
        app.dependency_overrides[get_current_rbac_user] = lambda: UserModel(
            id=user_id,
            username=f"{user_id}@example.com",
            role=role,
            department_id=department_id,
        )
        return TestClient(app)

    async def seed_local_revision(self) -> tuple[str, str, KnowledgeRevision]:
        async with self.factory() as session:
            kb = await ResourceService(session, _actor()).create_resource(
                resource_type="knowledge_base",
                slug=f"router-kb-{uuid.uuid4().hex[:8]}",
                display_name="router-kb",
                storage_kind="database",
            )
            kb.latest_version = 1
            kb.draft_revision = 1
            session.add(
                ResourceVersion(
                    id=str(uuid.uuid4()),
                    resource_id=kb.id,
                    version=1,
                    content_hash=hashlib.sha256(b"router-kb").hexdigest(),
                    storage_key=f"knowledge_bases/{kb.id}",
                    scan_result={},
                    content={"description": "router-kb"},
                    created_by=kb.owner_id,
                )
            )
            payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
                kb.id,
                documents=[
                    {
                        "filename": "guide.txt",
                        "content_hash": hashlib.sha256(GUIDE).hexdigest(),
                        "size_bytes": len(GUIDE),
                        "mime_type": "text/plain",
                    }
                ],
                device_id=DEVICE_ID,
            )
            await session.commit()
            revision = await session.get(KnowledgeRevision, str(payload["id"]))
            assert revision is not None
            return str(kb.id), str(kb.owner_id), revision


async def _noop_audit(*args, **kwargs) -> None:
    return None


@pytest.fixture
def harness(tmp_path):
    broker = FakeBroker(documents={"guide.txt": GUIDE.decode()})
    instance = Harness(tmp_path, broker=broker)
    kb_id, owner_id, revision = asyncio.run(instance.seed_local_revision())
    instance.kb_id = kb_id
    instance.revision_id = str(revision.id)
    try:
        yield instance
    finally:
        asyncio.run(instance.engine.dispose())


def test_owner_generates_and_reads_graph_with_sources(harness) -> None:
    client = harness.client()
    generated = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert generated.status_code == 200
    assert generated.json()["status"] == "completed"
    assert generated.json()["revision_no"] >= 1

    view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert view.status_code == 200
    body = view.json()
    assert body["status"] == "completed"
    assert body["manifest_hash"]
    assert {"name": "甲零件", "type": "零件", "document_id": body["entities"][0]["document_id"], "filename": "guide.txt"} in body["entities"]
    assert body["relations"] == [{"source": "甲零件", "target": "乙组件", "relation": "属于", "document_id": body["relations"][0]["document_id"], "filename": "guide.txt"}]
    assert body["sources"][0]["filename"] == "guide.txt"
    assert body["sources"][0]["content_hash"] == hashlib.sha256(GUIDE).hexdigest()


def test_graph_generation_is_idempotent_on_repeat(harness) -> None:
    client = harness.client()
    first = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    second = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert (first.status_code, second.status_code) == (200, 200)
    view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert len(view.json()["entities"]) == 2
    assert len(view.json()["relations"]) == 1


def test_other_account_cannot_see_or_generate(harness) -> None:
    owner = harness.client(user_id="owner")
    assert owner.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph").status_code == 200

    stranger = harness.client(user_id="stranger")
    assert stranger.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph").status_code == 404
    assert stranger.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph").status_code == 404


def test_department_member_reads_but_cannot_generate(harness) -> None:
    asyncio.run(_make_department_visible(harness))
    member = harness.client(user_id="colleague", department_id="dept-116")
    assert member.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph").status_code == 200
    assert member.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph").status_code == 403


async def _make_department_visible(harness: Harness) -> None:
    async with harness.factory() as session:
        resource = await session.get(Resource, harness.kb_id)
        resource.visibility = "department"
        resource.scope_department_id = "dept-116"
        await session.commit()


def test_unknown_revision_is_404(harness) -> None:
    client = harness.client()
    assert client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{uuid.uuid4()}/graph").status_code == 404


def test_partial_failure_is_visible_through_the_router(harness) -> None:
    """One drifted document fails with its fixed category; the other stays
    verifiable — the aggregate reads partial, never silently complete."""

    asyncio.run(_add_second_document(harness))
    client = harness.client()
    generated = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "partial"
    assert body["generated"] == 1 and body["failed"] == 1
    statuses = {row["filename"]: row["status"] for row in body["documents"]}
    assert statuses == {"guide.txt": "completed", "policy.txt": "failed"}
    view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert view.json()["status"] == "partial"


async def _add_second_document(harness: Harness) -> None:
    """Freeze a fresh two-document revision on the same KB; the device only
    still holds guide.txt at its frozen digest, so policy.txt drifts."""

    async with harness.factory() as session:
        kb = await session.get(Resource, harness.kb_id)
        payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
            kb.id,
            documents=[
                {
                    "filename": "guide.txt",
                    "content_hash": hashlib.sha256(GUIDE).hexdigest(),
                    "size_bytes": len(GUIDE),
                    "mime_type": "text/plain",
                },
                {
                    "filename": "policy.txt",
                    "content_hash": hashlib.sha256(b"policy bytes").hexdigest(),
                    "size_bytes": 12,
                    "mime_type": "text/plain",
                },
            ],
            device_id=DEVICE_ID,
        )
        await session.commit()
        harness.revision_id = str(payload["id"])
