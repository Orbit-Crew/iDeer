"""Controlled knowledge-graph generation for one frozen revision (#116).

The Server orchestrates every model call. A device never bulk-uploads its
library: material for a device-local revision is requested one frozen
document at a time through the same broker discipline as #113 retrieval
(frozen identity fields only, owner-scoped connection, device-gated
consent), the device re-validates every digest before its text leaves, and
the Server re-checks the digest of whatever comes back — so neither end can
substitute content.

Every entity and relation is stored bound to its KB/Revision/document
source, so views can locate the original document and another revision's
graph can never bleed in. Failures are per-document structured records with
fixed categories: a partial failure reads as partial, never as a complete
graph and never as silence.

#117 shares this material path: :class:`RevisionMaterialSource` is the one
execution chain through which scoped graph QA reads frozen documents too.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.knowledge.models import KnowledgeDocument, KnowledgeGraphArtifact, KnowledgeRevision
from app.agentplatform.knowledge.revisions import LOCAL_IMPORT_ORIGIN
from app.agentplatform.resources.service import (
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourceService,
)
from deerflow.config.paths import get_paths

# The device operation that answers one frozen-document material request.
# It is announced by paired Desktops, gated behind local confirmation like
# every content-leaving capability, and dispatched through the device broker
# so the task record and its receipt stay tied to the generation batch.
LOCAL_KNOWLEDGE_MATERIAL_OPERATION = "local.knowledge.material"

# One material answer is one frozen document. The device refuses larger
# documents outright instead of truncating (a truncated answer could never
# match the frozen digest); the Server enforces the same bound on arrival.
MAX_MATERIAL_BYTES = 524_288

# Controlled output bounds: a bounded graph keeps views responsive and stops
# a runaway model answer from flooding the KB.
MAX_GRAPH_ENTITIES = 200
MAX_GRAPH_RELATIONS = 200
MAX_ENTITY_NAME_CHARS = 200
MAX_ENTITY_TYPE_CHARS = 64
MAX_RELATION_NAME_CHARS = 200

# Fixed generation statuses and failure categories surfaced to the Desktop
# and the Web. Aggregate statuses distinguish an honest partial result from
# a complete one and from "nothing generated yet".
STATUS_COMPLETED = "completed"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_NOT_GENERATED = "not_generated"

GRAPH_REVISION_EMPTY = "GRAPH_REVISION_EMPTY"
GRAPH_DOCUMENT_UNAVAILABLE = "GRAPH_DOCUMENT_UNAVAILABLE"
GRAPH_DOCUMENT_NOT_TEXT = "GRAPH_DOCUMENT_NOT_TEXT"
GRAPH_DOCUMENT_TOO_LARGE = "GRAPH_DOCUMENT_TOO_LARGE"
GRAPH_CONTENT_DRIFTED = "GRAPH_CONTENT_DRIFTED"
GRAPH_DEVICE_UNAVAILABLE = "GRAPH_DEVICE_UNAVAILABLE"
GRAPH_DEVICE_DENIED = "GRAPH_DEVICE_DENIED"
GRAPH_MATERIAL_REJECTED = "GRAPH_MATERIAL_REJECTED"

# Device-side structured missing reasons (local.knowledge.material contract)
# mapped onto the fixed server-side categories.
_MATERIAL_MISSING_CODES = {
    "content_drift": GRAPH_CONTENT_DRIFTED,
    "document_unavailable": GRAPH_DOCUMENT_UNAVAILABLE,
    "document_too_large": GRAPH_DOCUMENT_TOO_LARGE,
    "not_text": GRAPH_DOCUMENT_NOT_TEXT,
}
GRAPH_MODEL_OUTPUT_INVALID = "GRAPH_MODEL_OUTPUT_INVALID"
GRAPH_MODEL_UNAVAILABLE = "GRAPH_MODEL_UNAVAILABLE"

class GraphMaterialFailure(Exception):
    """A fixed-category failure for one document's material or model step."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def _clean_entity_value(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError("entity field must be a string")
    text = value.strip()
    if not text or len(text) > limit or "\x00" in text:
        raise ValueError("entity field out of bounds")
    return text


