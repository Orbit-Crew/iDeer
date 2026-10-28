"""Wiki index navigation: links, backlinks, and the association graph (#119).

The index is a read-only projection of artifacts that already exist for one
frozen revision — the #118 wiki pages and the #116 graph rows are read, never
re-generated and no model is invoked. Links are extracted deterministically
from the stored page bodies (``[[target]]`` wiki links and ``[text](target)``
Markdown links) and resolved only against this revision's frozen manifest
(document id, filename) and its own completed page titles; anything else is
an explicit missing target, never a fabricated accessible page. Backlinks
invert exactly the resolved links, and the association graph reuses the
stored graph artifacts with their frozen document sources.

Every entry rides the KB's own visibility chain — the exact
``get_visible`` guard the #118 page list and the #116 graph view use — so no
other revision's or account's titles, links, or relations can appear here,
and page bodies stay behind the #118 per-page read.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.knowledge.graph_generation import (
    MAX_GRAPH_ENTITIES,
    MAX_GRAPH_RELATIONS,
    STATUS_NOT_GENERATED,
    aggregate_status,
    manifest_entries,
)
from app.agentplatform.knowledge.models import KnowledgeGraphArtifact, KnowledgeRevision, KnowledgeWikiPage
from app.agentplatform.knowledge.wiki_generation import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    aggregate_wiki_status,
)
from app.agentplatform.resources.service import (
    ResourceActor,
    ResourceNotFound,
    ResourceService,
)

# A link target is bounded like the filenames and titles it may name, and a
# page carries a bounded number of links so one pathological body cannot
# flood the index.
MAX_WIKI_LINK_TARGET_CHARS = 255
MAX_WIKI_LINKS_PER_PAGE = 100

_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "ftp://")

# ``[[target]]`` wiki links and ``[text](target)`` Markdown links. The wiki
# alternative matches first, so both shapes are one deterministic grammar;
# external URLs and bare anchors never match the target groups below.
_WIKI_LINK_PATTERN = re.compile(r"\[\[([^\[\]]+)\]\]|\[[^\[\]]*\]\(([^()\s]+)\)")


def extract_wiki_links(body: str) -> list[str]:
    """The deduplicated internal link targets of one page body, in order.

    Only bounded, non-external, non-anchor targets are returned; anything
    else (URLs, mailto, anchors, empty or oversized text) is ignored rather
    than guessed at, and duplicates collapse to their first occurrence.
    """

    if not isinstance(body, str) or not body:
        return []
    links: list[str] = []
    for match in _WIKI_LINK_PATTERN.finditer(body):
        target = (match.group(1) or match.group(2) or "").strip()
        if not target or len(target) > MAX_WIKI_LINK_TARGET_CHARS or "\x00" in target:
            continue
        if target.startswith("#") or target.lower().startswith(_EXTERNAL_LINK_PREFIXES):
            continue
        if target not in links:
            links.append(target)
        if len(links) >= MAX_WIKI_LINKS_PER_PAGE:
            break
    return links


class KnowledgeWikiNavigationService:
    """Permission-bound wiki index, link/backlink projection, and associations."""

    def __init__(self, session: AsyncSession, actor: ResourceActor) -> None:
        self.session = session
        self.actor = actor
        self.resource_service = ResourceService(session, actor)

    async def _knowledge_base(self, resource_id: str) -> Any:
        """Read-parity visibility: the guard the #118 page list rides."""

        resource = await self.resource_service.get_visible(resource_id)
        if resource.type != "knowledge_base":
            raise ResourceNotFound(f"KnowledgeBase {resource_id} not found")
        return resource

    async def _revision(self, resource_id: str, revision_id: str) -> KnowledgeRevision:
        revision = await self.session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.knowledge_base_id != resource_id:
            raise ResourceNotFound(f"Knowledge revision {revision_id} not found")
        return revision

    async def index(self, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Project one revision's wiki index with links, backlinks, and graph.

        Only this revision's frozen manifest, its own stored pages, and its
        own stored graph artifacts are read. A link resolves only to a
        document of exactly this revision; a target that names nothing here
        is reported as missing with its bounded text, and a resolved target
        names the honest page status — nothing pretends a skipped,
        failed, or ungenerated page is readable.
        """

        kb = await self._knowledge_base(resource_id)
        revision = await self._revision(resource_id, revision_id)
        entries = manifest_entries(revision)
        result = await self.session.execute(
            select(KnowledgeWikiPage).where(KnowledgeWikiPage.revision_id == revision.id).order_by(KnowledgeWikiPage.document_id)
        )
        stored = {row.document_id: row for row in result.scalars()}

        # Titles of this revision's completed pages, resolved to their
        # canonical (lexicographically first) document id.
        titles: dict[str, str] = {}
        for document_id in sorted(stored):
            row = stored[document_id]
            if row.status == STATUS_COMPLETED and row.title and row.title not in titles:
                titles[row.title] = document_id

        by_id = {str(entry["document_id"]): entry for entry in entries}
        by_filename = {str(entry.get("filename") or ""): entry for entry in entries if entry.get("filename")}
        rows: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        generated = failed = skipped = 0
        for entry in entries:
            document_id = str(entry["document_id"])
            filename = str(entry.get("filename") or "")
            artifact = stored.get(document_id)
            status = artifact.status if artifact is not None else STATUS_NOT_GENERATED
            error_code = artifact.error_code if artifact is not None else None
            if status == STATUS_COMPLETED:
                generated += 1
            elif status == STATUS_SKIPPED:
                skipped += 1
            elif status == STATUS_FAILED:
                failed += 1
            rows[document_id] = {
                "document_id": document_id,
                "filename": filename,
                "title": artifact.title if artifact is not None and status == STATUS_COMPLETED else "",
                "content_hash": str(entry.get("content_hash") or ""),
                "status": status,
                "error_code": error_code,
                "links": [],
                "missing_links": [],
                "backlinks": [],
            }
            order.append(document_id)

        def _resolve_document(target: str) -> str | None:
            """One target's document id inside exactly this revision, or None."""

            if target in by_id:
                return target
            if target in by_filename:
                return str(by_filename[target]["document_id"])
            return titles.get(target)

        # Links only derive from completed bodies, in manifest order; each
        # resolved link adds exactly one backlink to its target. A self
        # reference is neither a link nor a gap, and a target that names
        # nothing frozen here stays an explicit missing entry.
        for document_id in order:
            row = rows[document_id]
            artifact = stored.get(document_id)
            if artifact is None or artifact.status != STATUS_COMPLETED:
                continue
            for target in extract_wiki_links(artifact.body):
                resolved_id = _resolve_document(target)
                if resolved_id is None:
                    if len(row["missing_links"]) < MAX_WIKI_LINKS_PER_PAGE:
                        row["missing_links"].append(target)
                    continue
                if resolved_id == document_id or resolved_id not in rows:
                    continue
                target_row = stored.get(resolved_id)
                target_status = target_row.status if target_row is not None else STATUS_NOT_GENERATED
                resolved = {
                    "document_id": resolved_id,
                    "title": target_row.title if target_row is not None and target_status == STATUS_COMPLETED else "",
                    "status": target_status,
                }
                if all(link["document_id"] != resolved_id for link in row["links"]):
                    row["links"].append(resolved)
                target_entry = rows[resolved_id]
                if all(backlink["document_id"] != document_id for backlink in target_entry["backlinks"]):
                    target_entry["backlinks"].append({"document_id": document_id, "title": row["title"], "status": row["status"]})

        status: str = STATUS_NOT_GENERATED if not stored else aggregate_wiki_status(generated, failed, skipped)
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": status,
            "generated": generated,
            "failed": failed,
            "skipped": skipped,
            "pages": [rows[document_id] for document_id in order],
            "associations": await self._associations(revision),
        }

    async def _associations(self, revision: KnowledgeRevision) -> dict[str, Any]:
        """The #116 graph rows of exactly this revision, with frozen sources.

        Completed artifacts contribute their stored entities and relations,
        each row carrying the document identity and frozen digest; failed or
        ungenerated documents appear as honest coverage rows and contribute
        nothing else.
        """

        result = await self.session.execute(
            select(KnowledgeGraphArtifact).where(KnowledgeGraphArtifact.revision_id == revision.id).order_by(KnowledgeGraphArtifact.document_id)
        )
        artifacts = {row.document_id: row for row in result.scalars()}
        sources: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        generated = failed = 0
        for entry in manifest_entries(revision):
            document_id = str(entry["document_id"])
            filename = str(entry.get("filename") or "")
            content_hash = str(entry.get("content_hash") or "")
            artifact = artifacts.get(document_id)
            if artifact is None:
                sources.append(
                    {"document_id": document_id, "filename": filename, "content_hash": content_hash, "status": STATUS_NOT_GENERATED, "error_code": None}
                )
                continue
            if artifact.status == STATUS_COMPLETED:
                generated += 1
            else:
                failed += 1
            sources.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "content_hash": content_hash,
                    "status": artifact.status,
                    "error_code": artifact.error_code,
                }
            )
            if artifact.status != STATUS_COMPLETED:
                continue
            for entity in artifact.entities_json or []:
                if len(entities) >= MAX_GRAPH_ENTITIES:
                    break
                entities.append({**entity, "document_id": document_id, "filename": filename, "content_hash": content_hash})
            for relation in artifact.relations_json or []:
                if len(relations) >= MAX_GRAPH_RELATIONS:
                    break
                relations.append({**relation, "document_id": document_id, "filename": filename, "content_hash": content_hash})
        association_status = STATUS_NOT_GENERATED if not artifacts else aggregate_status(generated, failed)
        return {
            "status": association_status,
            "generated": generated,
            "failed": failed,
            "sources": sources,
            "entities": entities,
            "relations": relations,
        }
