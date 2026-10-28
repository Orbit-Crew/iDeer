"""HTTP contract of scoped graph QA and relation retrieval (#117).

The query/ask endpoints sit beside the #116 graph endpoints and ride the
same resource authorization chain: an invisible KnowledgeBase reads as 404,
a document outside the frozen revision is a 409 instead of a silently
widened scope, and an ask whose selected material is missing or partially
failed answers with an explicit structured refusal — never a fabricated
conclusion.
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

DEVICE_ID = "device-117-router"
GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()
POLICY = "乙组件的检修手册由检修班组维护。\n".encode()
UPDATE = "更新。\n".encode()


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


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


def _fixed_answerer():
    async def answer(question: str, documents: list[tuple[str, str, str]]) -> str:
        names = "、".join(name for name, _digest, _text in documents)
        return f"依据 {names}：甲零件属于乙组件。"

    return answer


class FakeConnection:
    def __init__(self, owner_id: str) -> None:
        self.device_id = DEVICE_ID
        self.owner_id = owner_id
        self.tasks_allowed = True
        self.capabilities = {"local.knowledge.search", "local.knowledge.material"}


class FakeBroker:
    """Device broker stand-in keyed by frozen filename."""

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
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-query-router.db'}")
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
            graph_answerer=_fixed_answerer(),
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

    async def seed_local_revision(self) -> tuple[str, KnowledgeRevision]:
        async with self.factory() as session:
            kb = await ResourceService(session, _actor()).create_resource(
                resource_type="knowledge_base",
                slug=f"query-kb-{uuid.uuid4().hex[:8]}",
                display_name="query-kb",
                storage_kind="database",
            )
            kb.latest_version = 1
            kb.draft_revision = 1
            session.add(
                ResourceVersion(
                    id=str(uuid.uuid4()),
                    resource_id=kb.id,
                    version=1,
                    content_hash=hashlib.sha256(b"query-kb").hexdigest(),
                    storage_key=f"knowledge_bases/{kb.id}",
                    scan_result={},
                    content={"description": "query-kb"},
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
                    },
                    {
                        "filename": "policy.txt",
                        "content_hash": hashlib.sha256(POLICY).hexdigest(),
                        "size_bytes": len(POLICY),
                        "mime_type": "text/plain",
                    },
                ],
                device_id=DEVICE_ID,
            )
            await session.commit()
            revision = await session.get(KnowledgeRevision, str(payload["id"]))
            assert revision is not None
            return str(kb.id), revision

    async def register_followup_revision(self, kb_id: str) -> KnowledgeRevision:
        """A later revision frozen from changed content on the same KB."""

        async with self.factory() as session:
            payload = await KnowledgeLocalImportService(session, _actor("owner")).register_local_import(
                kb_id,
                documents=[
                    {
                        "filename": "guide.txt",
                        "content_hash": hashlib.sha256(GUIDE + UPDATE).hexdigest(),
                        "size_bytes": len(GUIDE) + len(UPDATE),
                        "mime_type": "text/plain",
                    }
                ],
                device_id=DEVICE_ID,
            )
            await session.commit()
            revision = await session.get(KnowledgeRevision, str(payload["id"]))
            assert revision is not None
            return revision


async def _noop_audit(*args, **kwargs) -> None:
    return None


def _document_ids(revision: KnowledgeRevision) -> dict[str, str]:
    return {str(entry.get("filename")): str(entry["document_id"]) for entry in revision.manifest_json}


@pytest.fixture
def harness(tmp_path):
    broker = FakeBroker(documents={"guide.txt": GUIDE.decode(), "policy.txt": POLICY.decode()})
    instance = Harness(tmp_path, broker=broker)
    kb_id, revision = asyncio.run(instance.seed_local_revision())
    instance.kb_id = kb_id
    instance.revision_id = str(revision.id)
    instance.ids = _document_ids(revision)
    try:
        yield instance
    finally:
        asyncio.run(instance.engine.dispose())


def _generate(harness: Harness) -> dict:
    client = harness.client()
    generated = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph")
    assert generated.status_code == 200
    return generated.json()


def test_scoped_query_and_ask_contract_over_http(harness) -> None:
    """Narrow to guide.txt, then widen: results follow the selected scope with
    real sources, and the ask names exactly the selected documents."""

    _generate(harness)
    client = harness.client()
    guide_id = harness.ids["guide.txt"]

    narrowed = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
        json={"query": "", "document_ids": [guide_id]},
    )
    assert narrowed.status_code == 200
    body = narrowed.json()
    assert body["status"] == "completed"
    assert body["revision_no"] >= 1 and len(body["manifest_hash"]) == 64
    assert [entity["name"] for entity in body["entities"]] == ["甲零件", "乙组件"]
    assert all(row["document_id"] == guide_id for row in body["entities"])
    assert [row["document_id"] for row in body["scope"]] == [guide_id]
    assert body["scope"][0]["filename"] == "guide.txt"
    assert body["scope"][0]["content_hash"] == hashlib.sha256(GUIDE).hexdigest()

    widened = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
        json={"query": "检修班组", "document_ids": [guide_id, harness.ids["policy.txt"]]},
    )
    assert widened.status_code == 200
    widened_body = widened.json()
    assert [entity["name"] for entity in widened_body["entities"]] == ["检修班组"]
    assert widened_body["entities"][0]["filename"] == "policy.txt"

    asked = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/ask",
        json={"question": "乙组件由什么构成？", "document_ids": [guide_id]},
    )
    assert asked.status_code == 200
    answer = asked.json()
    assert answer["answer_available"] is True
    assert answer["answer"].startswith("依据 guide.txt")
    assert [row["document_id"] for row in answer["scope"]] == [guide_id]


def test_unauthorized_kb_is_404_while_visible_department_reads(harness) -> None:
    """No tag filter or label can stand in for authorization: a caller without
    access reads the scoped surface as 404, a granted department member reads
    it like retrieval — and still cannot generate."""

    _generate(harness)
    stranger = harness.client(user_id="stranger")
    assert (
        stranger.post(
            f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
            json={"query": "", "document_ids": [harness.ids["guide.txt"]]},
        ).status_code
        == 404
    )
    assert (
        stranger.post(
            f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/ask",
            json={"question": "问题", "document_ids": [harness.ids["guide.txt"]]},
        ).status_code
        == 404
    )

    async def grant() -> None:
        async with harness.factory() as session:
            resource = await session.get(Resource, harness.kb_id)
            resource.visibility = "department"
            resource.scope_department_id = "dept-117"
            await session.commit()

    asyncio.run(grant())
    member = harness.client(user_id="colleague", department_id="dept-117")
    assert (
        member.post(
            f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
            json={"query": "甲零件", "document_ids": [harness.ids["guide.txt"]]},
        ).status_code
        == 200
    )
    assert (
        member.post(
            f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/ask",
            json={"question": "乙组件由什么构成？", "document_ids": [harness.ids["guide.txt"]]},
        ).status_code
        == 200
    )
    assert member.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph").status_code == 403


def test_document_outside_the_frozen_revision_is_refused(harness) -> None:
    _generate(harness)
    client = harness.client()
    outside = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
        json={"query": "", "document_ids": [str(uuid.uuid4())]},
    )
    assert outside.status_code == 409
    unknown_revision = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{uuid.uuid4()}/graph/ask",
        json={"question": "问题", "document_ids": [harness.ids["guide.txt"]]},
    )
    assert unknown_revision.status_code == 404


def test_invalid_scoped_request_bodies_are_422(harness) -> None:
    client = harness.client()
    base = f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph"
    assert client.post(f"{base}/query", json={"query": "", "document_ids": []}).status_code == 422
    assert client.post(f"{base}/query", json={"query": "长" * 513, "document_ids": [harness.ids["guide.txt"]]}).status_code == 422
    assert client.post(f"{base}/ask", json={"question": "", "document_ids": [harness.ids["guide.txt"]]}).status_code == 422
    assert client.post(f"{base}/ask", json={"question": "问题"}).status_code == 422
    assert client.post(f"{base}/ask", json={"question": "问题", "document_ids": ["Guide/../escape"]}).status_code == 422


def test_version_change_never_replaces_the_original_revision_sources(harness) -> None:
    """After a new revision is published, the original revision's scoped
    answers and sources stay exactly what they were — frozen, not silently
    swapped to the new version."""

    _generate(harness)
    client = harness.client()
    guide_id = harness.ids["guide.txt"]
    ask_body = {"question": "乙组件由什么构成？", "document_ids": [guide_id]}
    before_query = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
        json={"query": "", "document_ids": [guide_id]},
    ).json()
    before_ask = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/ask", json=ask_body).json()

    followup = asyncio.run(harness.register_followup_revision(harness.kb_id))
    assert followup.manifest_hash != before_query["manifest_hash"]

    after_query = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
        json={"query": "", "document_ids": [guide_id]},
    )
    after_ask = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/ask", json=ask_body)
    assert after_query.status_code == 200 and after_ask.status_code == 200
    assert after_query.json() == before_query
    assert after_ask.json() == before_ask
    # And the new revision's documents are outside the original scope.
    refused = client.post(
        f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/graph/query",
        json={"query": "", "document_ids": [_document_ids(followup)["guide.txt"]]},
    )
    assert refused.status_code == 409


def test_partial_material_failure_refuses_to_answer(harness) -> None:
    """One drifted selected document: the ask states the failure per document
    and returns no answer — a gapped scope never reaches the model."""

    drifted = FakeBroker(documents={"guide.txt": GUIDE.decode()})
    instance = Harness(harness.tmp_path, broker=drifted)
    kb_id, revision = asyncio.run(instance.seed_local_revision())
    instance.kb_id = kb_id
    instance.revision_id = str(revision.id)
    instance.ids = _document_ids(revision)
    try:
        client = instance.client()
        generated = client.post(f"/api/resources/{kb_id}/knowledge-revisions/{instance.revision_id}/graph")
        assert generated.status_code == 200 and generated.json()["status"] == "partial"

        asked = client.post(
            f"/api/resources/{kb_id}/knowledge-revisions/{instance.revision_id}/graph/ask",
            json={"question": "检修手册由谁维护？", "document_ids": [instance.ids["guide.txt"], instance.ids["policy.txt"]]},
        )
        assert asked.status_code == 200
        body = asked.json()
        assert body["answer_available"] is False
        assert body["answer"] is None
        assert body["status"] == "partial"
        scope = {row["filename"]: row for row in body["scope"]}
        assert scope["policy.txt"]["status"] == "failed"
        assert scope["policy.txt"]["error_code"] == "GRAPH_CONTENT_DRIFTED"

        queried = client.post(
            f"/api/resources/{kb_id}/knowledge-revisions/{instance.revision_id}/graph/query",
            json={"query": "", "document_ids": [instance.ids["guide.txt"], instance.ids["policy.txt"]]},
        )
        assert queried.status_code == 200
        assert queried.json()["status"] == "partial"
        assert all(entity["filename"] == "guide.txt" for entity in queried.json()["entities"])
    finally:
        asyncio.run(instance.engine.dispose())
