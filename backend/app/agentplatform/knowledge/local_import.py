"""Explicit local knowledge import registration from a paired Desktop (#112).

A local import freezes a private KnowledgeBase Revision manifest on the
platform: document identities, sizes, MIME types, and content hashes are the
governance record. Original files and the device-side index never upload, so
this service stores no content, creates no provider dataset, and never
touches the KnowledgeBase pointer: the frozen bytes stay on the device that
imported them, and later imports always append a new revision.
"""

from __future__ import annotations

import mimetypes
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.knowledge import documents as knowledge_documents
from app.agentplatform.knowledge.models import KnowledgeRevision
from app.agentplatform.knowledge.revisions import (
    LOCAL_IMPORT_ORIGIN,
    _revision_payload,
    canonical_manifest_hash,
)
from app.agentplatform.resources.service import ResourceActor, ResourceNotFound, ResourceService

MAX_IMPORT_DOCUMENTS = 200


class LocalImportValidationError(ValueError):
    """Raised when a local import manifest cannot be safely registered."""


class KnowledgeLocalImportService:
    def __init__(self, session: AsyncSession, actor: ResourceActor) -> None:
        self.session = session
        self.resource_service = ResourceService(session, actor)

    async def _knowledge_base(self, resource_id: str) -> object:
        resource = await self.resource_service.get_visible(resource_id)
        if resource.type != "knowledge_base":
            raise ResourceNotFound(f"KnowledgeBase {resource_id} not found")
        self.resource_service.assert_modify(resource)
        return resource

    async def register_local_import(
        self,
        resource_id: str,
        *,
        documents: list,
        device_id: str | None = None,
    ) -> dict[str, object]:
        """Append one immutable local-import revision from device metadata.

        Every entry is validated before anything is written; a rejected
        manifest leaves no revision row, and a successful registration is
        draft-only with an empty provider mapping.
        """

        await self._knowledge_base(resource_id)
        if not isinstance(documents, list) or not documents:
            raise LocalImportValidationError("A local import requires at least one document")
        if len(documents) > MAX_IMPORT_DOCUMENTS:
            raise LocalImportValidationError("A local import accepts at most 200 documents")
        if device_id is not None and (
            not isinstance(device_id, str) or not device_id.strip() or len(device_id.strip()) > 128
        ):
            raise LocalImportValidationError("Device identity must be a short plain token")
        max_size = knowledge_documents._max_document_size()
        entries: list[dict[str, object]] = []
        seen_hashes: set[str] = set()
        for document in documents:
            if not isinstance(document, dict):
                raise LocalImportValidationError("Each local import document must be an object")
            try:
                filename = knowledge_documents._safe_document_filename(document.get("filename"))
            except knowledge_documents.DocumentValidationError as exc:
                raise LocalImportValidationError(str(exc)) from exc
            content_hash = document.get("content_hash")
            if (
                not isinstance(content_hash, str)
                or len(content_hash) != 64
                or any(character not in "0123456789abcdef" for character in content_hash)
            ):
                raise LocalImportValidationError("Document content hash must be a lowercase SHA-256 digest")
            if content_hash in seen_hashes:
                raise LocalImportValidationError("Duplicate document content in one local import")
            seen_hashes.add(content_hash)
            size_bytes = document.get("size_bytes")
            if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
                raise LocalImportValidationError("Document size must be a non-negative integer")
            if size_bytes > max_size:
                raise LocalImportValidationError("Document exceeds the maximum local import size")
            mime_type = document.get("mime_type")
            if mime_type is not None and (not isinstance(mime_type, str) or not mime_type.strip() or len(mime_type) > 128):
                raise LocalImportValidationError("Document MIME type must be a short token")
            mime_type = (mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream").lower()
            metadata: dict[str, object] = {"origin": LOCAL_IMPORT_ORIGIN}
            if device_id is not None:
                metadata["device_id"] = device_id.strip()
            # The document identity is derived from the frozen content, never
            # random: re-importing the same bytes yields the same document_id,
            # so the canonical manifest hash stays the content's governance
            # identity instead of drifting per import.
            document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"local-import:{filename}:{content_hash}"))
            entries.append(
                {
                    "document_id": document_id,
                    "content_hash": content_hash,
                    "filename": filename,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                    "metadata": metadata,
                }
            )
        highest = await self.session.scalar(
            select(func.max(KnowledgeRevision.revision_no)).where(KnowledgeRevision.knowledge_base_id == resource_id)
        )
        revision = KnowledgeRevision(
            id=str(uuid.uuid4()),
            knowledge_base_id=resource_id,
            revision_no=int(highest or 0) + 1,
            status="draft",
            manifest_hash=canonical_manifest_hash(entries),
            manifest_json=entries,
            provider_doc_map_json={},
            document_count=len(entries),
            created_by=self.resource_service.actor.user_id,
        )
        self.session.add(revision)
        await self.session.flush()
        return _revision_payload(revision, documents=list(revision.manifest_json))
