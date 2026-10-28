"""Server-orchestrated wiki generation and page reading for one frozen revision (#118).

The wiki mirrors the controlled graph stack: the Server orchestrates every
model call, and device-local material is requested one frozen document at a
time through the shared :class:`~app.agentplatform.knowledge.graph_generation.RevisionMaterialSource`
dispatch (frozen identity fields only, owner-scoped connection, device-gated
consent) — a device never bulk-uploads its library. Both ends re-verify the
frozen SHA-256, so a page can only be written from the frozen bytes.

One page per frozen document, bound to its (KB, Revision, document) source.
Progress, skips, and partial failures are honest per-page records: a page
whose material is unavailable at its frozen digest is **skipped** with its
fixed category (there was nothing to write from), a model failure is
**failed**, and a missing attempt reads **not_generated** — never a
fabricated body. Pages are keyed by revision, so versions never mix and a
retry never overrides the frozen basis.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.knowledge.graph_generation import (
    STATUS_COMPLETED,
    STATUS_NOT_GENERATED,
    GraphMaterialFailure,
    RevisionMaterialSource,
    manifest_entries,
)
from app.agentplatform.knowledge.models import KnowledgeRevision, KnowledgeWikiPage
from app.agentplatform.resources.service import (
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourceService,
)

# Fixed generation statuses surfaced to the Desktop and the Web. Aggregate
# statuses distinguish an honest partial result from a complete one and from
# "nothing generated yet"; skipped pages keep the skip visible.
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_PARTIAL = "partial"

# Controlled output bounds: a bounded page keeps views responsive and stops
# a runaway model answer from flooding the KB.
MAX_WIKI_TITLE_CHARS = 200
MAX_WIKI_BODY_CHARS = 20000

WIKI_REVISION_EMPTY = "WIKI_REVISION_EMPTY"
WIKI_MODEL_OUTPUT_INVALID = "WIKI_MODEL_OUTPUT_INVALID"
WIKI_MODEL_UNAVAILABLE = "WIKI_MODEL_UNAVAILABLE"

WIKI_SYSTEM_INSTRUCTION = (
    "You write one wiki page in Markdown from one document of an enterprise knowledge base.\n"
    "Return STRICT JSON only, no markdown fence, no commentary, shaped exactly as:\n"
    '{"title": "...", "body": "Markdown text of the wiki page"}\n'
    "The title names the document's subject; the body organizes and explains what the document states.\n"
    "State only what the document states; never invent facts, numbers, or sections the document does not have.\n"
    "Keep the body under 20000 characters."
)


def _clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError("wiki field must be a string")
    text = value.strip()
    if not text or len(text) > limit or "\x00" in text:
        raise ValueError("wiki field out of bounds")
    return text


def normalize_model_wiki(raw: object) -> dict[str, str]:
    """Validate one model answer into the stored page shape.

    The payload must carry a non-empty bounded title and body; malformed
    payloads raise ``ValueError`` (the caller records a per-document
    failure) and an overlong body is refused rather than silently
    truncated, so a stored page is always the model's complete answer.
    """

    if not isinstance(raw, dict):
        raise ValueError("model output must be an object")
    return {
        "title": _clean_text(raw.get("title"), MAX_WIKI_TITLE_CHARS),
        "body": _clean_text(raw.get("body"), MAX_WIKI_BODY_CHARS),
    }


async def generate_document_wiki(document_text: str) -> dict[str, str]:
    """The default server-orchestrated model call for one document's page.

    The model is chosen and invoked by the Server's own configuration
    (``run_oneshot_llm``); the device never sees the prompt or the page.
    Malformed model output raises, which the caller records as a
    per-document failure instead of a fabricated page.
    """

    from deerflow.config import get_app_config
    from deerflow.utils.llm_text import strip_markdown_code_fence, strip_think_blocks
    from deerflow.utils.oneshot_llm import run_oneshot_llm

    raw = await run_oneshot_llm(
        system_instruction=WIKI_SYSTEM_INSTRUCTION,
        user_content=f"<document>\n{document_text}\n</document>",
        run_name="knowledge_wiki_generation",
        app_config=get_app_config(),
    )
    cleaned = strip_markdown_code_fence(strip_think_blocks(raw, truncate_unclosed=True)).strip()
    try:
        parsed = json.loads(cleaned)
    except ValueError as exc:
        raise ValueError("model output was not valid JSON") from exc
    return normalize_model_wiki(parsed)


def aggregate_wiki_status(generated: int, failed: int, skipped: int) -> str:
    if generated and not failed and not skipped:
        return STATUS_COMPLETED
    if generated:
        return STATUS_PARTIAL
    return STATUS_FAILED


class KnowledgeWikiGenerationService:
    """Per-Revision controlled wiki generation and permission-bound reading."""

    def __init__(
        self,
        session: AsyncSession,
        actor: ResourceActor,
        *,
        writer: Callable[[str], Any] | None = None,
        broker_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.resource_service = ResourceService(session, actor)
        self._writer = writer or generate_document_wiki
        self._material_source = RevisionMaterialSource(session, actor, broker_factory, label="knowledge-wiki")

    async def _knowledge_base(self, resource_id: str, *, modify: bool) -> Any:
        resource = await self.resource_service.get_visible(resource_id)
        if resource.type != "knowledge_base":
            raise ResourceNotFound(f"KnowledgeBase {resource_id} not found")
        if modify:
            # Generation derives and rewrites this KB's wiki pages: the same
            # owner boundary as importing, publishing, and graph generation.
            self.resource_service.assert_modify(resource)
        return resource

    async def _revision(self, resource_id: str, revision_id: str) -> KnowledgeRevision:
        revision = await self.session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.knowledge_base_id != resource_id:
            raise ResourceNotFound(f"Knowledge revision {revision_id} not found")
        return revision

    async def generate(self, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Generate the wiki for one frozen revision, document by document.

        Material acquisition and model calls both run here, on the Server.
        A retry re-reads every source at its frozen digest and never touches
        the revision itself — the frozen basis cannot be overridden, and each
        page succeeds, skips, or fails independently with a visible record.
        """

        kb = await self._knowledge_base(resource_id, modify=True)
        revision = await self._revision(resource_id, revision_id)
        entries = manifest_entries(revision)
        if not entries:
            raise ResourceConflict("This revision has no frozen documents to generate a wiki from")

        pages: list[dict[str, Any]] = []
        generated = failed = skipped = 0
        for entry in entries:
            document_id = str(entry["document_id"])
            try:
                text = await self._material_source.document_text(kb, revision, entry)
                page = normalize_model_wiki(await self._invoke_writer(text))
                await self._store_page(kb, revision, entry, page)
                generated += 1
                status, error_code = STATUS_COMPLETED, None
            except GraphMaterialFailure as exc:
                await self._store_skip(kb, revision, entry, exc.code)
                skipped += 1
                status, error_code = STATUS_SKIPPED, exc.code
            except ValueError:
                await self._store_failure(kb, revision, entry, WIKI_MODEL_OUTPUT_INVALID)
                failed += 1
                status, error_code = STATUS_FAILED, WIKI_MODEL_OUTPUT_INVALID
            except Exception:
                await self._store_failure(kb, revision, entry, WIKI_MODEL_UNAVAILABLE)
                failed += 1
                status, error_code = STATUS_FAILED, WIKI_MODEL_UNAVAILABLE
            pages.append(
                {
                    "document_id": document_id,
                    "filename": str(entry.get("filename") or ""),
                    "content_hash": str(entry.get("content_hash") or ""),
                    "status": status,
                    "error_code": error_code,
                }
            )
        await self.session.flush()
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": aggregate_wiki_status(generated, failed, skipped),
            "generated": generated,
            "failed": failed,
            "skipped": skipped,
            "pages": pages,
        }

    async def view(self, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Project the page list with its sources for a visible caller.

        Visibility is the KB's own: a caller without access reads a 404, a
        department member reads the same frozen bindings, and only documents
        of exactly this revision's manifest ever appear here. Bodies stay
        behind the per-page read.
        """

        kb = await self._knowledge_base(resource_id, modify=False)
        revision = await self._revision(resource_id, revision_id)
        result = await self.session.execute(
            select(KnowledgeWikiPage).where(KnowledgeWikiPage.revision_id == revision.id).order_by(KnowledgeWikiPage.document_id)
        )
        stored = {row.document_id: row for row in result.scalars()}

        pages: list[dict[str, Any]] = []
        generated = failed = skipped = 0
        for entry in manifest_entries(revision):
            document_id = str(entry["document_id"])
            filename = str(entry.get("filename") or "")
            artifact = stored.get(document_id)
            if artifact is None:
                pages.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "title": "",
                        "content_hash": str(entry.get("content_hash") or ""),
                        "status": STATUS_NOT_GENERATED,
                        "error_code": None,
                    }
                )
                continue
            if artifact.status == STATUS_COMPLETED:
                generated += 1
            elif artifact.status == STATUS_SKIPPED:
                skipped += 1
            else:
                failed += 1
            pages.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "title": artifact.title,
                    "content_hash": artifact.document_content_hash,
                    "status": artifact.status,
                    "error_code": artifact.error_code,
                }
            )

        if not stored:
            status: str = STATUS_NOT_GENERATED
        else:
            status = aggregate_wiki_status(generated, failed, skipped)
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": status,
            "generated": generated,
            "failed": failed,
            "skipped": skipped,
            "pages": pages,
        }

    async def read_page(self, resource_id: str, revision_id: str, document_id: str) -> dict[str, Any]:
        """Read one page with its body for a visible caller.

        The document id must be frozen in this revision — anything else reads
        as not-found, so out-of-scope pages never leak a title or a body.
        A skipped or failed page reads as exactly that: its fixed category,
        never a body.
        """

        kb = await self._knowledge_base(resource_id, modify=False)
        revision = await self._revision(resource_id, revision_id)
        entry = next((row for row in manifest_entries(revision) if str(row["document_id"]) == str(document_id)), None)
        if entry is None:
            raise ResourceNotFound(f"Knowledge document {document_id} not found in revision {revision_id}")
        artifact = (
            await self.session.execute(
                select(KnowledgeWikiPage).where(
                    KnowledgeWikiPage.revision_id == revision.id,
                    KnowledgeWikiPage.document_id == str(document_id),
                )
            )
        ).scalar_one_or_none()
        if artifact is None:
            status: str = STATUS_NOT_GENERATED
            title = body = ""
            error_code = None
            content_hash = str(entry.get("content_hash") or "")
        else:
            status = artifact.status
            title = artifact.title if artifact.status == STATUS_COMPLETED else ""
            body = artifact.body if artifact.status == STATUS_COMPLETED else ""
            error_code = artifact.error_code
            content_hash = artifact.document_content_hash
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "document_id": str(document_id),
            "filename": str(entry.get("filename") or ""),
            "title": title,
            "content_hash": content_hash,
            "status": status,
            "error_code": error_code,
            "body": body,
        }

    async def _invoke_writer(self, text: str) -> dict:
        return await self._writer(text)

    async def _store_page(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any], page: dict[str, str]) -> KnowledgeWikiPage:
        await self._drop_existing(revision.id, str(entry["document_id"]))
        row = KnowledgeWikiPage(
            id=str(uuid.uuid4()),
            knowledge_base_id=kb.id,
            revision_id=revision.id,
            revision_no=revision.revision_no,
            manifest_hash=revision.manifest_hash,
            document_id=str(entry["document_id"]),
            document_filename=str(entry.get("filename") or ""),
            document_content_hash=str(entry.get("content_hash") or ""),
            title=page["title"],
            body=page["body"],
            status=STATUS_COMPLETED,
            error_code=None,
            error_message=None,
            generated_by=self.actor.user_id,
        )
        self.session.add(row)
        return row

    async def _store_skip(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any], code: str) -> KnowledgeWikiPage:
        """A skipped document stays an explicit, visible record — never silence."""

        return await self._store_empty(kb, revision, entry, STATUS_SKIPPED, code)

    async def _store_failure(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any], code: str) -> KnowledgeWikiPage:
        return await self._store_empty(kb, revision, entry, STATUS_FAILED, code)

    async def _store_empty(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any], status: str, code: str) -> KnowledgeWikiPage:
        await self._drop_existing(revision.id, str(entry["document_id"]))
        row = KnowledgeWikiPage(
            id=str(uuid.uuid4()),
            knowledge_base_id=kb.id,
            revision_id=revision.id,
            revision_no=revision.revision_no,
            manifest_hash=revision.manifest_hash,
            document_id=str(entry["document_id"]),
            document_filename=str(entry.get("filename") or ""),
            document_content_hash=str(entry.get("content_hash") or ""),
            title="",
            body="",
            status=status,
            error_code=code,
            error_message=None,
            generated_by=self.actor.user_id,
        )
        self.session.add(row)
        return row

    async def _drop_existing(self, revision_id: str, document_id: str) -> None:
        await self.session.execute(
            delete(KnowledgeWikiPage).where(
                KnowledgeWikiPage.revision_id == revision_id,
                KnowledgeWikiPage.document_id == document_id,
            )
        )
