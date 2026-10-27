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

from sqlalchemy.exc import SQLAlchemyError

from app.agentplatform.knowledge.documents import KnowledgeDocumentService
from app.agentplatform.knowledge.eval_cases import KnowledgeEvalCaseService
from app.agentplatform.knowledge.evaluation import KnowledgeEvaluationService
from app.agentplatform.knowledge.graph_generation import KnowledgeGraphGenerationService
from app.agentplatform.knowledge.local_import import KnowledgeLocalImportService
from app.agentplatform.knowledge.local_publish import KnowledgeLocalPublishService
from app.agentplatform.knowledge.provider import KnowledgeProvider, KnowledgeProviderUnavailable
from app.agentplatform.knowledge.ragflow import configured_ragflow_provider
from app.agentplatform.knowledge.retrieval_test import KnowledgeRetrievalTestService, RetrievalTestStorageUnavailable
from app.agentplatform.knowledge.revisions import KnowledgeRevisionService, execute_publish
from app.agentplatform.resources.service import ResourceActor

AuditSink = Callable[..., Awaitable[None]]
# HTTP surfaces hand the facade their background-task scheduler so the
# publish/prepare build stays the seam's business without coupling the
# knowledge package to a web-framework type.
BuildScheduler = Callable[..., None]
ProviderFactory = Callable[[], KnowledgeProvider | None]
SearchCall = Callable[..., Any]
SettingsFactory = Callable[[], Any]


