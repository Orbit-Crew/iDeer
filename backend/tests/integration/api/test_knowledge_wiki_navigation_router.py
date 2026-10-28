"""HTTP contract of the wiki index navigation surface (#119).

The navigation read is a projection of artifacts that already exist for one
frozen revision: the #118 page list, the links its completed bodies declare,
the inverted backlinks, and the #116 graph rows as the association graph.
Everything rides the same resource authorization chain as the wiki itself —
a hidden KnowledgeBase reads as 404, a non-modifiable one answers 403 on
generate while department members may still navigate — and no other
revision's titles, links, or relations can appear. A link target that names
nothing in this revision is an explicit missing entry, and a skipped target
names its honest page status instead of pretending to be readable.
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
from app.agentplatform.knowledge.models import KnowledgeGraphArtifact, KnowledgeRevision
from app.agentplatform.rbac_models import UserModel
from app.agentplatform.resource_models import Resource, ResourceVersion
from app.agentplatform.resources.service import ResourceAction, ResourceActor, ResourceService
from app.gateway.authz import get_current_rbac_user
from app.gateway.knowledge_seam import knowledge_facade
from app.gateway.routers import resources
from deerflow.persistence.base import Base

DEVICE_ID = "device-119-router"
GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()
POLICY = "乙组件的检修手册由检修班组维护。\n".encode()
EXTRA = "第三份材料描述备用方案。\n".encode()
GUIDE_TITLE = "甲零件与乙组件"
POLICY_TITLE = "检修手册"
EXTRA_TITLE = "第二版新页"
GUIDE_PAGE = {
    "title": GUIDE_TITLE,
    "body": f"# {GUIDE_TITLE}\n\n甲零件属于乙组件，乙组件由甲零件与螺栓构成。\n\n相关：[[policy.txt]]、[[{POLICY_TITLE}]] 与 [[幽灵附录]]。外部 [参考](https://example.com) 不算。",
}
POLICY_PAGE = {
    "title": POLICY_TITLE,
    "body": f"# {POLICY_TITLE}\n\n乙组件的检修手册由检修班组维护。\n\n回看 [[{GUIDE_TITLE}]]。",
}
EXTRA_PAGE = {"title": EXTRA_TITLE, "body": f"# {EXTRA_TITLE}\n\n备用方案另见 [[policy.txt]]。"}
GHOST_TARGET = "幽灵附录"


def _actor(user_id: str = "owner") -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=None,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


def _fixed_writer():
    async def write(document_text: str) -> dict:
        if "甲零件" in document_text:
            return dict(GUIDE_PAGE)
        if "备用方案" in document_text:
            return dict(EXTRA_PAGE)
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
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'wiki-nav-router.db'}")
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
                slug=f"wiki-nav-router-kb-{uuid.uuid4().hex[:8]}",
                display_name="wiki-nav-router-kb",
                storage_kind="database",
            )
            kb.latest_version = 1
            kb.draft_revision = 1
            session.add(
                ResourceVersion(
                    id=str(uuid.uuid4()),
                    resource_id=kb.id,
                    version=1,
                    content_hash=hashlib.sha256(b"wiki-nav-router-kb").hexdigest(),
                    storage_key=f"knowledge_bases/{kb.id}",
                    scan_result={},
                    content={"description": "wiki-nav-router-kb"},
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

    async def seed_graph_artifacts(self, revision_id: str) -> None:
        """Stored #116 rows: guide completed, policy failed at a fixed category."""

        async with self.factory() as session:
            revision = await session.get(KnowledgeRevision, revision_id)
            for entry in revision.manifest_json:
                completed = entry["filename"] == "guide.txt"
                session.add(
                    KnowledgeGraphArtifact(
                        id=str(uuid.uuid4()),
                        knowledge_base_id=revision.knowledge_base_id,
                        revision_id=revision.id,
                        revision_no=revision.revision_no,
                        manifest_hash=revision.manifest_hash,
                        document_id=str(entry["document_id"]),
                        document_filename=str(entry.get("filename") or ""),
                        document_content_hash=str(entry.get("content_hash") or ""),
                        status="completed" if completed else "failed",
                        entities_json=[{"name": "甲零件", "type": "零件"}, {"name": "乙组件", "type": "组件"}] if completed else [],
                        relations_json=[{"source": "甲零件", "target": "乙组件", "relation": "属于"}] if completed else [],
                        entity_count=2 if completed else 0,
                        relation_count=1 if completed else 0,
                        error_code=None if completed else "GRAPH_DOCUMENT_TOO_LARGE",
                        error_message=None,
                        generated_by="owner",
                    )
                )
            await session.commit()


async def _noop_audit(*args, **kwargs) -> None:
    return None


def _entry(filename: str, content: bytes) -> dict:
    return {
        "filename": filename,
        "content_hash": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "mime_type": "text/plain",
    }


