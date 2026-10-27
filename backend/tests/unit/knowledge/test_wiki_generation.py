"""Server-orchestrated wiki generation and page reading for one frozen revision (#118).

The wiki mirrors the controlled graph idioms (#116/#117): the Server
orchestrates every model call, a device never bulk-uploads its library —
material rides the shared frozen-identity dispatch one document at a time,
re-verified against the frozen SHA-256 on both ends. One wiki page per
frozen document is bound to the KB/Revision/document source; progress,
skips, and partial failures are honest per-page records; a retry never
mixes sources or overrides the frozen basis; another revision's or another
account's pages never appear here.
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
    GRAPH_DOCUMENT_NOT_TEXT,
    GRAPH_MATERIAL_REJECTED,
)
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeDocument, KnowledgeRevision
from app.agentplatform.knowledge.wiki_generation import (
    MAX_WIKI_BODY_CHARS,
    WIKI_MODEL_OUTPUT_INVALID,
    KnowledgeWikiGenerationService,
    normalize_model_wiki,
)
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

DEVICE_ID = "device-118"
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


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[tuple[AsyncSession, async_sessionmaker, Path]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'wiki-generation.db'}")
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
        provider_doc_map_json={document_id: "provider-doc-118"},
        document_count=1,
        provider_dataset_id="dataset-118",
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
        self.missing_reason = missing_reason
        self.connections: dict[str, FakeConnection] = {}
        if online:
            self.connections[DEVICE_ID] = FakeConnection(DEVICE_ID, owner_id=owner_id)
        self.documents = documents or {}
        self.dispatched: list[dict] = []

    async def send_task(self, *, device_id, operation, path, run_id, tool_call_id, payload_extra=None, **kwargs):
        assert operation == "local.knowledge.material"
        arguments = (payload_extra or {})["arguments"]
        self.dispatched.append(dict(device_id=device_id, run_id=run_id, arguments=arguments))
        requested = arguments["documents"]
        assert len(requested) == 1, "material dispatch must request exactly one document"
        entry = requested[0]
        text = self.documents.get(entry["document_id"])
        if text is None:
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


def _fixed_writer():
    """The server-driven model call stand-in: deterministic per material.

    The wiki page is derived from the fixed document content, not invented
    by this file; wording needs not match the source verbatim (#118 AC4).
    """

    async def write(document_text: str) -> dict:
        if "乙组件" in document_text and "甲零件" in document_text:
            return dict(GUIDE_PAGE)
        return dict(POLICY_PAGE)

    return write


def _local_entries() -> list[dict]:
    return [
        {
            "filename": "guide.txt",
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
            "size_bytes": len(GUIDE),
            "mime_type": "text/plain",
        }
    ]


async def _local_service(session, factory, *, broker=None, writer=None, user_id="owner") -> KnowledgeWikiGenerationService:
    return KnowledgeWikiGenerationService(
        session,
        _actor(user_id),
        writer=writer or _fixed_writer(),
        broker_factory=lambda: broker if broker is not None else FakeBroker(documents={}),
    )


# --- Slice A: server-orchestrated generation over authorized material only ----


@pytest.mark.anyio
async def test_generation_is_server_orchestrated_and_requests_one_document_at_a_time(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)

    result = await service.generate(kb.id, revision.id)

    assert result["status"] == "completed"
    assert result["generated"] == 1 and result["failed"] == 0 and result["skipped"] == 0
    # One broker task per frozen document, frozen identity fields only: the
    # device answers the request, it never uploads its library.
    assert len(broker.dispatched) == 1
    dispatched = broker.dispatched[0]
    assert dispatched["device_id"] == DEVICE_ID
    assert dispatched["run_id"].startswith("knowledge-wiki:")
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
    kb = await _seed_resource(session, slug="wiki-provider-kb")
    monkeypatch.setattr("app.agentplatform.knowledge.graph_generation.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    revision = await _seed_provider_revision(session, kb, tmp_path)

    def _fail_broker():
        raise AssertionError("provider material must never touch the device broker")

    service = KnowledgeWikiGenerationService(session, _actor(), writer=_fixed_writer(), broker_factory=_fail_broker)
    result = await service.generate(kb.id, revision.id)

    assert result["status"] == "completed"
    assert result["pages"][0]["filename"] == "policy.txt"


# --- Slice B: pages are bound to KB/Revision and their permissions ------------


@pytest.mark.anyio
async def test_view_projects_pages_and_sources_with_frozen_bindings(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-bound-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)
    await service.generate(kb.id, revision.id)

    view = await service.view(kb.id, revision.id)

    assert view["knowledge_base_id"] == kb.id
    assert view["revision_id"] == revision.id
    assert view["revision_no"] == revision.revision_no
    assert view["manifest_hash"] == revision.manifest_hash
    assert view["status"] == "completed"
    assert view["pages"] == [
        {
            "document_id": document_id,
            "filename": "guide.txt",
            "title": GUIDE_PAGE["title"],
            "content_hash": hashlib.sha256(GUIDE).hexdigest(),
            "status": "completed",
            "error_code": None,
        }
    ]
    # The stored page body derives from the frozen material; the wording is
    # the model's, the facts are the document's (#118 AC4).
    page = await service.read_page(kb.id, revision.id, document_id)
    assert page["title"] == GUIDE_PAGE["title"]
    assert "甲零件属于乙组件" in page["body"]
    assert page["content_hash"] == hashlib.sha256(GUIDE).hexdigest()
    assert page["revision_id"] == revision.id and page["manifest_hash"] == revision.manifest_hash


@pytest.mark.anyio
async def test_wikis_are_isolated_between_revisions(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-isolation-kb")
    first = await _register_local_revision(session, kb, _local_entries())
    second = await _register_local_revision(
        session,
        kb,
        [
            {
                "filename": "guide.txt",
                "content_hash": hashlib.sha256(POLICY).hexdigest(),
                "size_bytes": len(POLICY),
                "mime_type": "text/plain",
            }
        ],
    )

    first_generation = KnowledgeWikiGenerationService(
        session,
        _actor(),
        writer=_fixed_writer(),
        broker_factory=lambda: FakeBroker(documents={first.manifest_json[0]["document_id"]: GUIDE.decode()}),
    )
    await first_generation.generate(kb.id, first.id)
    second_generation = KnowledgeWikiGenerationService(
        session,
        _actor(),
        writer=_fixed_writer(),
        broker_factory=lambda: FakeBroker(documents={second.manifest_json[0]["document_id"]: POLICY.decode()}),
    )
    await second_generation.generate(kb.id, second.id)

    viewer = KnowledgeWikiGenerationService(session, _actor(), writer=_fixed_writer(), broker_factory=lambda: FakeBroker())
    first_view = await viewer.view(kb.id, first.id)
    second_view = await viewer.view(kb.id, second.id)
    # Same filename in both revisions, but each page stays bound to its own
    # frozen revision, digest, and content: no cross-revision bleed.
    assert first_view["revision_id"] == first.id and second_view["revision_id"] == second.id
    assert first_view["manifest_hash"] != second_view["manifest_hash"]
    assert first_view["pages"][0]["title"] == GUIDE_PAGE["title"]
    assert second_view["pages"][0]["title"] == POLICY_PAGE["title"]
    assert first_view["pages"][0]["content_hash"] == hashlib.sha256(GUIDE).hexdigest()
    assert second_view["pages"][0]["content_hash"] == hashlib.sha256(POLICY).hexdigest()
    first_page = await viewer.read_page(kb.id, first.id, first.manifest_json[0]["document_id"])
    assert "甲零件属于乙组件" in first_page["body"]


@pytest.mark.anyio
async def test_other_account_cannot_view_or_generate(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-private-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    service = await _local_service(session, factory, broker=FakeBroker(documents={document_id: GUIDE.decode()}))
    await service.generate(kb.id, revision.id)
    await session.commit()

    outsider = KnowledgeWikiGenerationService(session, _actor("stranger"), writer=_fixed_writer(), broker_factory=lambda: FakeBroker())
    with pytest.raises(ResourceNotFound):
        await outsider.view(kb.id, revision.id)
    with pytest.raises(ResourceNotFound):
        await outsider.read_page(kb.id, revision.id, document_id)
    with pytest.raises(ResourceNotFound):
        await outsider.generate(kb.id, revision.id)


def _department_reader() -> ResourceActor:
    return ResourceActor(
        user_id="reader",
        department_id="dept-118",
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


@pytest.mark.anyio
async def test_department_visibility_can_read_but_not_generate(store) -> None:
    """Department-visible KB: members read the wiki; generation stays owner-only."""

    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-shared-kb")
    kb.visibility = "department"
    kb.scope_department_id = "dept-118"
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    service = await _local_service(session, factory, broker=FakeBroker(documents={document_id: GUIDE.decode()}))
    await service.generate(kb.id, revision.id)
    await session.commit()

    reader = KnowledgeWikiGenerationService(session, _department_reader(), writer=_fixed_writer(), broker_factory=lambda: FakeBroker())
    view = await reader.view(kb.id, revision.id)
    assert view["status"] == "completed"
    page = await reader.read_page(kb.id, revision.id, document_id)
    assert page["status"] == "completed" and page["body"]
    with pytest.raises(ResourcePermissionDenied):
        await reader.generate(kb.id, revision.id)


@pytest.mark.anyio
async def test_unknown_or_out_of_revision_document_page_is_invisible(store) -> None:
    """A page id outside this revision's frozen manifest reads as not-found:
    no titles, no bodies, no structure leaks."""

    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-leak-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    service = await _local_service(session, factory, broker=FakeBroker(documents={document_id: GUIDE.decode()}))
    await service.generate(kb.id, revision.id)
    await session.commit()

    with pytest.raises(ResourceNotFound):
        await service.read_page(kb.id, revision.id, str(uuid.uuid4()))
    with pytest.raises(ResourceNotFound):
        await service.read_page(kb.id, revision.id, "not-a-document")


@pytest.mark.anyio
async def test_revision_of_another_kb_is_invisible(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-kb-a")
    other = await _seed_resource(session, slug="wiki-kb-b")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory)
    with pytest.raises(ResourceNotFound):
        await service.generate(other.id, revision.id)
    with pytest.raises(ResourceNotFound):
        await service.view(other.id, revision.id)


@pytest.mark.anyio
async def test_view_before_generation_reports_not_generated(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-fresh-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory)

    view = await service.view(kb.id, revision.id)
    assert view["status"] == "not_generated"
    assert view["generated"] == 0 and view["failed"] == 0 and view["skipped"] == 0
    # The frozen documents stay listed as pending pages: the entry shows what
    # a generation would cover, and none of it pretends to exist.
    assert [row["status"] for row in view["pages"]] == ["not_generated"]
    page = await service.read_page(kb.id, revision.id, revision.manifest_json[0]["document_id"])
    assert page["status"] == "not_generated" and page["body"] == "" and page["title"] == ""


# --- Slice C: honest progress, skips, and partial failures --------------------


@pytest.mark.anyio
async def test_device_material_drift_is_skipped_and_successes_survive(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-partial-kb")
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
    assert result["generated"] == 1 and result["failed"] == 0 and result["skipped"] == 1
    pages = {row["filename"]: row for row in result["pages"]}
    assert pages["guide.txt"]["status"] == "completed"
    assert pages["policy.txt"]["status"] == "skipped"
    assert pages["policy.txt"]["error_code"] == GRAPH_CONTENT_DRIFTED

    view = await service.view(kb.id, revision.id)
    assert view["status"] == "partial"
    assert {row["filename"]: row["status"] for row in view["pages"]} == {"guide.txt": "completed", "policy.txt": "skipped"}
    # The completed page keeps its readable body; the skipped page has none.
    done = await service.read_page(kb.id, revision.id, document_ids["guide.txt"])
    assert done["body"]
    skipped = await service.read_page(kb.id, revision.id, document_ids["policy.txt"])
    assert skipped["status"] == "skipped" and skipped["body"] == "" and skipped["error_code"] == GRAPH_CONTENT_DRIFTED


@pytest.mark.anyio
async def test_device_offline_is_a_skipped_page(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-offline-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory, broker=FakeBroker(online=False))

    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["pages"][0]["status"] == "skipped"
    assert result["pages"][0]["error_code"] == GRAPH_DEVICE_UNAVAILABLE


@pytest.mark.anyio
async def test_returned_material_must_match_the_frozen_digest(store) -> None:
    """A buggy or compromised device cannot inject substitute material."""

    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-reject-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: "被替换的内容"})
    service = await _local_service(session, factory, broker=broker)

    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["pages"][0]["error_code"] == GRAPH_MATERIAL_REJECTED


@pytest.mark.anyio
async def test_model_failure_is_a_failed_page(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-model-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]

    async def bad_writer(document_text: str) -> dict:
        return {"unrelated": True}

    service = await _local_service(
        session,
        factory,
        broker=FakeBroker(documents={document_id: GUIDE.decode()}),
        writer=bad_writer,
    )
    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["pages"][0]["status"] == "failed"
    assert result["pages"][0]["error_code"] == WIKI_MODEL_OUTPUT_INVALID


@pytest.mark.anyio
async def test_all_skipped_reports_failed_not_completed(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-allskip-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    service = await _local_service(session, factory, broker=FakeBroker(documents={}))

    result = await service.generate(kb.id, revision.id)
    assert result["status"] == "failed"
    assert result["skipped"] == 1 and result["generated"] == 0


@pytest.mark.asyncio
async def test_non_text_material_names_a_fixed_category(store, monkeypatch, tmp_path) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-binary-kb")
    monkeypatch.setattr("app.agentplatform.knowledge.graph_generation.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    revision = await _seed_provider_revision(session, kb, tmp_path)
    # The stored bytes match the frozen digest but are not text: the fixed
    # not-text category applies, never a crash or an invented page.
    binary = b"\xff\xfe\x00binary"
    revision.manifest_json = [{**revision.manifest_json[0], "content_hash": hashlib.sha256(binary).hexdigest()}]
    destination = next((tmp_path / "knowledge-documents" / kb.id).glob("*-policy.txt"))
    destination.write_bytes(binary)
    await session.commit()

    service = KnowledgeWikiGenerationService(session, _actor(), writer=_fixed_writer(), broker_factory=lambda: FakeBroker())
    result = await service.generate(kb.id, revision.id)
    assert result["pages"][0]["status"] == "skipped"
    assert result["pages"][0]["error_code"] == GRAPH_DOCUMENT_NOT_TEXT


# --- Slice D: retry and the frozen basis --------------------------------------


@pytest.mark.anyio
async def test_retry_never_overrides_the_frozen_basis_and_completes_skipped_pages(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-retry-kb")
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
    frozen_hash = revision.manifest_hash
    frozen_manifest = [dict(entry) for entry in revision.manifest_json]
    broker = FakeBroker(documents={document_ids["guide.txt"]: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)
    first = await service.generate(kb.id, revision.id)
    assert first["status"] == "partial"

    # The device comes back with both documents; the retry re-reads every
    # source at its frozen digest and never rewrites the revision itself.
    broker.documents[document_ids["policy.txt"]] = POLICY.decode()
    second = await service.generate(kb.id, revision.id)

    assert second["status"] == "completed"
    await session.refresh(revision)
    assert revision.manifest_hash == frozen_hash
    assert revision.manifest_json == frozen_manifest
    view = await service.view(kb.id, revision.id)
    assert {row["filename"]: row["status"] for row in view["pages"]} == {"guide.txt": "completed", "policy.txt": "completed"}
    page = await service.read_page(kb.id, revision.id, document_ids["policy.txt"])
    assert page["status"] == "completed" and "检修班组" in page["body"]


@pytest.mark.anyio
async def test_retry_keeps_each_revision_its_own_sources(store) -> None:
    """A newer revision existing on the same KB never bleeds into an older
    revision's retry: sources, digests, and pages stay per-revision."""

    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-two-rev-kb")
    first = await _register_local_revision(session, kb, _local_entries())
    first_document = first.manifest_json[0]["document_id"]
    second = await _register_local_revision(
        session,
        kb,
        [
            {
                "filename": "guide.txt",
                "content_hash": hashlib.sha256(POLICY).hexdigest(),
                "size_bytes": len(POLICY),
                "mime_type": "text/plain",
            }
        ],
    )
    second_document = second.manifest_json[0]["document_id"]
    documents = {first_document: GUIDE.decode(), second_document: POLICY.decode()}
    service = KnowledgeWikiGenerationService(session, _actor(), writer=_fixed_writer(), broker_factory=lambda: FakeBroker(documents=documents))
    await service.generate(kb.id, first.id)
    await service.generate(kb.id, second.id)
    # Retry the FIRST revision after the second exists.
    await service.generate(kb.id, first.id)

    first_view = await service.view(kb.id, first.id)
    assert first_view["pages"][0]["document_id"] == first_document
    assert first_view["pages"][0]["content_hash"] == hashlib.sha256(GUIDE).hexdigest()
    assert first_view["pages"][0]["title"] == GUIDE_PAGE["title"]
    second_view = await service.view(kb.id, second.id)
    assert second_view["pages"][0]["content_hash"] == hashlib.sha256(POLICY).hexdigest()
    assert second_view["pages"][0]["title"] == POLICY_PAGE["title"]


@pytest.mark.anyio
async def test_regeneration_replaces_previous_pages(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-regen-kb")
    revision = await _register_local_revision(session, kb, _local_entries())
    document_id = revision.manifest_json[0]["document_id"]
    broker = FakeBroker(documents={document_id: GUIDE.decode()})
    service = await _local_service(session, factory, broker=broker)
    first = await service.generate(kb.id, revision.id)
    second = await service.generate(kb.id, revision.id)
    assert first["status"] == second["status"] == "completed"
    view = await service.view(kb.id, revision.id)
    assert len(view["pages"]) == 1


@pytest.mark.anyio
async def test_empty_revision_is_refused(store) -> None:
    session, factory, _tmp = store
    kb = await _seed_resource(session, slug="wiki-empty-kb")
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


# --- Slice E: model output normalization contract ------------------------------


def test_normalize_model_wiki_accepts_bounded_shape() -> None:
    normalized = normalize_model_wiki({"title": "  甲零件与乙组件  ", "body": "  # 正文\n\n事实。\n"})
    assert normalized == {"title": "甲零件与乙组件", "body": "# 正文\n\n事实。"}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "wiki",
        [],
        {},
        {"title": "标题"},
        {"body": "正文"},
        {"title": "", "body": "正文"},
        {"title": "标题", "body": ""},
        {"title": "标题", "body": "   "},
        {"title": "标\x00题", "body": "正文"},
        {"title": "标题", "body": "正\x00文"},
        {"title": "x" * 201, "body": "正文"},
        {"title": "标题", "body": "长" * (MAX_WIKI_BODY_CHARS + 1)},
        {"title": 7, "body": "正文"},
        {"title": "标题", "body": ["正文"]},
    ],
)
def test_normalize_model_wiki_rejects_malformed_output(raw) -> None:
    with pytest.raises(ValueError):
        normalize_model_wiki(raw)


def test_normalize_model_wiki_enforces_bounds() -> None:
    normalized = normalize_model_wiki({"title": "标题", "body": "长" * MAX_WIKI_BODY_CHARS})
    assert len(normalized["body"]) == MAX_WIKI_BODY_CHARS
