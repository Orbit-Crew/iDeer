"""HTTP-side companion of the knowledge seam.

The knowledge domain raises domain errors; this module owns the one
domain-error to HTTP-status mapping shared by the ``/api/resources`` routers,
the session-factory resolution both routers need, and the FastAPI dependency
that produces the gateway's :class:`KnowledgeFacade`. Routes stay free of
error-translation copies and never import each other's private helpers.
"""

from __future__ import annotations

from functools import wraps

from fastapi import HTTPException

from app.agentplatform.knowledge.evaluation import KnowledgeEvaluationValidationError
from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.provider import KnowledgeProviderUnavailable
from app.agentplatform.knowledge.retrieval_test import (
    KnowledgeRetrievalTestValidationError,
    RetrievalTestStorageUnavailable,
    RetrievalTestUnavailable,
)
from app.agentplatform.resource_runtime import StorageConflict, StorageValidationError
from app.agentplatform.resource_service import (
    ResourceApprovalRequired,
    ResourceConflict,
    ResourceNotFound,
    ResourcePermissionDenied,
    VisibilityClosureError,
)
from app.agentplatform.workflow_runtime import WorkflowRunError
from app.gateway.audit import record_audit
from deerflow.persistence.engine import get_session_factory


def persistence_factory():
    """Resolve the gateway session factory; persistence absence is a 503."""
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(503, "Resource persistence is unavailable")
    return session_factory


def knowledge_facade() -> KnowledgeFacade:
    """Wire the knowledge-domain seam with this gateway's session factory and audit sink."""
    return KnowledgeFacade(persistence_factory(), audit=record_audit)


def translate_resource_errors(handler):
    """The single knowledge/resource domain-error to HTTP-status mapping."""

    @wraps(handler)
    async def wrapped(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except ResourceNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ResourcePermissionDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        except VisibilityClosureError as exc:
            raise HTTPException(
                409,
                detail={
                    "code": "visibility_closure_violation",
                    "message": str(exc),
                    "violations": exc.violations,
                },
            ) from exc
        except (ResourceConflict, ResourceApprovalRequired, StorageConflict) as exc:
            raise HTTPException(409, str(exc)) from exc
        except KnowledgeProviderUnavailable as exc:
            # Environment readiness, not a client mistake: align with the admin
            # reconciliation endpoint's 503 semantics.
            raise HTTPException(503, str(exc)) from exc
        except RetrievalTestUnavailable as exc:
            raise HTTPException(status_code=503, detail={"code": "retrieval_test_unavailable", "message": str(exc)}) from exc
        except RetrievalTestStorageUnavailable as exc:
            raise HTTPException(status_code=503, detail={"code": "retrieval_test_storage_unavailable", "message": str(exc)}) from exc
        except KnowledgeRetrievalTestValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_retrieval_test", "message": str(exc)}) from exc
        except KnowledgeEvaluationValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_evaluation", "message": str(exc)}) from exc
        except WorkflowRunError as exc:
            raise HTTPException(400, detail=exc.api_detail()) from exc
        except (StorageValidationError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    return wrapped