@pytest.fixture
def harness(tmp_path):
    broker = FakeBroker(documents={})
    instance = Harness(tmp_path, broker=broker)
    kb_id, owner_id, revision = asyncio.run(instance.seed_local_revision([_entry("guide.txt", GUIDE), _entry("policy.txt", POLICY)]))
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
        text = {"guide.txt": GUIDE, "policy.txt": POLICY, "extra.txt": EXTRA}.get(entry["filename"], b"")
        harness.broker.documents[str(entry["document_id"])] = text.decode()


def _navigation(client: TestClient, harness: Harness) -> dict:
    response = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/navigation")
    assert response.status_code == 200
    return response.json()


def test_owner_navigates_links_backlinks_and_associations(harness) -> None:
    _fill_broker_documents(harness)
    client = harness.client()
    assert client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200
    asyncio.run(harness.seed_graph_artifacts(harness.revision_id))

    index = _navigation(client, harness)
    assert index["knowledge_base_id"] == harness.kb_id
    assert index["revision_id"] == harness.revision_id
    assert index["manifest_hash"] == harness.revision.manifest_hash
    assert index["status"] == "completed" and index["generated"] == 2 and index["failed"] == 0 and index["skipped"] == 0

    guide_entry = next(entry for entry in harness.revision.manifest_json if entry["filename"] == "guide.txt")
    policy_entry = next(entry for entry in harness.revision.manifest_json if entry["filename"] == "policy.txt")
    guide_row = next(row for row in index["pages"] if row["filename"] == "guide.txt")
    policy_row = next(row for row in index["pages"] if row["filename"] == "policy.txt")
    assert guide_row["title"] == GUIDE_TITLE and policy_row["title"] == POLICY_TITLE
    # The index never carries page bodies; bodies stay behind the #118 read.
    assert all("body" not in row for row in index["pages"])

    # Both link shapes to the policy page dedupe into one resolved link; the
    # ghost target stays an explicit missing entry; the external URL is gone.
    assert guide_row["links"] == [{"document_id": str(policy_entry["document_id"]), "title": POLICY_TITLE, "status": "completed"}]
    assert guide_row["missing_links"] == [GHOST_TARGET]
    assert "https://example.com" not in repr(index)
    # The link loop closes: policy links back by title, so each page names
    # the other as its backlink with the source's own title and status.
    assert policy_row["links"] == [{"document_id": str(guide_entry["document_id"]), "title": GUIDE_TITLE, "status": "completed"}]
    assert policy_row["backlinks"] == [{"document_id": str(guide_entry["document_id"]), "title": GUIDE_TITLE, "status": "completed"}]
    assert guide_row["backlinks"] == [{"document_id": str(policy_entry["document_id"]), "title": POLICY_TITLE, "status": "completed"}]

    # The association graph reuses the #116 rows with their frozen sources.
    associations = index["associations"]
    assert associations["status"] == "partial" and associations["generated"] == 1 and associations["failed"] == 1
    assert associations["relations"] == [
        {
            "source": "甲零件",
            "target": "乙组件",
            "relation": "属于",
            "document_id": str(guide_entry["document_id"]),
            "filename": "guide.txt",
            "content_hash": str(guide_entry["content_hash"]),
        }
    ]
    sources = {row["document_id"]: row for row in associations["sources"]}
    assert sources[str(guide_entry["document_id"])]["status"] == "completed"
    assert sources[str(policy_entry["document_id"])]["status"] == "failed"
    assert sources[str(policy_entry["document_id"])]["error_code"] == "GRAPH_DOCUMENT_TOO_LARGE"

    # Reading a linked target still goes through the #118 per-page read.
    page = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/pages/{policy_entry['document_id']}")
    assert page.status_code == 200 and page.json()["title"] == POLICY_TITLE


def test_navigation_permission_matrix(harness) -> None:
    _fill_broker_documents(harness)
    owner = harness.client()
    assert owner.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200
    asyncio.run(harness.seed_graph_artifacts(harness.revision_id))

    stranger = harness.client(user_id="stranger")
    assert stranger.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 404
    assert stranger.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/navigation").status_code == 404
    policy_entry = next(entry for entry in harness.revision.manifest_json if entry["filename"] == "policy.txt")
    assert stranger.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki/pages/{policy_entry['document_id']}").status_code == 404
    assert stranger.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 404

    async def _make_department_visible() -> None:
        async with harness.factory() as session:
            resource = await session.get(Resource, harness.kb_id)
            resource.visibility = "department"
            resource.scope_department_id = "dept-119"
            await session.commit()

    asyncio.run(_make_department_visible())
    member = harness.client(user_id="colleague", department_id="dept-119")
    member_index = _navigation(member, harness)
    # A department member navigates the same frozen scope: identical rows and
    # relations, and generation still rides the KB's modify boundary.
    assert {row["title"] for row in member_index["pages"]} == {GUIDE_TITLE, POLICY_TITLE}
    assert [row["relation"] for row in member_index["associations"]["relations"]] == ["属于"]
    assert member.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 403
    # Another revision is simply not this one.
    assert member.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{uuid.uuid4()}/wiki/navigation").status_code == 404