def normalize_model_graph(raw: object) -> dict[str, list[dict[str, str]]]:
    """Validate one model answer into the stored entity/relation shape.

    The payload must name every entity with a non-empty bounded string;
    malformed payloads raise ``ValueError`` (the caller records a
    per-document failure). Relations whose endpoints were not extracted are
    dropped rather than stored dangling, and duplicates collapse to their
    first occurrence, so the stored graph only contains verifiable rows.
    """

    if not isinstance(raw, dict):
        raise ValueError("model output must be an object")
    raw_entities = raw.get("entities")
    raw_relations = raw.get("relations")
    if not isinstance(raw_entities, list) or not isinstance(raw_relations, list):
        raise ValueError("model output must carry entities and relations lists")

    entities: list[dict[str, str]] = []
    seen_entities: set[tuple[str, str]] = set()
    names: set[str] = set()
    for entry in raw_entities[: MAX_GRAPH_ENTITIES * 2]:
        if len(entities) >= MAX_GRAPH_ENTITIES:
            break
        if not isinstance(entry, dict):
            raise ValueError("each entity must be an object")
        name = _clean_entity_value(entry.get("name"), MAX_ENTITY_NAME_CHARS)
        kind = _clean_entity_value(entry.get("type") or "", MAX_ENTITY_TYPE_CHARS)
        key = (name, kind)
        if key in seen_entities:
            continue
        seen_entities.add(key)
        names.add(name)
        entities.append({"name": name, "type": kind})

    relations: list[dict[str, str]] = []
    seen_relations: set[tuple[str, str, str]] = set()
    for entry in raw_relations[: MAX_GRAPH_RELATIONS * 2]:
        if len(relations) >= MAX_GRAPH_RELATIONS:
            break
        if not isinstance(entry, dict):
            raise ValueError("each relation must be an object")
        source = _clean_entity_value(entry.get("source"), MAX_ENTITY_NAME_CHARS)
        target = _clean_entity_value(entry.get("target"), MAX_ENTITY_NAME_CHARS)
        relation = _clean_entity_value(entry.get("relation"), MAX_RELATION_NAME_CHARS)
        if source not in names or target not in names:
            continue
        key = (source, target, relation)
        if key in seen_relations:
            continue
        seen_relations.add(key)
        relations.append({"source": source, "target": target, "relation": relation})
    return {"entities": entities, "relations": relations}


_GRAPH_SYSTEM_INSTRUCTION = (
    "You extract a knowledge graph from one document of an enterprise knowledge base.\n"
    "Return STRICT JSON only, no markdown, no commentary, shaped exactly as:\n"
    '{"entities": [{"name": "...", "type": "..."}], '
    '"relations": [{"source": "...", "target": "...", "relation": "..."}]}\n'
    "Entity names must appear in the document or be its title; entity type is a short category word.\n"
    "Every relation must connect two extracted entities and name the relationship verb.\n"
    "Extract at most 200 entities and 200 relations. Do not invent facts that the document does not state."
)


async def generate_document_graph(document_text: str) -> dict[str, list[dict[str, str]]]:
    """The default server-orchestrated model call for one document.

    The model is chosen and invoked by the Server's own configuration
    (``run_oneshot_llm``); the device never sees the prompt or the answer.
    Malformed model output raises, which the caller records as a
    per-document failure instead of a fabricated graph.
    """

    from deerflow.config import get_app_config
    from deerflow.utils.llm_text import strip_markdown_code_fence, strip_think_blocks
    from deerflow.utils.oneshot_llm import run_oneshot_llm

    raw = await run_oneshot_llm(
        system_instruction=_GRAPH_SYSTEM_INSTRUCTION,
        user_content=f"<document>\n{document_text}\n</document>",
        run_name="knowledge_graph_generation",
        app_config=get_app_config(),
    )
    cleaned = strip_markdown_code_fence(strip_think_blocks(raw, truncate_unclosed=True)).strip()
    try:
        parsed = json.loads(cleaned)
    except ValueError as exc:
        raise ValueError("model output was not valid JSON") from exc
    return normalize_model_graph(parsed)


def manifest_entries(revision: KnowledgeRevision) -> list[dict[str, Any]]:
    """The frozen, well-formed manifest entries of one revision."""

    return [entry for entry in (revision.manifest_json or []) if isinstance(entry, dict) and isinstance(entry.get("document_id"), str)]


def _entry_origin(entry: dict[str, Any]) -> str:
    metadata = entry.get("metadata")
    return str(metadata.get("origin") or "provider") if isinstance(metadata, dict) else "provider"


