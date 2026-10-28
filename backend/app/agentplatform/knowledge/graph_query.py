"""Scoped graph QA and relation retrieval inside one frozen revision (#117).

The user narrows a question or an entity/relation search to selected frozen
documents of one valid KB/Revision. Authorization is the KB's own visibility
chain — the same one knowledge retrieval rides — so no label, tag, or
client-side filter can impersonate access. Selected document ids are
validated against the frozen manifest, never trusted.

Every answer names its sources: relation/entity rows carry the document
identity and frozen digest, and a scoped ask reads material only through the
shared :class:`~app.agentplatform.knowledge.graph_generation.RevisionMaterialSource`
before the Server-orchestrated model call. When any selected document's
material is missing, drifted, or otherwise unavailable, the ask refuses with
a structured per-document record and never reaches the model — a gapped
scope cannot form an unfounded conclusion. Queries are bound to the revision
they name: a later revision never silently replaces an earlier scope's
sources.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.knowledge.graph_generation import (
    GRAPH_MODEL_OUTPUT_INVALID,
    GRAPH_MODEL_UNAVAILABLE,
    MAX_GRAPH_ENTITIES,
    MAX_GRAPH_RELATIONS,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_NOT_GENERATED,
    STATUS_PARTIAL,
    GraphMaterialFailure,
    RevisionMaterialSource,
    aggregate_status,
    manifest_entries,
)
from app.agentplatform.knowledge.models import KnowledgeGraphArtifact, KnowledgeRevision
from app.agentplatform.resources.service import (
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourceService,
)

# The scoped surface is deliberately narrower than the whole library: one
# revision, a handful of selected documents, bounded text in and out.
MAX_SCOPED_DOCUMENTS = 50
MAX_SCOPED_QUERY_CHARS = 512
MAX_SCOPED_QUESTION_CHARS = 4000
MAX_SCOPED_ANSWER_CHARS = 8000
MAX_SCOPED_DOCUMENT_ID_CHARS = 64

_SCOPED_QA_SYSTEM_INSTRUCTION = (
    "You answer one question strictly from the provided knowledge-base documents.\n"
    "Each document is given with its filename and SHA-256; name the filenames you relied on.\n"
    "If the provided documents do not contain the answer, state exactly that they do not contain enough information.\n"
    "Never use outside knowledge, never guess, and never present an unsourced statement as an answer."
)


async def answer_scoped_question(question: str, documents: list[tuple[str, str, str]]) -> str:
    """The default server-orchestrated scoped QA model call.

    ``documents`` are ``(filename, content_hash, text)`` tuples of the
    selected frozen documents. The model runs on the Server's own
    configuration; an empty or oversized answer raises, which the caller
    records as a structured refusal instead of a fabricated conclusion.
    """

    from deerflow.config import get_app_config
    from deerflow.utils.llm_text import strip_markdown_code_fence, strip_think_blocks
    from deerflow.utils.oneshot_llm import run_oneshot_llm

    parts = [f'<document filename="{filename}" sha256="{content_hash}">\n{text}\n</document>' for filename, content_hash, text in documents]
    joined = "\n".join(parts)
    raw = await run_oneshot_llm(
        system_instruction=_SCOPED_QA_SYSTEM_INSTRUCTION,
        user_content=f"<documents>\n{joined}\n</documents>\n<question>\n{question}\n</question>",
        run_name="knowledge_graph_scoped_qa",
        app_config=get_app_config(),
    )
    answer = strip_markdown_code_fence(strip_think_blocks(raw, truncate_unclosed=True)).strip()
    if not answer:
        raise ValueError("model answer was empty")
    if len(answer) > MAX_SCOPED_ANSWER_CHARS:
        raise ValueError("model answer exceeds the bounded answer size")
    return answer


def _matches(values: list[str], needle: str) -> bool:
    if not needle:
        return True
    folded = needle.casefold()
    return any(folded in value.casefold() for value in values if value)


class KnowledgeGraphQueryService:
    """Permission-bound scoped entity/relation retrieval and QA."""

    def __init__(
        self,
        session: AsyncSession,
        actor: ResourceActor,
        *,
        answerer: Any = None,
        broker_factory: Any = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.resource_service = ResourceService(session, actor)
        self._answerer = answerer or answer_scoped_question
        self._material_source = RevisionMaterialSource(session, actor, broker_factory)

    async def _knowledge_base(self, resource_id: str) -> Any:
        """Read-parity visibility: the exact guard knowledge retrieval uses.

        ``get_visible`` is the whole check — a hidden KB reads as not-found
        regardless of any client-supplied labels, and a visible department
        member reads the same frozen scope as retrieval does.
        """

        resource = await self.resource_service.get_visible(resource_id)
        if resource.type != "knowledge_base":
            raise ResourceNotFound(f"KnowledgeBase {resource_id} not found")
        return resource

    async def _revision(self, resource_id: str, revision_id: str) -> KnowledgeRevision:
        revision = await self.session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.knowledge_base_id != resource_id:
            raise ResourceNotFound(f"Knowledge revision {revision_id} not found")
        return revision

    async def _scoped_entries(self, resource_id: str, revision_id: str, document_ids: object) -> tuple[Any, KnowledgeRevision, list[dict[str, Any]]]:
        """Resolve one valid KB/Revision and the selected frozen documents.

        The requested document ids must be a non-empty subset of the
        revision's frozen manifest: anything else is a scope violation, not
        a widened query.
        """

        if (
            not isinstance(document_ids, list)
            or not document_ids
            or len(document_ids) > MAX_SCOPED_DOCUMENTS
            or any(not isinstance(document_id, str) or not document_id or len(document_id) > MAX_SCOPED_DOCUMENT_ID_CHARS for document_id in document_ids)
        ):
            raise ResourceConflict("Select one or more documents frozen in this revision to scope the query")
        kb = await self._knowledge_base(resource_id)
        revision = await self._revision(resource_id, revision_id)
        entries = manifest_entries(revision)
        if not entries:
            raise ResourceConflict("This revision has no frozen documents to scope a query against")
        by_id = {str(entry["document_id"]): entry for entry in entries}
        selected_ids = list(dict.fromkeys(document_ids))
        unknown = [document_id for document_id in selected_ids if document_id not in by_id]
        if unknown:
            raise ResourceConflict(f"Documents outside this revision's frozen scope: {', '.join(sorted(unknown)[:5])}")
        return kb, revision, [by_id[document_id] for document_id in selected_ids]

    async def query(self, resource_id: str, revision_id: str, document_ids: list[str], query_text: str = "") -> dict[str, Any]:
        """Retrieve entities and relations inside the selected document scope.

        Only stored artifacts of exactly this revision and the selected
        documents are read; every result row and every scope row carries the
        frozen document identity and digest. Un-generated or failed
        documents appear as honest coverage rows, never as invented rows.
        """

        kb, revision, entries = await self._scoped_entries(resource_id, revision_id, document_ids)
        needle = query_text.strip() if isinstance(query_text, str) else ""
        if len(needle) > MAX_SCOPED_QUERY_CHARS:
            raise ResourceConflict("The query text exceeds the bounded length")
        result = await self.session.execute(
            select(KnowledgeGraphArtifact)
            .where(
                KnowledgeGraphArtifact.revision_id == revision.id,
                KnowledgeGraphArtifact.document_id.in_([str(entry["document_id"]) for entry in entries]),
            )
            .order_by(KnowledgeGraphArtifact.document_id)
        )
        artifacts = {row.document_id: row for row in result.scalars()}

        scope: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        generated = failed = 0
        for entry in entries:
            document_id = str(entry["document_id"])
            filename = str(entry.get("filename") or "")
            content_hash = str(entry.get("content_hash") or "")
            artifact = artifacts.get(document_id)
            if artifact is None:
                scope.append({"document_id": document_id, "filename": filename, "content_hash": content_hash, "status": STATUS_NOT_GENERATED, "error_code": None})
                continue
            if artifact.status == STATUS_COMPLETED:
                generated += 1
            else:
                failed += 1
            scope.append(
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
                if _matches([str(entity.get("name") or ""), str(entity.get("type") or "")], needle):
                    entities.append({**entity, "document_id": document_id, "filename": filename, "content_hash": content_hash})
            for relation in artifact.relations_json or []:
                if len(relations) >= MAX_GRAPH_RELATIONS:
                    break
                if _matches([str(relation.get("source") or ""), str(relation.get("target") or ""), str(relation.get("relation") or "")], needle):
                    relations.append({**relation, "document_id": document_id, "filename": filename, "content_hash": content_hash})

        status = STATUS_NOT_GENERATED if not artifacts else aggregate_status(generated, failed)
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": status,
            "query": needle,
            "scope": scope,
            "entities": entities,
            "relations": relations,
        }

    async def ask(self, resource_id: str, revision_id: str, document_ids: list[str], question: str) -> dict[str, Any]:
        """Answer one question strictly from the selected frozen documents.

        Material is acquired through the shared execution chain; if any
        selected document is unavailable the ask refuses without invoking
        the model, stating every gap with its fixed category. The answer
        always travels with the per-document sources it was built from.
        """

        kb, revision, entries = await self._scoped_entries(resource_id, revision_id, document_ids)
        if not isinstance(question, str) or not question.strip() or len(question.strip()) > MAX_SCOPED_QUESTION_CHARS or "\x00" in question:
            raise ResourceConflict("Ask one bounded, non-empty question scoped to this revision")
        question = question.strip()

        scope: list[dict[str, Any]] = []
        documents: list[tuple[str, str, str]] = []
        failures = 0
        for entry in entries:
            document_id = str(entry["document_id"])
            filename = str(entry.get("filename") or "")
            content_hash = str(entry.get("content_hash") or "")
            try:
                text = await self._material_source.document_text(kb, revision, entry)
            except GraphMaterialFailure as exc:
                # The gap is recorded with its fixed category; the ask never
                # answers over a scope it could not fully read.
                failures += 1
                scope.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "content_hash": content_hash,
                        "status": STATUS_FAILED,
                        "error_code": exc.code,
                    }
                )
                continue
            scope.append({"document_id": document_id, "filename": filename, "content_hash": content_hash, "status": STATUS_COMPLETED, "error_code": None})
            documents.append((filename, content_hash, text))

        if failures:
            # A gapped scope never reaches the model: the refusal states the
            # gaps instead of an answer that would look grounded.
            return self._ask_payload(
                kb,
                revision,
                status=STATUS_FAILED if failures == len(entries) else STATUS_PARTIAL,
                question=question,
                answer=None,
                error_code=None,
                scope=scope,
            )
        try:
            answer = await self._invoke_answerer(question, documents)
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("answerer returned no text")
            answer = answer.strip()
            if len(answer) > MAX_SCOPED_ANSWER_CHARS:
                raise ValueError("model answer exceeds the bounded answer size")
        except ValueError:
            return self._ask_payload(kb, revision, status=STATUS_FAILED, question=question, answer=None, error_code=GRAPH_MODEL_OUTPUT_INVALID, scope=scope)
        except Exception:
            return self._ask_payload(kb, revision, status=STATUS_FAILED, question=question, answer=None, error_code=GRAPH_MODEL_UNAVAILABLE, scope=scope)
        return self._ask_payload(kb, revision, status=STATUS_COMPLETED, question=question, answer=answer, error_code=None, scope=scope)

    @staticmethod
    def _ask_payload(
        kb: Any,
        revision: KnowledgeRevision,
        *,
        status: str,
        question: str,
        answer: str | None,
        error_code: str | None,
        scope: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": status,
            "question": question,
            "answer": answer,
            "answer_available": answer is not None,
            "error_code": error_code,
            "scope": scope,
        }

    async def _invoke_answerer(self, question: str, documents: list[tuple[str, str, str]]) -> str:
        return await self._answerer(question, documents)