def test_missing_target_and_skipped_page_are_explicit(harness) -> None:
    # The device still holds guide.txt at its frozen digest; policy.txt drifted.
    async def _drift() -> None:
        async with harness.factory() as session:
            revision = await session.get(KnowledgeRevision, harness.revision_id)
            guide_document = next(entry for entry in revision.manifest_json if entry["filename"] == "guide.txt")
            harness.broker.documents[str(guide_document["document_id"])] = GUIDE.decode()

    asyncio.run(_drift())
    client = harness.client()
    generated = client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki")
    assert generated.status_code == 200
    assert generated.json()["status"] == "partial"

    index = _navigation(client, harness)
    assert index["status"] == "partial" and index["generated"] == 1 and index["skipped"] == 1
    policy_entry = next(entry for entry in harness.revision.manifest_json if entry["filename"] == "policy.txt")
    guide_row = next(row for row in index["pages"] if row["filename"] == "guide.txt")
    policy_row = next(row for row in index["pages"] if row["filename"] == "policy.txt")
    assert policy_row["status"] == "skipped" and policy_row["title"] == ""
    # The filename link still resolves to the frozen policy document, but
    # names the honest skipped status and never a title that would look
    # readable. The title-shaped link degrades to an explicit missing entry:
    # a skipped page has no title, so nothing may pretend it resolves.
    assert guide_row["links"] == [{"document_id": str(policy_entry["document_id"]), "title": "", "status": "skipped"}]
    assert guide_row["missing_links"] == [POLICY_TITLE, GHOST_TARGET]
    assert policy_row["backlinks"] == [{"document_id": guide_row["document_id"], "title": GUIDE_TITLE, "status": "completed"}]
    # No graph artifacts were generated: the associations say so instead of
    # inventing relations, and every source names its not_generated status.
    associations = index["associations"]
    assert associations["status"] == "not_generated"
    assert associations["entities"] == [] and associations["relations"] == []
    assert {row["status"] for row in associations["sources"]} == {"not_generated"}


def test_navigation_is_revision_bound_and_never_leaks_other_versions(harness) -> None:
    _fill_broker_documents(harness)
    client = harness.client()
    assert client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.revision_id}/wiki").status_code == 200
    asyncio.run(harness.seed_graph_artifacts(harness.revision_id))

    async def _second_revision() -> None:
        async with harness.factory() as session:
            kb = await session.get(Resource, harness.kb_id)
            payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
                kb.id,
                documents=[_entry("policy.txt", POLICY), _entry("extra.txt", EXTRA)],
                device_id=DEVICE_ID,
            )
            await session.commit()
            harness.second_revision_id = str(payload["id"])
            revision = await session.get(KnowledgeRevision, harness.second_revision_id)
            harness.second_documents = {str(entry["document_id"]): (POLICY if entry["filename"] == "policy.txt" else EXTRA).decode() for entry in revision.manifest_json}

    asyncio.run(_second_revision())
    harness.broker.documents.update(harness.second_documents)
    assert client.post(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.second_revision_id}/wiki").status_code == 200

    first = _navigation(client, harness)
    second_response = client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{harness.second_revision_id}/wiki/navigation")
    assert second_response.status_code == 200
    second = second_response.json()

    assert first["revision_id"] == harness.revision_id and second["revision_id"] == harness.second_revision_id
    assert first["manifest_hash"] == harness.revision.manifest_hash != second["manifest_hash"]
    # Each index lists exactly its own revision's manifest and its own pages.
    assert [row["filename"] for row in first["pages"]] == ["guide.txt", "policy.txt"]
    assert [row["filename"] for row in second["pages"]] == ["policy.txt", "extra.txt"]
    assert EXTRA_TITLE not in repr(first)
    # The second revision's policy page is its own row: it never shows the
    # first revision's guide page as a title, link, or backlink — its body's
    # title-shaped reference has nothing to resolve in this manifest and
    # stays an explicit missing entry quoting only the page's own text.
    assert GUIDE_TITLE not in {row["title"] for row in second["pages"]}
    second_policy = next(row for row in second["pages"] if row["filename"] == "policy.txt")
    assert second_policy["title"] == POLICY_TITLE
    assert second_policy["links"] == []
    assert second_policy["missing_links"] == [GUIDE_TITLE]
    # The second revision's extra page links to policy.txt and gets its
    # backlink from this revision's pages only.
    second_extra = next(row for row in second["pages"] if row["filename"] == "extra.txt")
    assert [link["document_id"] for link in second_extra["links"]] == [second_policy["document_id"]]
    assert [row["title"] for row in second_policy["backlinks"]] == [EXTRA_TITLE]
    # The old revision's association graph is untouched by the new version.
    assert [row["relation"] for row in first["associations"]["relations"]] == ["属于"]
    assert second["associations"]["status"] == "not_generated"


def test_unknown_revision_navigation_is_404(harness) -> None:
    client = harness.client()
    assert client.get(f"/api/resources/{harness.kb_id}/knowledge-revisions/{uuid.uuid4()}/wiki/navigation").status_code == 404
