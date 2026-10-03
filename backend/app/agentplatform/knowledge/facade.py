"""Single seam between the knowledge domain and its HTTP surface.

Routes resolve the request into an actor and an intent and call
:class:`KnowledgeFacade`; the five knowledge services, the provider-passing
rules, session commits, and audit wiring stay implementation details behind
this seam. Visibility guarding itself lives in :class:`ResourceService` and is
invoked on every intent through the services, so a hidden KnowledgeBase reads
as 404 and a non-modifiable one as 403 no matter which intent touches it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.agentplatform.knowledge.documents import KnowledgeDocumentService
from app.agentplatform.knowledge.eval_cases import KnowledgeEvalCaseService
from app.agentplatform.resources.service import ResourceActor

AuditSink = Callable[..., Awaitable[None]]


class KnowledgeFacade:
    """Owns service construction, commit discipline, and audit for the
    KnowledgeBase document and eval-case operations."""

    def __init__(self, session_factory: Callable[[], Any], *, audit: AuditSink) -> None:
        self._session_factory = session_factory
        self._audit = audit

    def _documents(self, session: Any, actor: ResourceActor) -> KnowledgeDocumentService:
        return KnowledgeDocumentService(session, actor)

    def _eval_cases(self, session: Any, actor: ResourceActor) -> KnowledgeEvalCaseService:
        return KnowledgeEvalCaseService(session, actor)

    # --- Documents ---------------------------------------------------------

    async def list_documents(self, actor: ResourceActor, resource_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            documents = await self._documents(session, actor).list_documents(resource_id)
            return {"items": documents, "total": len(documents)}

    async def upload_document(self, actor: ResourceActor, resource_id: str, upload: Any) -> dict[str, Any]:
        async with self._session_factory() as session:
            document = await self._documents(session, actor).upload(resource_id, upload)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_document_uploaded",
            "knowledge_document",
            str(document["id"]),
            {"resource_id": resource_id, "content_hash": document["content_hash"], "size": document["size"]},
        )
        return document

    async def get_document(self, actor: ResourceActor, resource_id: str, document_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._documents(session, actor).get_document(document_id, resource_id=resource_id)

    async def update_document(
        self,
        actor: ResourceActor,
        resource_id: str,
        document_id: str,
        *,
        title: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            document = await self._documents(session, actor).update_document(
                document_id,
                resource_id=resource_id,
                title=title,
                metadata=metadata,
            )
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_document_updated",
            "knowledge_document",
            document_id,
            {"resource_id": resource_id, "changed_title": title is not None, "changed_metadata": metadata is not None},
        )
        return document

    async def request_document_retry(self, actor: ResourceActor, resource_id: str, document_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            document = await self._documents(session, actor).request_retry(document_id, resource_id=resource_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_document_retry_requested",
            "knowledge_document",
            document_id,
            {"resource_id": resource_id},
        )
        return document

    async def request_document_rebuild(self, actor: ResourceActor, resource_id: str, document_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            document = await self._documents(session, actor).request_retry(document_id, resource_id=resource_id, rebuild=True)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_document_rebuild_requested",
            "knowledge_document",
            document_id,
            {"resource_id": resource_id},
        )
        return document

    async def request_document_delete(self, actor: ResourceActor, resource_id: str, document_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            document = await self._documents(session, actor).request_delete(document_id, resource_id=resource_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_document_delete_requested",
            "knowledge_document",
            document_id,
            {"resource_id": resource_id, "status": document["status"], "failure_code": document["failure_code"]},
        )
        return document

    async def request_initialization(self, actor: ResourceActor, resource_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            result = await self._documents(session, actor).request_initialization(resource_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_initialization_requested",
            "knowledge_base",
            resource_id,
            {"status": result["status"]},
        )
        return result

    # --- Eval cases --------------------------------------------------------

    async def create_eval_case(
        self,
        actor: ResourceActor,
        resource_id: str,
        *,
        question: str,
        expected_document_ids: list[str],
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            case = await self._eval_cases(session, actor).create_case(
                resource_id,
                question=question,
                expected_document_ids=expected_document_ids,
                tags=tags,
            )
            await session.commit()
        await self._audit(
            actor.user_id,
            "eval_case_created",
            "knowledge_eval_case",
            str(case["id"]),
            {
                "resource_id": resource_id,
                "version_no": case["version_no"],
                "content_hash": case["content_hash"],
                "expected_document_count": len(case["expected_document_ids"]),
            },
        )
        return case

    async def list_eval_cases(self, actor: ResourceActor, resource_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            cases = await self._eval_cases(session, actor).list_cases(resource_id)
            return {"items": cases, "total": len(cases)}

    async def eval_case_revision_applicability(self, actor: ResourceActor, resource_id: str, revision_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._eval_cases(session, actor).revision_applicability(resource_id, revision_id)

    async def get_eval_case(self, actor: ResourceActor, resource_id: str, case_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._eval_cases(session, actor).get_case(resource_id, case_id)

    async def update_eval_case(
        self,
        actor: ResourceActor,
        resource_id: str,
        case_id: str,
        *,
        question: str | None,
        expected_document_ids: list[str] | None,
        tags: list[str] | None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            case = await self._eval_cases(session, actor).update_case(
                resource_id,
                case_id,
                question=question,
                expected_document_ids=expected_document_ids,
                tags=tags,
            )
            await session.commit()
        await self._audit(
            actor.user_id,
            "eval_case_updated",
            "knowledge_eval_case",
            case_id,
            {"resource_id": resource_id, "version_no": case["version_no"], "content_hash": case["content_hash"]},
        )
        return case

    async def delete_eval_case(self, actor: ResourceActor, resource_id: str, case_id: str) -> None:
        async with self._session_factory() as session:
            await self._eval_cases(session, actor).delete_case(resource_id, case_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "eval_case_deleted",
            "knowledge_eval_case",
            case_id,
            {"resource_id": resource_id},
        )
