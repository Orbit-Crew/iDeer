"""Explicit server-side publication of a device-local KnowledgeBase (#115).

A registered local-import revision (#112) freezes document identities only;
the original bytes stay on the importing device. Publication is the owner's
explicit, confirmed decision to create an independent server-side copy of one
frozen revision:

- the copy is a NEW private KnowledgeBase resource with its own lifecycle;
  the device KB is never re-scoped, its visibility is never flipped, and its
  frozen revisions stay draft (the only LIVE pointer move remains #113's
  activate-local);
- content travels only after the destination has been shown and the user has
  explicitly confirmed, and only through the platform's own document upload
  and revision publish machinery;
- the copy's frozen revision manifest carries a ``published_from`` provenance
  block naming the source KB, revision, and manifest hash, so the managed
  origin stays auditable on the copy itself;
- nothing syncs back: later device imports never touch an existing copy, and
  publishing a new revision creates a new copy.

Team access is granted exclusively through the existing visibility
application and approval flow on the copy — never by widening the device KB.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentplatform.knowledge.models import KnowledgeDocument, KnowledgeRevision
from app.agentplatform.knowledge.provider import KnowledgeProvider
from app.agentplatform.knowledge.revisions import (
    KnowledgeRevisionService,
    is_local_import_revision,
)
from app.agentplatform.resource_models import Resource
from app.agentplatform.resources.service import (
    ResourceActor,
    ResourceConflict,
    ResourceNotFound,
    ResourceService,
)

# Manifest metadata marker proving the managed origin of a published copy
# (mirrors LOCAL_IMPORT_ORIGIN for device-local registrations).
LOCAL_PUBLICATION_PROVENANCE = "local_publication"

# Fixed failure/permission categories surfaced to the Desktop and the Web.
CONFIRMATION_REQUIRED = "LOCAL_PUBLISH_CONFIRMATION_REQUIRED"
COPY_MISSING = "LOCAL_PUBLISH_COPY_MISSING"
CONTENT_INCOMPLETE = "LOCAL_PUBLISH_CONTENT_INCOMPLETE"
CONTENT_DRIFTED = "LOCAL_PUBLISH_CONTENT_DRIFTED"
ALREADY_PUBLISHED = "LOCAL_PUBLISH_ALREADY_PUBLISHED"


def copy_slug_for(source_slug: str, revision_no: int) -> str:
    """The deterministic slug of the server copy of one frozen revision.

    Determinism makes confirmation idempotent: retrying an interrupted
    publication reuses the same copy instead of duplicating it.
    """

    return f"{source_slug[:96]}-pub-r{revision_no}"


def copy_display_name_for(source_display_name: str, revision_no: int) -> str:
    return f"{source_display_name[:220]} · 服务端副本 R{revision_no}"


class KnowledgeLocalPublishService:
    """Owner-gated explicit publication of one local-import revision."""

    def __init__(self, session: AsyncSession, actor: ResourceActor) -> None:
        self.session = session
        self.resource_service = ResourceService(session, actor)
        self._revisions = KnowledgeRevisionService(session, actor)

    async def _knowledge_base(self, resource_id: str) -> Resource:
        resource = await self.resource_service.get_visible(resource_id)
        if resource.type != "knowledge_base":
            raise ResourceNotFound(f"KnowledgeBase {resource_id} not found")
        # Publication is an owner decision about this KB's content: the same
        # modify boundary as the import that created the frozen revision.
        self.resource_service.assert_modify(resource)
        return resource

    async def _source_revision(self, resource_id: str, revision_id: str) -> KnowledgeRevision:
        revision = await self.session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.knowledge_base_id != resource_id:
            raise ResourceNotFound(f"Knowledge revision {revision_id} not found")
        if not is_local_import_revision(revision) or revision.status != "draft":
            raise ResourceConflict("Only a registered local import revision can be published to the server")
        return revision

    async def _find_copy(self, owner_id: str, slug: str) -> Resource | None:
        row = await self.session.execute(
            select(Resource).where(
                Resource.type == "knowledge_base",
                Resource.owner_id == owner_id,
                Resource.slug == slug,
            )
        )
        return row.scalar_one_or_none()

    async def _copy_documents(self, copy_id: str) -> list[KnowledgeDocument]:
        rows = await self.session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.resource_id == copy_id, KnowledgeDocument.status != "deleted")
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        )
        return list(rows.scalars().all())

    async def _copy_revision(self, copy_id: str) -> KnowledgeRevision | None:
        row = await self.session.execute(
            select(KnowledgeRevision)
            .where(KnowledgeRevision.knowledge_base_id == copy_id)
            .order_by(KnowledgeRevision.revision_no)
        )
        return row.scalars().first()

    def _missing_documents(self, entries: list[dict], documents: list[KnowledgeDocument]) -> list[str]:
        """Frozen manifest documents whose verified content is not on the copy yet."""

        ready_hashes = {document.content_hash for document in documents if document.status == "ready"}
        return [str(entry["filename"]) for entry in entries if str(entry["content_hash"]) not in ready_hashes]

    def _status(
        self,
        copy: Resource | None,
        documents: list[KnowledgeDocument],
        revision: KnowledgeRevision | None,
        entries: list[dict],
    ) -> str:
        if copy is None:
            return "none"
        if revision is None:
            if not self._missing_documents(entries, documents) and len(documents) == len(entries):
                return "ready_to_complete"
            return "awaiting_content"
        if revision.status in {"published", "superseded"}:
            return "published"
        if revision.status == "indexing":
            return "publishing"
        if revision.status == "failed":
            return "failed"
        return f"revision_{revision.status}"

    async def _publication_payload(
        self,
        revision: KnowledgeRevision,
        source: Resource,
        copy: Resource | None,
    ) -> dict[str, object]:
        entries = list(revision.manifest_json or [])
        documents = await self._copy_documents(copy.id) if copy is not None else []
        copy_revision = await self._copy_revision(copy.id) if copy is not None else None
        return {
            "source": {
                "resource_id": source.id,
                "display_name": source.display_name,
                "revision_id": revision.id,
                "revision_no": revision.revision_no,
                "manifest_hash": revision.manifest_hash,
                "document_count": revision.document_count,
            },
            "status": self._status(copy, documents, copy_revision, entries),
            "missing_documents": self._missing_documents(entries, documents),
            "copy": None if copy is None else {
                "resource_id": copy.id,
                "slug": copy.slug,
                "display_name": copy.display_name,
                "visibility": copy.visibility,
                "document_count": len(documents),
                "documents": [
                    {
                        "filename": document.original_filename,
                        "content_hash": document.content_hash,
                        "size_bytes": document.size_bytes,
                        "status": document.status,
                    }
                    for document in documents
                ],
            },
            "revision": None if copy_revision is None else {
                "resource_id": copy.id,
                "id": copy_revision.id,
                "revision_no": copy_revision.revision_no,
                "status": copy_revision.status,
                "manifest_hash": copy_revision.manifest_hash,
                "failure_code": copy_revision.failure_code,
                "failure_message": copy_revision.failure_message,
                "published_at": copy_revision.published_at.isoformat() if copy_revision.published_at else None,
                "provider_dataset_id": copy_revision.provider_dataset_id,
            },
        }

    # --- Explicit publication steps ----------------------------------------

    async def preview_publication(self, resource_id: str, revision_id: str) -> dict[str, object]:
        """Read-only preview of what an explicit publication would upload.

        The preview states the destination and the exact document identities;
        it performs no write, no upload, and creates no copy.
        """

        source = await self._knowledge_base(resource_id)
        revision = await self._source_revision(resource_id, revision_id)
        return {
            "source": {
                "resource_id": source.id,
                "display_name": source.display_name,
                "revision_id": revision.id,
                "revision_no": revision.revision_no,
                "manifest_hash": revision.manifest_hash,
                "document_count": revision.document_count,
            },
            "documents": [
                {
                    "document_id": str(entry["document_id"]),
                    "filename": str(entry["filename"]),
                    "size_bytes": entry.get("size_bytes"),
                    "mime_type": entry.get("mime_type"),
                    "content_hash": str(entry["content_hash"]),
                }
                for entry in revision.manifest_json or []
            ],
            "destination": {
                "kind": "server_copy",
                "display_name": copy_display_name_for(source.display_name, revision.revision_no),
                "slug": copy_slug_for(source.slug, revision.revision_no),
                "visibility": "private",
                "governance": "visibility_application_required",
            },
            "upload_policy": {
                "requires_explicit_confirmation": True,
                "device_kb_unchanged": True,
                "two_way_sync": False,
            },
        }

    async def confirm_publication(self, resource_id: str, revision_id: str, *, confirmed: bool) -> dict[str, object]:
        """Create (or reuse) the private server copy after explicit confirmation.

        Without ``confirmed=True`` nothing is created and nothing is uploaded:
        the refusal is the fixed ``LOCAL_PUBLISH_CONFIRMATION_REQUIRED``
        category, so a preview alone can never impersonate a publication.
        """

        source = await self._knowledge_base(resource_id)
        revision = await self._source_revision(resource_id, revision_id)
        if confirmed is not True:
            raise ResourceConflict(CONFIRMATION_REQUIRED)
        slug = copy_slug_for(source.slug, revision.revision_no)
        copy = await self._find_copy(self.resource_service.actor.user_id, slug)
        if copy is None:
            copy = await self.resource_service.create_resource(
                resource_type="knowledge_base",
                slug=slug,
                display_name=copy_display_name_for(source.display_name, revision.revision_no),
                storage_kind="database",
            )
        else:
            existing = await self._copy_revision(copy.id)
            if existing is not None and existing.manifest_hash != revision.manifest_hash:
                raise ResourceConflict("This revision is already published to a different server copy")
        return await self._publication_payload(revision, source, copy)

    async def complete_publication(
        self,
        resource_id: str,
        revision_id: str,
        *,
        provider: KnowledgeProvider,
    ) -> dict[str, object]:
        """Verify uploaded content against the frozen manifest, then publish.

        Every frozen manifest document must exist on the copy as a ready
        platform document with the identical content hash, and nothing else
        may have been uploaded. On success the copy's own revision is created
        through the standard freezing path and published with the standard
        provider build; the source KB and its revisions are never touched.
        """

        source = await self._knowledge_base(resource_id)
        revision = await self._source_revision(resource_id, revision_id)
        slug = copy_slug_for(source.slug, revision.revision_no)
        copy = await self._find_copy(self.resource_service.actor.user_id, slug)
        if copy is None:
            raise ResourceConflict(COPY_MISSING)
        entries = list(revision.manifest_json or [])
        documents = await self._copy_documents(copy.id)
        manifest_hashes = {str(entry["content_hash"]) for entry in entries}
        document_hashes = {document.content_hash for document in documents}
        if document_hashes - manifest_hashes or len(documents) > len(entries):
            raise ResourceConflict(CONTENT_DRIFTED)
        missing = self._missing_documents(entries, documents)
        if missing:
            raise ResourceConflict(f"{CONTENT_INCOMPLETE}: {', '.join(missing)}")

        copy_revision = await self._copy_revision(copy.id)
        if copy_revision is None:
            # The provenance block is frozen into the copy's manifest entries,
            # so the managed origin travels with the immutable revision.
            by_hash = {document.content_hash: document for document in documents}
            for entry in entries:
                document = by_hash[str(entry["content_hash"])]
                document.metadata_json = {
                    **(document.metadata_json or {}),
                    "origin": LOCAL_PUBLICATION_PROVENANCE,
                    "published_from": {
                        "source_knowledge_base_id": source.id,
                        "source_revision_id": revision.id,
                        "source_manifest_hash": revision.manifest_hash,
                    },
                }
            await self.session.flush()
            copy_revision_payload = await self._revisions.create_revision(copy.id)
            copy_revision = await self.session.get(KnowledgeRevision, str(copy_revision_payload["id"]))
        elif copy_revision.status in {"published", "superseded"}:
            return await self._publication_payload(revision, source, copy)
        else:
            copy_document_hashes = {str(entry.get("content_hash")) for entry in copy_revision.manifest_json or []}
            if copy_document_hashes != manifest_hashes:
                raise ResourceConflict(CONTENT_DRIFTED)

        # The copy publishes through the exact same gates as any KB: integrity,
        # eval policy, build verification, then its own LIVE pointer move.
        await self._revisions.publish_revision(copy.id, copy_revision.id, provider=provider)
        return await self._publication_payload(revision, source, copy)

    async def get_publication_status(self, resource_id: str, revision_id: str) -> dict[str, object]:
        """Derived publication state: no publication table, no stale status.

        The state is recomputed from the copy resource, its documents, and its
        revision on every read, so an interrupted upload or a failed build is
        always visible exactly as it is.
        """

        source = await self._knowledge_base(resource_id)
        revision = await self._source_revision(resource_id, revision_id)
        slug = copy_slug_for(source.slug, revision.revision_no)
        copy = await self._find_copy(self.resource_service.actor.user_id, slug)
        return await self._publication_payload(revision, source, copy)