class RevisionMaterialSource:
    """One frozen document's text, acquired through the shared execution chain.

    Provider originals are read from platform storage; device-local
    documents are requested per frozen identity through the authorized
    broker dispatch. Both ends re-check the frozen digest before text moves,
    so neither side can substitute content. Graph generation (#116), scoped
    graph QA (#117), and wiki generation (#118) all read material only
    through this class.
    """

    def __init__(self, session: AsyncSession, actor: ResourceActor, broker_factory: Callable[[], Any] | None, *, label: str = "knowledge-graph") -> None:
        self.session = session
        self.actor = actor
        self._broker_factory = broker_factory
        self._broker: Any = None
        # The dispatch identity records which surface asked for the document
        # (graph generation, scoped QA, wiki generation); the execution chain
        # and its re-verification stay shared.
        self._label = label

    async def document_text(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any]) -> str:
        if _entry_origin(entry) == LOCAL_IMPORT_ORIGIN:
            return await self._device_material(revision, entry, self._device_broker())
        return await self._provider_material(kb, entry)

    def _device_broker(self) -> Any:
        """The device broker, constructed lazily: a provider-only read
        never touches the broker at all."""

        if self._broker_factory is None:
            raise GraphMaterialFailure(GRAPH_DEVICE_UNAVAILABLE)
        if self._broker is None:
            self._broker = self._broker_factory()
        return self._broker

    async def _provider_material(self, kb: Any, entry: dict[str, Any]) -> str:
        """Read one server-owned original through the platform store.

        The stored bytes are verified against the frozen digest before any
        model call, so a drifted server file fails loudly instead of feeding
        the graph substitute content.
        """

        row = await self.session.get(KnowledgeDocument, str(entry["document_id"]))
        if row is None or row.resource_id != kb.id or row.status == "deleted":
            raise GraphMaterialFailure(GRAPH_DOCUMENT_UNAVAILABLE)
        path = get_paths().base_dir / row.storage_key
        try:
            raw = await asyncio.to_thread(path.read_bytes)
        except OSError:
            raise GraphMaterialFailure(GRAPH_DOCUMENT_UNAVAILABLE) from None
        if hashlib.sha256(raw).hexdigest() != str(entry.get("content_hash") or ""):
            raise GraphMaterialFailure(GRAPH_CONTENT_DRIFTED)
        if len(raw) > MAX_MATERIAL_BYTES:
            raise GraphMaterialFailure(GRAPH_DOCUMENT_TOO_LARGE)
        try:
            return raw.decode("utf-8")
        except UnicodeError:
            raise GraphMaterialFailure(GRAPH_DOCUMENT_NOT_TEXT) from None

    async def _device_material(self, revision: KnowledgeRevision, entry: dict[str, Any], broker: Any) -> str:
        """Request exactly one frozen document from its importing device.

        The payload carries the frozen identity fields only; the device
        re-validates the digest in its workspace and returns the document
        text only after its user approves the material request. The Server
        re-checks the digest on arrival, so the graph can only be built from
        the frozen bytes.
        """

        from app.device_control.broker import TaskStatus

        document_id = str(entry["document_id"])
        device_id = ""
        metadata = entry.get("metadata")
        if isinstance(metadata, dict):
            device_id = str(metadata.get("device_id") or "")
        connection = broker.connections.get(device_id) if device_id else None
        if (
            connection is None
            or not getattr(connection, "tasks_allowed", False)
            or getattr(connection, "owner_id", None) != str(self.actor.user_id)
            or LOCAL_KNOWLEDGE_MATERIAL_OPERATION not in getattr(connection, "capabilities", set())
        ):
            raise GraphMaterialFailure(GRAPH_DEVICE_UNAVAILABLE)

        identity = {
            "document_id": document_id,
            "filename": str(entry.get("filename") or ""),
            "content_hash": str(entry.get("content_hash") or ""),
        }
        record = await broker.send_task(
            device_id=device_id,
            operation=LOCAL_KNOWLEDGE_MATERIAL_OPERATION,
            path="",
            run_id=f"{self._label}:{revision.id}",
            tool_call_id="",
            expires_in=timedelta(minutes=5),
            payload_extra={
                "arguments": {
                    "revision_id": revision.id,
                    "manifest_hash": revision.manifest_hash,
                    "documents": [identity],
                },
                "operation": LOCAL_KNOWLEDGE_MATERIAL_OPERATION,
                "thread_id": self._label,
            },
        )
        while record.status in {
            TaskStatus.CREATED,
            TaskStatus.SENT,
            TaskStatus.ACKED,
            TaskStatus.CONSENT_REQUIRED,
            TaskStatus.CANCEL_REQUESTED,
            TaskStatus.PROGRESS,
        }:
            await asyncio.sleep(0.05)
            record = broker.get_task(record.task_id)
        if record.status is not TaskStatus.COMPLETED:
            code = str(getattr(record, "error_code", "") or "")
            # The device's own fixed categories stay verbatim; anything else
            # reads as a device denial instead of a fabricated cause.
            raise GraphMaterialFailure(
                code if code.startswith(("GRAPH_", "MATERIAL_", "KNOWLEDGE_", "INVALID_", "BULK_")) else GRAPH_DEVICE_DENIED
            )
        result = record.result
        if not isinstance(result, dict):
            raise GraphMaterialFailure(GRAPH_MATERIAL_REJECTED)
        if result.get("missing") is True:
            # The device answered and re-validated: this frozen document is
            # gone, drifted, or unreadable on that device. The reason maps to
            # a fixed category instead of a crash or a silent gap.
            reason = str(result.get("reason") or "")
            raise GraphMaterialFailure(_MATERIAL_MISSING_CODES.get(reason, GRAPH_DOCUMENT_UNAVAILABLE))
        if str(result.get("document_id") or "") != document_id or not isinstance(result.get("text"), str):
            raise GraphMaterialFailure(GRAPH_MATERIAL_REJECTED)
        text = result["text"]
        try:
            raw = text.encode("utf-8")
        except UnicodeError:  # pragma: no cover - str.encode never raises this
            raise GraphMaterialFailure(GRAPH_MATERIAL_REJECTED) from None
        if len(raw) > MAX_MATERIAL_BYTES:
            raise GraphMaterialFailure(GRAPH_MATERIAL_REJECTED)
        if hashlib.sha256(raw).hexdigest() != str(entry.get("content_hash") or ""):
            raise GraphMaterialFailure(GRAPH_MATERIAL_REJECTED)
        return text


