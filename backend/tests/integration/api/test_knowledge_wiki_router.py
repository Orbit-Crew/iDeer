"""HTTP contract of the controlled wiki surface (#118).

Generation and reading ride the same resource authorization chain as every
knowledge intent: a hidden KnowledgeBase reads as 404, a non-modifiable one
answers 403 on generate while department members may still read pages, and
the responses carry the frozen revision identity, per-page progress, and
source bindings verbatim from the stored rows. A page body is only ever
served through the per-page read, and only for pages of this revision's
frozen manifest.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

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

DEVICE_ID = "device-118-router"
GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()
POLICY = "乙组件的检修手册由检修班组维护。\n".encode()
GUIDE_PAGE = {"title": "甲零件与乙组件", "body": "# 甲零件与乙组件\n\n甲零件属于乙组件，乙组件由甲零件与螺栓构成。"}
POLICY_PAGE = {"title": "检修手册", "body": "# 检修手册\n\n乙组件的检修手册由检修班组维护。"}


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


def _fixed_writer():
    async def write(document_text: str) -> dict:
        if "乙组件" in document_text and "甲零件" in document_text:
            return dict(GUIDE_PAGE)
        return dict(POLICY_PAGE)

    return write


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
        text = self.documents.get(entry["document_id"])
        if text is None:
            result = {"document_id": entry["document_id"], "missing": True, "reason": "content_drift"}
        else:
            result = {"document_id": entry["document_id"], "filename": entry["filename"], "content_hash": entry["content_hash"], "text": text}
        from types import SimpleNamespace

        return SimpleNamespace(task_id=str(uuid.uuid4()), status=self._completed, receipt=None, tool_call_id="", error_code=None, result=result)

    def get_task(self, task_id):
        raise AssertionError("fake broker tasks settle immediately")


class Harness:
    def __init__(self, tmp_path: Path, *, broker: FakeBroker) -> None:
        self.tmp_path = tmp_path
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'wiki-router.db'}")
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
            wiki_writer=_fixed_writer(),
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

    async def seed_local_revision(self, entries: list[dict]) -> tuple[str, str, KnowledgeRevision]:
        async with self.factory() as session:
            kb = await ResourceService(session, _actor()).create_resource(
                resource_type="knowledge_base",
                slug=f"wiki-router-kb-{uuid.uuid4().hex[:8]}",
                display_name="wiki-router-kb",
                storage_kind="database",
            )
            kb.latest_version = 1
            kb.draft_revision = 1
            session.add(
                ResourceVersion(
                    id=str(uuid.uuid4()),
                    resource_id=kb.id,
                    version=1,
                    content_hash=hashlib.sha256(b"wiki-router-kb").hexdigest(),
                    storage_key=f"knowledge_bases/{kb.id}",
                    scan_result={},
                    content={"description": "wiki-router-kb"},
                    created_by=kb.owner_id,
                )
            )
            payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
                kb.id,
                documents=entries,
                device_id=DEVICE_ID,
            )
            await session.commit()
            revision = await session.get(KnowledgeRevision, str(payload["id"]))
            assert revision is not None
            return str(kb.id), str(kb.owner_id), revision


async def _noop_audit(*args, **kwargs) -> None:
    return None


def _guide_entry() -> dict:
    return {
        "filename": "guide.txt",
        "content_hash": hashlib.sha256(GUIDE).hexdigest(),
        "size_bytes": len(GUIDE),
        "mime_type": "text/plain",
    }


def _policy_entry() -> dict:
    return {
        "filename": "policy.txt",
        "content_hash": hashlib.sha256(POLICY).hexdigest(),
        "size_bytes": len(POLICY),
        "mime_type": "text/plain",
    }


@pytest.fixture
def harness(tmp_path):
    broker = FakeBroker(documents={})
    instance = Harness(tmp_path, broker=broker)
    kb_id, owner_id, revision = asyncio.run(instance.seed_local_revision([_guide_entry(), _policy_entry()]))
    instance.kb_id = kb_id
    instance.revision_id = str(revision.id)
    instance.revision = revision
    instance.broker = broker
    try:
        yield instance
    finally:
        asyncio.run(instance.engine.dispose())


def _fill_broker_documents(harness: Harness) -> None:
    for entry in harness.revision.manifest_json:
        text = GUIDE if entry["filename"] == "guide.txt" else POLICY
        harness.broker.documents[str(entry["document_id"])] = text.decode()


def test_owner_generates_reads_page_list_and_one_page(harness) -> None:
    _fill_broker_documents(harness)
    client = harness.client()
    generated = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "completed"
    assert body["revision_no"] >= 1
    assert body["generated"] == 2 and body["failed"] == 0 and body["skipped"] == 0

    view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    assert view.status_code == 200
    listed = view.json()
    assert listed["status"] == "completed"
    assert listed["manifest_hash"]
    titles = {row["filename"]: row["title"] for row in listed["pages"]}
    assert titles == {"guide.txt": GUIDE_PAGE["title"], "policy.txt": POLICY_PAGE["title"]}
    digests = {row["filename"]: row["content_hash"] for row in listed["pages"]}
    assert digests["guide.txt"] == hashlib.sha256(GUIDE).hexdigest()
    # The list never carries page bodies.
    assert all("body" not in row for row in listed["pages"])

    guide_page = next(row for row in listed["pages"] if row["filename"] == "guide.txt")
    page = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/pages/{guide_page['document_id']}")
    assert page.status_code == 200
    page_body = page.json()
    assert page_body["title"] == GUIDE_PAGE["title"]
    assert page_body["body"] == GUIDE_PAGE["body"]
    assert page_body["content_hash"] == hashlib.sha256(GUIDE).hexdigest()
    assert page_body["status"] == "completed"
    assert page_body["revision_id"] == harness.revision_id


def test_page_read_is_404_outside_the_frozen_manifest(harness) -> None:
    _fill_broker_documents(harness)
    client = harness.client()
    assert client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200
    view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    other_document = str(uuid.uuid4())
    leaked = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/pages/{other_document}")
    assert leaked.status_code == 404
    assert other_document not in view.text


def test_other_account_cannot_see_or_generate(harness) -> None:
    _fill_broker_documents(harness)
    owner = harness.client()
    assert owner.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200

    stranger = harness.client(user_id="stranger")
    assert stranger.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 404
    assert stranger.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 404
    page = stranger.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/pages/{uuid.uuid4()}")
    assert page.status_code == 404


def test_department_member_reads_but_cannot_generate(harness) -> None:
    _fill_broker_documents(harness)

    async def _make_department_visible() -> None:
        async with harness.factory() as session:
            resource = await session.get(Resource, harness.kb_id)
            resource.visibility = "department"
            resource.scope_department_id = "dept-118"
            await session.commit()

    asyncio.run(_make_department_visible())
    member = harness.client(user_id="colleague", department_id="dept-118")
    assert member.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200
    assert member.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 403


def test_unknown_revision_is_404(harness) -> None:
    client = harness.client()
    assert client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{uuid.uuid4()}/wiki").status_code == 404


def test_partial_skip_is_visible_and_retry_completes_without_mixing(harness) -> None:
    """One drifted document skips with its fixed category; the retry re-reads
    every source at its frozen digest and never rewrites the revision."""

    # The device still holds guide.txt at its frozen digest; policy.txt drifted.
    async def _drift() -> None:
        async with harness.factory() as session:
            revision = await session.get(KnowledgeRevision, harness.revision_id)
            guide_document = next(entry for entry in revision.manifest_json if entry["filename"] == "guide.txt")
            harness.broker.documents[str(guide_document["document_id"])] = GUIDE.decode()

    asyncio.run(_drift())
    client = harness.client()
    first = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "partial"
    assert body["generated"] == 1 and body["skipped"] == 1 and body["failed"] == 0
    statuses = {row["filename"]: (row["status"], row["error_code"]) for row in body["pages"]}
    assert statuses["guide.txt"] == ("completed", None)
    assert statuses["policy.txt"][0] == "skipped"
    assert statuses["policy.txt"][1] == "GRAPH_CONTENT_DRIFTED"

    # A drifted page has no readable body.
    policy_page = next(row for row in body["pages"] if row["filename"] == "policy.txt")
    skipped = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/pages/{policy_page['document_id']}")
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped" and skipped.json()["body"] == ""

    # The device recovers; the retry completes and the frozen basis stands.
    _fill_broker_documents(harness)
    frozen_hash = harness.revision.manifest_hash
    second = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    assert second.status_code == 200
    assert second.json()["status"] == "completed"
    assert harness.revision.manifest_hash == frozen_hash
    view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    assert {row["filename"]: row["status"] for row in view.json()["pages"]} == {"guide.txt": "completed", "policy.txt": "completed"}


def test_wiki_pages_are_isolated_between_revisions(harness) -> None:
    _fill_broker_documents(harness)
    client = harness.client()
    assert client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200

    async def _second_revision() -> None:
        async with harness.factory() as session:
            kb = await session.get(Resource, harness.kb_id)
            payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
                kb.id,
                documents=[_policy_entry()],
                device_id=DEVICE_ID,
            )
            await session.commit()
            harness.second_revision_id = str(payload["id"])
            revision = await session.get(KnowledgeRevision, harness.second_revision_id)
            harness.second_documents = {str(entry["document_id"]): POLICY.decode() for entry in revision.manifest_json}

    asyncio.run(_second_revision())
    harness.broker.documents.update(harness.second_documents)
    assert client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.second_revision_id}/wiki").status_code == 200

    first_view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").json()
    second_view = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.second_revision_id}/wiki").json()
    assert first_view["revision_id"] == harness.revision_id
    assert second_view["revision_id"] == harness.second_revision_id
    assert first_view["manifest_hash"] != second_view["manifest_hash"]
    assert {row["title"] for row in first_view["pages"]} == {GUIDE_PAGE["title"], POLICY_PAGE["title"]}
    assert {row["title"] for row in second_view["pages"]} == {POLICY_PAGE["title"]}
