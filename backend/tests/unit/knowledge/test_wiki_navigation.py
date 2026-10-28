"""Wiki index navigation: links, backlinks, and the association graph (#119).

The index is a deterministic projection of artifacts that already exist for
one frozen revision — the #118 pages and the #116 graph rows are read, never
re-generated. Links are extracted from the stored page bodies and resolved
only against this revision's frozen manifest (document id, filename) and its
own completed page titles; anything else is an explicit missing target, not
a fabricated accessible page. Backlinks invert the resolved links, and the
association graph reuses the stored graph artifacts with their frozen
document sources. Every entry rides the KB's own visibility chain, so no
other revision's or account's titles or relations can appear here.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.graph_generation import GRAPH_DOCUMENT_TOO_LARGE, STATUS_FAILED, STATUS_NOT_GENERATED
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.models import KnowledgeGraphArtifact, KnowledgeRevision, KnowledgeWikiPage
from app.agentplatform.knowledge.wiki_generation import STATUS_COMPLETED, STATUS_SKIPPED
from app.agentplatform.knowledge.wiki_navigation import (
    MAX_WIKI_LINK_TARGET_CHARS,
    MAX_WIKI_LINKS_PER_PAGE,
    KnowledgeWikiNavigationService,
    extract_wiki_links,
)
from app.agentplatform.resource_models import Resource, ResourceVersion
from app.agentplatform.resources.service import (
    ResourceAction,
    ResourceActor,
    ResourceNotFound,
    ResourceService,
)
from deerflow.persistence.base import Base

GUIDE = "甲零件属于乙组件。乙组件由甲零件与螺栓构成。\n".encode()
POLICY = "乙组件的检修手册由检修班组维护。\n".encode()
GUIDE_TITLE = "甲零件与乙组件"
POLICY_TITLE = "检修手册"
GUIDE_BODY = f"# {GUIDE_TITLE}\n\n甲零件属于乙组件，乙组件由甲零件与螺栓构成。\n\n参见 [[policy.txt]] 与 [[{POLICY_TITLE}]]。"
POLICY_BODY = f"# {POLICY_TITLE}\n\n乙组件的检修手册由检修班组维护。\n\n回看 [[{GUIDE_TITLE}]]。"


def _actor(user_id: str = "owner", department_id: str | None = None) -> ResourceActor:
    return ResourceActor(
        user_id=user_id,
        department_id=department_id,
        role="user",
        permissions=frozenset({ResourceAction.READ, ResourceAction.USE, ResourceAction.WRITE}),
    )


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[tuple[AsyncSession, async_sessionmaker]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'wiki-navigation.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


async def _seed_kb(session: AsyncSession, *, slug: str = "wiki-nav-kb", owner_id: str = "owner") -> Resource:
    resource = await ResourceService(session, _actor(owner_id)).create_resource(
        resource_type="knowledge_base",
        slug=f"{slug}-{uuid.uuid4().hex[:8]}",
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
    await session.commit()
    return resource


async def _register_revision(session: AsyncSession, kb: Resource, entries: list[dict]) -> KnowledgeRevision:
    payload = await KnowledgeLocalImportService(session, _actor(str(kb.owner_id))).register_local_import(
        kb.id,
        documents=entries,
        device_id="device-119",
    )
    await session.commit()
    revision = await session.get(KnowledgeRevision, str(payload["id"]))
    assert revision is not None
    return revision


def _entry(filename: str, content: bytes) -> dict:
    return {
        "filename": filename,
        "content_hash": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "mime_type": "text/plain",
    }


async def _store_page(
    session: AsyncSession,
    kb: Resource,
    revision: KnowledgeRevision,
    entry: dict,
    *,
    title: str,
    body: str,
    status: str = STATUS_COMPLETED,
    error_code: str | None = None,
) -> KnowledgeWikiPage:
    row = KnowledgeWikiPage(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_id=revision.id,
        revision_no=revision.revision_no,
        manifest_hash=revision.manifest_hash,
        document_id=str(entry["document_id"]),
        document_filename=str(entry.get("filename") or ""),
        document_content_hash=str(entry.get("content_hash") or ""),
        title=title if status == STATUS_COMPLETED else "",
        body=body if status == STATUS_COMPLETED else "",
        status=status,
        error_code=error_code,
        error_message=None,
        generated_by="owner",
    )
    session.add(row)
    await session.commit()
    return row


async def _rewrite_page(
    session: AsyncSession,
    revision: KnowledgeRevision,
    filename: str,
    *,
    title: str = "",
    body: str = "",
    status: str = STATUS_COMPLETED,
    error_code: str | None = None,
) -> None:
    """Overwrite one stored page in place (regeneration semantics)."""

    result = await session.execute(select(KnowledgeWikiPage).where(KnowledgeWikiPage.revision_id == revision.id))
    row = next(item for item in result.scalars() if item.document_filename == filename)
    row.title = title if status == STATUS_COMPLETED else ""
    row.body = body if status == STATUS_COMPLETED else ""
    row.status = status
    row.error_code = error_code
    await session.commit()


async def _store_graph_artifact(
    session: AsyncSession,
    kb: Resource,
    revision: KnowledgeRevision,
    entry: dict,
    *,
    entities: list[dict] | None = None,
    relations: list[dict] | None = None,
    status: str = STATUS_COMPLETED,
    error_code: str | None = None,
) -> KnowledgeGraphArtifact:
    row = KnowledgeGraphArtifact(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb.id,
        revision_id=revision.id,
        revision_no=revision.revision_no,
        manifest_hash=revision.manifest_hash,
        document_id=str(entry["document_id"]),
        document_filename=str(entry.get("filename") or ""),
        document_content_hash=str(entry.get("content_hash") or ""),
        status=status,
        entities_json=entities or [],
        relations_json=relations or [],
        entity_count=len(entities or []),
        relation_count=len(relations or []),
        error_code=error_code,
        error_message=None,
        generated_by="owner",
    )
    session.add(row)
    await session.commit()
    return row


async def _seed_linked_revision(session: AsyncSession) -> tuple[Resource, KnowledgeRevision, dict[str, dict]]:
    """One revision whose two pages link to each other by title and filename."""

    kb = await _seed_kb(session)
    revision = await _register_revision(session, kb, [_entry("guide.txt", GUIDE), _entry("policy.txt", POLICY)])
    entries = {str(entry["filename"]): entry for entry in revision.manifest_json}
    await _store_page(session, kb, revision, entries["guide.txt"], title=GUIDE_TITLE, body=GUIDE_BODY)
    await _store_page(session, kb, revision, entries["policy.txt"], title=POLICY_TITLE, body=POLICY_BODY)
    return kb, revision, entries


def test_extract_wiki_links_is_deterministic_and_internal_only() -> None:
    body = f"参见 [[policy.txt]] 与 [{POLICY_TITLE}](policy.txt)。\n外部引用 [官网](https://example.com/x) 与 [邮件](mailto:a@b.c) 不算。\n锚点 [跳转](#section) 与空链接 [[]]() 以及 [空](   ) 不算。\n重复 [[policy.txt]] 只算一次。"
    # Both link shapes name the same frozen filename; dedupe keeps one row.
    assert extract_wiki_links(body) == ["policy.txt"]
    assert extract_wiki_links("没有链接的正文") == []
    assert extract_wiki_links(f"[[{'x' * (MAX_WIKI_LINK_TARGET_CHARS + 1)}]]") == []


def test_extract_wiki_links_is_capped_per_page() -> None:
    body = " ".join(f"[[target-{index}]]" for index in range(MAX_WIKI_LINKS_PER_PAGE + 10))
    assert len(extract_wiki_links(body)) == MAX_WIKI_LINKS_PER_PAGE


@pytest.mark.anyio
async def test_index_resolves_links_by_filename_and_title_and_reports_missing(store) -> None:
    session, _factory = store
    kb, revision, entries = await _seed_linked_revision(session)
    guide_entry = entries["guide.txt"]
    guide_document_id = str(guide_entry["document_id"])

    first_index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    by_title = {row["title"]: row for row in first_index["pages"]}
    guide_row = by_title[GUIDE_TITLE]
    # Links resolve by filename and by title to the policy page.
    assert {link["document_id"] for link in guide_row["links"]} == {str(entries["policy.txt"]["document_id"])}
    assert all(link["status"] == STATUS_COMPLETED and link["title"] == POLICY_TITLE for link in guide_row["links"])
    assert guide_row["missing_links"] == []
    # Backlinks invert the resolved links: the policy page is pointed at by
    # the guide page, and the guide page by the policy page.
    policy_row = by_title[POLICY_TITLE]
    assert [row["document_id"] for row in policy_row["backlinks"]] == [guide_document_id]
    assert [row["document_id"] for row in guide_row["backlinks"]] == [str(entries["policy.txt"]["document_id"])]

    # A later revision freezes a different manifest; a link that names a real
    # document of the SAME KB still resolves only inside the named revision —
    # policy.txt is frozen in the first revision, not this one.
    third = await _register_revision(session, kb, [_entry("solo.txt", "独立材料。\n".encode())])
    solo_entry = next(entry for entry in third.manifest_json if entry["filename"] == "solo.txt")
    await _store_page(session, kb, third, solo_entry, title="独立页", body="指向 [[幽灵文档]] 与 [[policy.txt]]。")

    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, third.id)
    solo_row = index["pages"][0]
    assert solo_row["document_id"] == str(solo_entry["document_id"])
    # The ghost target is an explicit missing link, never a fabricated page;
    # policy.txt names nothing frozen in THIS revision, so it is missing here
    # too — revision 1's page for it never leaks into this index.
    assert solo_row["missing_links"] == ["幽灵文档", "policy.txt"]
    assert solo_row["links"] == []
    assert all(row["document_id"] != guide_document_id for row in index["pages"])
    assert index["status"] == STATUS_COMPLETED


@pytest.mark.anyio
async def test_index_reports_skipped_target_status_instead_of_a_readable_page(store) -> None:
    session, _factory = store
    kb, revision, entries = await _seed_linked_revision(session)
    # The policy page drifts: it becomes a skipped record with no body.
    await _rewrite_page(session, revision, "policy.txt", status=STATUS_SKIPPED, error_code=GRAPH_DOCUMENT_TOO_LARGE)

    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    by_title = {row["title"]: row for row in index["pages"]}
    assert index["status"] == "partial"
    policy_row = next(row for row in index["pages"] if row["filename"] == "policy.txt")
    assert policy_row["status"] == STATUS_SKIPPED and policy_row["error_code"] == GRAPH_DOCUMENT_TOO_LARGE
    assert policy_row["title"] == ""
    # The guide's link still resolves to the policy document, but names the
    # honest page status — nothing pretends the target is readable.
    guide_row = by_title[GUIDE_TITLE]
    assert [link["status"] for link in guide_row["links"]] == [STATUS_SKIPPED]
    assert all(link["title"] == "" for link in guide_row["links"])
    # The skipped page keeps its backlink visibility; reading it stays gated
    # by the #118 page read, which returns no body for a skipped page.
    assert [row["title"] for row in policy_row["backlinks"]] == [GUIDE_TITLE]


@pytest.mark.anyio
async def test_index_backlink_never_points_at_a_missing_target(store) -> None:
    session, _factory = store
    kb, revision, _entries = await _seed_linked_revision(session)
    await _rewrite_page(
        session,
        revision,
        "guide.txt",
        title=GUIDE_TITLE,
        # A self reference is neither a link nor a gap; only the ghost is missing.
        body="自指 [[guide.txt]] 与 [[不存在的页面]]。",
    )
    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    by_title = {row["title"]: row for row in index["pages"]}
    assert by_title[POLICY_TITLE]["backlinks"] == []
    assert by_title[GUIDE_TITLE]["missing_links"] == ["不存在的页面"]
    assert by_title[GUIDE_TITLE]["links"] == []


@pytest.mark.anyio
async def test_index_associations_reuse_graph_artifacts_with_frozen_sources(store) -> None:
    session, _factory = store
    kb, revision, entries = await _seed_linked_revision(session)
    guide_entry, policy_entry = entries["guide.txt"], entries["policy.txt"]
    await _store_graph_artifact(
        session,
        kb,
        revision,
        guide_entry,
        entities=[{"name": "甲零件", "type": "零件"}, {"name": "乙组件", "type": "组件"}],
        relations=[{"source": "甲零件", "target": "乙组件", "relation": "属于"}],
    )
    await _store_graph_artifact(session, kb, revision, policy_entry, status=STATUS_FAILED, error_code=GRAPH_DOCUMENT_TOO_LARGE)

    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    associations = index["associations"]
    assert associations["status"] == "partial"
    assert associations["generated"] == 1 and associations["failed"] == 1
    assert [(row["name"], row["document_id"]) for row in associations["entities"]] == [
        ("甲零件", str(guide_entry["document_id"])),
        ("乙组件", str(guide_entry["document_id"])),
    ]
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
    assert sources[str(guide_entry["document_id"])]["status"] == STATUS_COMPLETED
    assert sources[str(guide_entry["document_id"])]["content_hash"] == str(guide_entry["content_hash"])
    assert sources[str(policy_entry["document_id"])]["status"] == STATUS_FAILED
    assert sources[str(policy_entry["document_id"])]["error_code"] == GRAPH_DOCUMENT_TOO_LARGE


@pytest.mark.anyio
async def test_index_associations_report_not_generated_without_artifacts(store) -> None:
    session, _factory = store
    kb, revision, _entries = await _seed_linked_revision(session)
    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    assert index["associations"]["status"] == STATUS_NOT_GENERATED
    assert index["associations"]["entities"] == [] and index["associations"]["relations"] == []
    assert {row["status"] for row in index["associations"]["sources"]} == {STATUS_NOT_GENERATED}


@pytest.mark.anyio
async def test_index_is_scoped_to_exactly_one_revision(store) -> None:
    session, _factory = store
    kb, revision, entries = await _seed_linked_revision(session)
    await _store_graph_artifact(
        session,
        kb,
        revision,
        entries["guide.txt"],
        relations=[{"source": "甲零件", "target": "乙组件", "relation": "属于"}],
    )
    # A second revision freezes a different manifest and a different page.
    second = await _register_revision(session, kb, [_entry("policy.txt", POLICY), _entry("extra.txt", "新材料。\n".encode())])
    extra_entry = next(entry for entry in second.manifest_json if entry["filename"] == "extra.txt")
    await _store_page(session, kb, second, extra_entry, title="第二版新页", body="指向 [[policy.txt]]。")

    first_index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    second_index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, second.id)

    # Document identity is stable across revisions, but pages, titles, links,
    # and graph rows are keyed by revision: each index lists exactly its own
    # revision's manifest and its own revision's artifacts.
    assert [row["filename"] for row in first_index["pages"]] == ["guide.txt", "policy.txt"]
    assert [row["filename"] for row in second_index["pages"]] == ["policy.txt", "extra.txt"]
    first_text = repr(first_index)
    assert "第二版新页" not in first_text and str(extra_entry["document_id"]) not in first_text
    # Second revision's policy page was never generated: it reads as an honest
    # not_generated row, never as the first revision's generated page.
    second_policy = next(row for row in second_index["pages"] if row["filename"] == "policy.txt")
    assert second_policy["status"] == STATUS_NOT_GENERATED and second_policy["title"] == ""
    # The second revision's extra page links to policy.txt; the backlink comes
    # only from this revision's pages, never from the first revision's guide.
    assert [row["title"] for row in second_policy["backlinks"]] == ["第二版新页"]
    # First revision's relations never bleed into the second revision's view.
    assert all(row["relation"] != "属于" for row in second_index["associations"]["relations"])
    assert first_index["manifest_hash"] == revision.manifest_hash
    assert second_index["manifest_hash"] == second.manifest_hash
    assert second_index["revision_id"] == second.id


@pytest.mark.anyio
async def test_index_visibility_is_the_kb_parity_guard(store) -> None:
    session, _factory = store
    kb, revision, _entries = await _seed_linked_revision(session)

    # A caller without access reads not-found — the same answer a hidden KB
    # gives everywhere else; no title, link, or relation may leak first.
    with pytest.raises(ResourceNotFound):
        await KnowledgeWikiNavigationService(session, _actor("stranger")).index(kb.id, revision.id)

    async def _make_department_visible() -> None:
        kb.visibility = "department"
        kb.scope_department_id = "dept-119"
        await session.commit()

    await _make_department_visible()
    member_index = await KnowledgeWikiNavigationService(session, _actor("colleague", department_id="dept-119")).index(kb.id, revision.id)
    assert {row["title"] for row in member_index["pages"]} == {GUIDE_TITLE, POLICY_TITLE}

    with pytest.raises(ResourceNotFound):
        await KnowledgeWikiNavigationService(session, _actor()).index(str(uuid.uuid4()), revision.id)
    with pytest.raises(ResourceNotFound):
        await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, str(uuid.uuid4()))


@pytest.mark.anyio
async def test_index_before_any_generation_reports_not_generated(store) -> None:
    session, _factory = store
    kb = await _seed_kb(session)
    revision = await _register_revision(session, kb, [_entry("guide.txt", GUIDE)])
    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    assert index["status"] == STATUS_NOT_GENERATED
    assert index["pages"][0]["links"] == [] and index["pages"][0]["backlinks"] == []
    assert index["pages"][0]["status"] == STATUS_NOT_GENERATED


@pytest.mark.anyio
async def test_index_page_rows_never_carry_bodies(store) -> None:
    session, _factory = store
    kb, revision, _entries = await _seed_linked_revision(session)
    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    assert all("body" not in row for row in index["pages"])


@pytest.mark.anyio
async def test_index_resolves_links_by_frozen_document_id(store) -> None:
    session, _factory = store
    kb, revision, entries = await _seed_linked_revision(session)
    guide_entry, policy_entry = entries["guide.txt"], entries["policy.txt"]
    policy_document_id = str(policy_entry["document_id"])
    # The body names the target only by its frozen document id.
    await _rewrite_page(session, revision, "guide.txt", title=GUIDE_TITLE, body=f"按冻结标识直达 [[{policy_document_id}]]。")

    index = await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, revision.id)
    guide_row = next(row for row in index["pages"] if row["filename"] == "guide.txt")
    assert [link["document_id"] for link in guide_row["links"]] == [policy_document_id]
    assert guide_row["missing_links"] == []
    policy_row = next(row for row in index["pages"] if row["filename"] == "policy.txt")
    assert [row["document_id"] for row in policy_row["backlinks"]] == [str(guide_entry["document_id"])]


@pytest.mark.anyio
async def test_index_refuses_a_revision_from_another_knowledge_base(store) -> None:
    session, _factory = store
    kb, _revision, _entries = await _seed_linked_revision(session)
    other_kb = await _seed_kb(session, slug="wiki-nav-other-kb")
    other_revision = await _register_revision(session, other_kb, [_entry("guide.txt", GUIDE)])

    # The revision exists, but belongs to a different KB: the same not-found
    # answer everywhere else, never the other base's index.
    with pytest.raises(ResourceNotFound):
        await KnowledgeWikiNavigationService(session, _actor()).index(kb.id, other_revision.id)


@pytest.mark.anyio
async def test_stored_rows_are_queryable_by_revision(store) -> None:
    session, _factory = store
    kb, revision, _entries = await _seed_linked_revision(session)
    rows = (await session.execute(select(KnowledgeWikiPage).where(KnowledgeWikiPage.revision_id == revision.id))).scalars().all()
    assert len(rows) == 2