class KnowledgeGraphGenerationService:
    """Per-Revision controlled graph generation and permission-bound views."""

    def __init__(
        self,
        session: AsyncSession,
        actor: ResourceActor,
        *,
        generator: Callable[[str], Any] | None = None,
        broker_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.resource_service = ResourceService(session, actor)
        self._generator = generator or generate_document_graph
        self._material_source = RevisionMaterialSource(session, actor, broker_factory)

    async def _knowledge_base(self, resource_id: str, *, modify: bool) -> Any:
        resource = await self.resource_service.get_visible(resource_id)
        if resource.type != "knowledge_base":
            raise ResourceNotFound(f"KnowledgeBase {resource_id} not found")
        if modify:
            # Generation derives and rewrites this KB's graph artifacts: the
            # same owner boundary as importing, publishing, and deleting.
            self.resource_service.assert_modify(resource)
        return resource

    async def _revision(self, resource_id: str, revision_id: str) -> KnowledgeRevision:
        revision = await self.session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.knowledge_base_id != resource_id:
            raise ResourceNotFound(f"Knowledge revision {revision_id} not found")
        return revision

    async def generate(self, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Generate the graph for one frozen revision, document by document.

        Material acquisition and model calls both run here, on the Server;
        each document succeeds or fails independently and its artifact row
        records exactly what happened.
        """

        kb = await self._knowledge_base(resource_id, modify=True)
        revision = await self._revision(resource_id, revision_id)
        entries = manifest_entries(revision)
        if not entries:
            raise ResourceConflict("This revision has no frozen documents to generate a graph from")

        rows: dict[str, KnowledgeGraphArtifact] = {}
        documents: list[dict[str, Any]] = []
        generated = failed = 0
        for entry in entries:
            document_id = str(entry["document_id"])
            try:
                text = await self._material_source.document_text(kb, revision, entry)
                graph = normalize_model_graph(await self._invoke_generator(text))
                row = await self._store_artifact(kb, revision, entry, graph)
                generated += 1
                status, error_code = STATUS_COMPLETED, None
            except GraphMaterialFailure as exc:
                row = await self._store_failure(kb, revision, entry, exc.code)
                failed += 1
                status, error_code = "failed", exc.code
            except ValueError:
                row = await self._store_failure(kb, revision, entry, GRAPH_MODEL_OUTPUT_INVALID)
                failed += 1
                status, error_code = "failed", GRAPH_MODEL_OUTPUT_INVALID
            except Exception:
                row = await self._store_failure(kb, revision, entry, GRAPH_MODEL_UNAVAILABLE)
                failed += 1
                status, error_code = "failed", GRAPH_MODEL_UNAVAILABLE
            rows[document_id] = row
            documents.append(
                {
                    "document_id": document_id,
                    "filename": str(entry.get("filename") or ""),
                    "content_hash": str(entry.get("content_hash") or ""),
                    "status": status,
                    "entity_count": row.entity_count,
                    "relation_count": row.relation_count,
                    "error_code": error_code,
                }
            )
        await self.session.flush()
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": aggregate_status(generated, failed),
            "generated": generated,
            "failed": failed,
            "documents": documents,
        }

    async def view(self, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Project the stored graph with its sources for a visible caller.

        Visibility is the KB's own: a caller without access reads a 404, a
        department member reads the same frozen bindings, and nothing from
        another revision ever appears here.
        """

        kb = await self._knowledge_base(resource_id, modify=False)
        revision = await self._revision(resource_id, revision_id)
        result = await self.session.execute(
            select(KnowledgeGraphArtifact).where(KnowledgeGraphArtifact.revision_id == revision.id).order_by(KnowledgeGraphArtifact.document_id)
        )
        artifacts = {row.document_id: row for row in result.scalars()}

        documents: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        generated = failed = 0
        for entry in manifest_entries(revision):
            document_id = str(entry["document_id"])
            filename = str(entry.get("filename") or "")
            artifact = artifacts.get(document_id)
            if artifact is None:
                documents.append({"document_id": document_id, "filename": filename, "status": STATUS_NOT_GENERATED})
                sources.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "content_hash": str(entry.get("content_hash") or ""),
                        "status": STATUS_NOT_GENERATED,
                        "error_code": None,
                    }
                )
                continue
            if artifact.status == STATUS_COMPLETED:
                generated += 1
            else:
                failed += 1
            documents.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "status": artifact.status,
                    "entity_count": artifact.entity_count,
                    "relation_count": artifact.relation_count,
                    "error_code": artifact.error_code,
                }
            )
            sources.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "content_hash": artifact.document_content_hash,
                    "status": artifact.status,
                    "error_code": artifact.error_code,
                }
            )
            if artifact.status != STATUS_COMPLETED:
                continue
            for entity in artifact.entities_json or []:
                entities.append({**entity, "document_id": document_id, "filename": filename})
            for relation in artifact.relations_json or []:
                relations.append({**relation, "document_id": document_id, "filename": filename})

        if not artifacts:
            status: str = STATUS_NOT_GENERATED
        else:
            status = aggregate_status(generated, failed)
        return {
            "knowledge_base_id": kb.id,
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "manifest_hash": revision.manifest_hash,
            "status": status,
            "generated": generated,
            "failed": failed,
            "documents": documents,
            "sources": sources,
            "entities": entities,
            "relations": relations,
        }

    async def _invoke_generator(self, text: str) -> dict:
        return await self._generator(text)

    async def _store_artifact(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any], graph: dict[str, list[dict[str, str]]]) -> KnowledgeGraphArtifact:
        await self._drop_existing(revision.id, str(entry["document_id"]))
        row = KnowledgeGraphArtifact(
            id=str(uuid.uuid4()),
            knowledge_base_id=kb.id,
            revision_id=revision.id,
            revision_no=revision.revision_no,
            manifest_hash=revision.manifest_hash,
            document_id=str(entry["document_id"]),
            document_filename=str(entry.get("filename") or ""),
            document_content_hash=str(entry.get("content_hash") or ""),
            status=STATUS_COMPLETED,
            entities_json=graph["entities"],
            relations_json=graph["relations"],
            entity_count=len(graph["entities"]),
            relation_count=len(graph["relations"]),
            error_code=None,
            error_message=None,
            generated_by=self.actor.user_id,
        )
        self.session.add(row)
        return row

    async def _store_failure(self, kb: Any, revision: KnowledgeRevision, entry: dict[str, Any], code: str) -> KnowledgeGraphArtifact:
        """A failed document stays an explicit, visible record — never silence."""

        await self._drop_existing(revision.id, str(entry["document_id"]))
        row = KnowledgeGraphArtifact(
            id=str(uuid.uuid4()),
            knowledge_base_id=kb.id,
            revision_id=revision.id,
            revision_no=revision.revision_no,
            manifest_hash=revision.manifest_hash,
            document_id=str(entry["document_id"]),
            document_filename=str(entry.get("filename") or ""),
            document_content_hash=str(entry.get("content_hash") or ""),
            status="failed",
            entities_json=[],
            relations_json=[],
            entity_count=0,
            relation_count=0,
            error_code=code,
            error_message=None,
            generated_by=self.actor.user_id,
        )
        self.session.add(row)
        return row

    async def _drop_existing(self, revision_id: str, document_id: str) -> None:
        await self.session.execute(
            delete(KnowledgeGraphArtifact).where(
                KnowledgeGraphArtifact.revision_id == revision_id,
                KnowledgeGraphArtifact.document_id == document_id,
            )
        )


def aggregate_status(generated: int, failed: int) -> str:
    if generated and not failed:
        return STATUS_COMPLETED
    if generated and failed:
        return STATUS_PARTIAL
    return STATUS_FAILED