class KnowledgeFacade:
    """Owns service construction, provider acquisition, commit discipline, and
    audit for the KnowledgeBase document, revision, retrieval-test, and
    evaluation operations."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        audit: AuditSink,
        provider_factory: ProviderFactory = configured_ragflow_provider,
        search: SearchCall | None = None,
        settings_factory: SettingsFactory | None = None,
        graph_generator: Any | None = None,
        graph_broker_factory: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit = audit
        self._provider_factory = provider_factory
        self._search = search
        self._settings_factory = settings_factory
        self._graph_generator = graph_generator
        self._graph_broker_factory = graph_broker_factory

    def _documents(self, session: Any, actor: ResourceActor) -> KnowledgeDocumentService:
        return KnowledgeDocumentService(session, actor)

    def _eval_cases(self, session: Any, actor: ResourceActor) -> KnowledgeEvalCaseService:
        return KnowledgeEvalCaseService(session, actor)

    def _revisions(self, session: Any, actor: ResourceActor) -> KnowledgeRevisionService:
        return KnowledgeRevisionService(session, actor)

    def _retrieval_tests(self, session: Any, actor: ResourceActor) -> KnowledgeRetrievalTestService:
        return KnowledgeRetrievalTestService(session, actor, search=self._search, settings_factory=self._settings_factory)

    def _evaluations(self, session: Any, actor: ResourceActor) -> KnowledgeEvaluationService:
        return KnowledgeEvaluationService(session, actor, search=self._search, settings_factory=self._settings_factory)

    def _provider(self) -> KnowledgeProvider:
        """Resolve the configured knowledge provider or refuse the intent."""
        provider = self._provider_factory()
        if provider is None:
            raise KnowledgeProviderUnavailable("No knowledge provider is configured")
        return provider

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

    # --- Revisions ---------------------------------------------------------

    async def create_revision(self, actor: ResourceActor, resource_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            revision = await self._revisions(session, actor).create_revision(resource_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_revision_created",
            "knowledge_revision",
            str(revision["id"]),
            {
                "resource_id": resource_id,
                "revision_no": revision["revision_no"],
                "manifest_hash": revision["manifest_hash"],
                "document_count": revision["document_count"],
            },
        )
        return revision

    async def prepare_revision(
        self,
        actor: ResourceActor,
        resource_id: str,
        revision_id: str,
        *,
        schedule: BuildScheduler,
    ) -> dict[str, Any]:
        """Start building a candidate index without changing the pointer."""
        provider = self._provider()
        async with self._session_factory() as session:
            revision = await self._revisions(session, actor).prepare_revision(resource_id, revision_id, provider=provider)
            await session.commit()
        if revision["status"] == "indexing":
            schedule(
                execute_publish,
                self._session_factory,
                resource_id=resource_id,
                revision_id=revision_id,
                actor_id=actor.user_id,
                provider=provider,
                execution_token=revision.get("publish_execution_token"),
                activate=False,
            )
        await self._audit(
            actor.user_id,
            "knowledge_revision_prepare_requested",
            "knowledge_revision",
            revision_id,
            {"resource_id": resource_id, "revision_no": revision["revision_no"]},
        )
        return revision

    async def list_revisions(self, actor: ResourceActor, resource_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            revisions = await self._revisions(session, actor).list_revisions(resource_id)
            return {"items": revisions, "total": len(revisions)}

    async def get_revision(self, actor: ResourceActor, resource_id: str, revision_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._revisions(session, actor).get_revision(resource_id, revision_id)

    async def publish_revision(
        self,
        actor: ResourceActor,
        resource_id: str,
        revision_id: str,
        *,
        schedule: BuildScheduler,
    ) -> dict[str, Any]:
        """Gate a candidate into the ``indexing`` build state and schedule the
        provider build; the pointer moves only after the build verifies."""
        provider = self._provider()
        async with self._session_factory() as session:
            revision = await self._revisions(session, actor).publish_revision(resource_id, revision_id, provider=provider)
            await session.commit()
        schedule(
            execute_publish,
            self._session_factory,
            resource_id=resource_id,
            revision_id=revision_id,
            actor_id=actor.user_id,
            provider=provider,
            execution_token=revision.get("publish_execution_token"),
        )
        await self._audit(
            actor.user_id,
            "knowledge_revision_publish_requested",
            "knowledge_revision",
            revision_id,
            {"resource_id": resource_id, "revision_no": revision["revision_no"]},
        )
        return revision

    # --- Local imports -----------------------------------------------------

    def _local_imports(self, session: Any, actor: ResourceActor) -> KnowledgeLocalImportService:
        return KnowledgeLocalImportService(session, actor)

    def _local_publications(self, session: Any, actor: ResourceActor) -> KnowledgeLocalPublishService:
        return KnowledgeLocalPublishService(session, actor)

    def _graph_generations(self, session: Any, actor: ResourceActor) -> KnowledgeGraphGenerationService:
        return KnowledgeGraphGenerationService(
            session,
            actor,
            generator=self._graph_generator,
            broker_factory=self._graph_broker_factory,
        )

    async def generate_graph(self, actor: ResourceActor, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Orchestrate controlled graph generation for one frozen revision (#116).

        Every model call runs on the Server; device material is requested per
        frozen document through the authorized dispatch. The per-document
        results — successes and fixed-category failures alike — are the
        generation's honest outcome.
        """
        async with self._session_factory() as session:
            result = await self._graph_generations(session, actor).generate(resource_id, revision_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_graph_generated",
            "knowledge_base",
            resource_id,
            {
                "revision_id": revision_id,
                "status": result.get("status"),
                "generated": result.get("generated"),
                "failed": result.get("failed"),
            },
        )
        return result

    async def graph_view(self, actor: ResourceActor, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Project the stored graph, its sources, and its generation status."""
        async with self._session_factory() as session:
            return await self._graph_generations(session, actor).view(resource_id, revision_id)

    async def register_local_import(
        self,
        actor: ResourceActor,
        resource_id: str,
        *,
        documents: list,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one explicit local-import revision from device metadata."""
        async with self._session_factory() as session:
            revision = await self._local_imports(session, actor).register_local_import(
                resource_id,
                documents=documents,
                device_id=device_id,
            )
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_local_import_registered",
            "knowledge_revision",
            str(revision["id"]),
            {
                "resource_id": resource_id,
                "revision_no": revision["revision_no"],
                "manifest_hash": revision["manifest_hash"],
                "document_count": revision["document_count"],
            },
        )
        return revision

    async def activate_local_revision(
        self,
        actor: ResourceActor,
        resource_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        """Anchor a device-local KnowledgeBase on one local-import revision (#113)."""
        async with self._session_factory() as session:
            revision = await self._local_imports(session, actor).activate_local_revision(resource_id, revision_id)
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_local_revision_activated",
            "knowledge_revision",
            str(revision["id"]),
            {
                "resource_id": resource_id,
                "revision_no": revision["revision_no"],
                "manifest_hash": revision["manifest_hash"],
            },
        )
        return revision

    # --- Local publications (#115) ------------------------------------------

    async def preview_local_publication(self, actor: ResourceActor, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Read-only preview of one explicit server publication; no side effects."""
        async with self._session_factory() as session:
            return await self._local_publications(session, actor).preview_publication(resource_id, revision_id)

    async def confirm_local_publication(
        self,
        actor: ResourceActor,
        resource_id: str,
        revision_id: str,
        *,
        confirmed: bool,
    ) -> dict[str, Any]:
        """Create the private server copy after the owner's explicit confirmation."""
        async with self._session_factory() as session:
            publication = await self._local_publications(session, actor).confirm_publication(
                resource_id,
                revision_id,
                confirmed=confirmed,
            )
            await session.commit()
        if confirmed:
            await self._audit(
                actor.user_id,
                "knowledge_local_publication_confirmed",
                "knowledge_base",
                resource_id,
                {
                    "revision_id": revision_id,
                    "copy_resource_id": (publication.get("copy") or {}).get("resource_id"),
                },
            )
        return publication

    async def complete_local_publication(
        self,
        actor: ResourceActor,
        resource_id: str,
        revision_id: str,
        *,
        schedule: BuildScheduler,
    ) -> dict[str, Any]:
        """Verify uploaded content, freeze the copy revision, and start its build."""
        provider = self._provider()
        async with self._session_factory() as session:
            publication = await self._local_publications(session, actor).complete_publication(
                resource_id,
                revision_id,
                provider=provider,
            )
            await session.commit()
        copy_revision = publication.get("revision") or {}
        if copy_revision.get("status") == "indexing" and copy_revision.get("id"):
            schedule(
                execute_publish,
                self._session_factory,
                resource_id=str(copy_revision.get("resource_id")),
                revision_id=str(copy_revision["id"]),
                actor_id=actor.user_id,
                provider=provider,
                execution_token=None,
            )
        await self._audit(
            actor.user_id,
            "knowledge_local_publication_completed",
            "knowledge_base",
            resource_id,
            {
                "revision_id": revision_id,
                "copy_resource_id": (publication.get("copy") or {}).get("resource_id"),
                "copy_revision_status": copy_revision.get("status"),
            },
        )
        return publication

    async def get_local_publication(self, actor: ResourceActor, resource_id: str, revision_id: str) -> dict[str, Any]:
        """Derived publication state for status, permission, and failure visibility."""
        async with self._session_factory() as session:
            return await self._local_publications(session, actor).get_publication_status(resource_id, revision_id)

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

    # --- Retrieval tests ---------------------------------------------------

    async def create_retrieval_test(
        self,
        actor: ResourceActor,
        resource_id: str,
        *,
        revision_id: str,
        query: str,
        top_k: int | None,
        profile_id: str,
    ) -> dict[str, Any]:
        """Execute and archive one bounded retrieval probe."""
        async with self._session_factory() as session:
            service = self._retrieval_tests(session, actor)
            try:
                payload = await service.execute(resource_id, revision_id, query=query, top_k=top_k, profile_id=profile_id)
                await session.commit()
            except SQLAlchemyError as exc:
                raise RetrievalTestStorageUnavailable("The retrieval test could not be archived; try again later.") from exc
        await self._audit(
            actor.user_id,
            "knowledge_retrieval_test_executed",
            "knowledge_base",
            resource_id,
            {
                "resource_id": resource_id,
                "revision_id": payload["revision_id"],
                "test_id": payload["id"],
                "result_status": payload["result_status"],
            },
        )
        return payload

    async def list_retrieval_tests(self, actor: ResourceActor, resource_id: str, *, offset: int, limit: int) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._retrieval_tests(session, actor).list_tests(resource_id, offset=offset, limit=limit)

    async def get_retrieval_test(self, actor: ResourceActor, resource_id: str, test_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._retrieval_tests(session, actor).get_test(resource_id, test_id)

    # --- Evaluations -------------------------------------------------------

    async def create_evaluation(
        self,
        actor: ResourceActor,
        resource_id: str,
        *,
        revision_id: str,
        profile_id: str,
        top_k: int,
        case_ids: list[str] | None,
    ) -> dict[str, Any]:
        """Freeze and enqueue one bounded profile evaluation."""
        async with self._session_factory() as session:
            payload = await self._evaluations(session, actor).start(
                resource_id,
                revision_id,
                profile_id=profile_id,
                top_k=top_k,
                case_ids=case_ids,
            )
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_evaluation_started",
            "knowledge_base",
            resource_id,
            {"run_id": payload["id"], "revision_id": payload["revision_id"]},
        )
        return payload

    async def list_evaluations(self, actor: ResourceActor, resource_id: str, *, offset: int, limit: int) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._evaluations(session, actor).list_runs(resource_id, offset=offset, limit=limit)

    async def get_evaluation(self, actor: ResourceActor, resource_id: str, run_id: str, *, result_offset: int, result_limit: int) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._evaluations(session, actor).get_run(resource_id, run_id, result_offset=result_offset, result_limit=result_limit)

    async def retry_evaluation(self, actor: ResourceActor, resource_id: str, run_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            payload = await self._evaluations(session, actor).retry(resource_id, run_id)
            await session.commit()
        return payload

    async def create_evaluation_comparison(
        self,
        actor: ResourceActor,
        resource_id: str,
        *,
        left_revision_id: str,
        left_profile_id: str,
        right_revision_id: str,
        right_profile_id: str,
        top_k: int,
        case_ids: list[str] | None,
    ) -> dict[str, Any]:
        """Enqueue two ordinary frozen evaluations under one comparison identity."""
        async with self._session_factory() as session:
            payload = await self._evaluations(session, actor).start_comparison(
                resource_id,
                left_revision_id=left_revision_id,
                left_profile_id=left_profile_id,
                right_revision_id=right_revision_id,
                right_profile_id=right_profile_id,
                top_k=top_k,
                case_ids=case_ids,
            )
            await session.commit()
        await self._audit(
            actor.user_id,
            "knowledge_evaluation_comparison_started",
            "knowledge_base",
            resource_id,
            {"comparison_id": payload["id"]},
        )
        return payload

    async def get_evaluation_comparison(self, actor: ResourceActor, resource_id: str, comparison_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._evaluations(session, actor).get_comparison(resource_id, comparison_id)

    # --- Evaluation policy -------------------------------------------------

    async def get_evaluation_policy(self, actor: ResourceActor, resource_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            return await self._evaluations(session, actor).get_policy(resource_id)

    async def put_evaluation_policy(
        self,
        actor: ResourceActor,
        resource_id: str,
        *,
        profile_id: str,
        top_k: int,
        case_ids: list[str],
        min_expected_hit_rate: float,
        min_recall_at_k: float,
        min_mrr_at_k: float,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            payload = await self._evaluations(session, actor).put_policy(
                resource_id,
                profile_id=profile_id,
                top_k=top_k,
                case_ids=case_ids,
                min_expected_hit_rate=min_expected_hit_rate,
                min_recall_at_k=min_recall_at_k,
                min_mrr_at_k=min_mrr_at_k,
            )
            await session.commit()
        return payload
