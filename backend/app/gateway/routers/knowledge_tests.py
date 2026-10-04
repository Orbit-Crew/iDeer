"""KnowledgeBase retrieval-test, evaluation, and policy endpoints (M6 ticket 01).

Lives outside ``resources.py`` so the eval-case and retrieval-test verticals
stay independent; every handler resolves the request into an actor plus an
intent and delegates to the shared :class:`KnowledgeFacade` seam, so
visibility, error classification, commit, and audit semantics cannot drift.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.rbac_models import UserModel
from app.agentplatform.resources.actors import actor_from_user
from app.gateway.authz import get_current_rbac_user
from app.gateway.knowledge_seam import knowledge_facade, translate_resource_errors

router = APIRouter(prefix="/api/resources", tags=["knowledge-tests"])


class RetrievalTestCreateRequest(BaseModel):
    """Only the parameters the shared retrieval path supports; anything else
    is an explicit 422 instead of a silently applied default."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1, max_length=36)
    profile_id: Literal["frozen", "configured"] = "frozen"
    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=20)


class EvaluationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1, max_length=36)
    profile_id: Literal["frozen", "configured"] = "frozen"
    top_k: int = Field(default=8, ge=1, le=20)
    case_ids: list[str] | None = Field(default=None, max_length=1000)


class EvaluationComparisonCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_revision_id: str = Field(min_length=1, max_length=36)
    left_profile_id: Literal["frozen", "configured"] = "frozen"
    right_revision_id: str = Field(min_length=1, max_length=36)
    right_profile_id: Literal["frozen", "configured"] = "configured"
    top_k: int = Field(default=8, ge=1, le=20)
    case_ids: list[str] | None = Field(default=None, max_length=1000)


class EvaluationPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: Literal["frozen", "configured"] = "frozen"
    top_k: int = Field(ge=1, le=20)
    case_ids: list[str] = Field(min_length=1, max_length=1000)
    min_expected_hit_rate: float = Field(ge=0, le=1)
    min_recall_at_k: float = Field(ge=0, le=1)
    min_mrr_at_k: float = Field(ge=0, le=1)


@router.get("/{resource_id}/evaluation-policy")
@translate_resource_errors
async def get_evaluation_policy(
    resource_id: str,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.get_evaluation_policy(actor_from_user(current_user), resource_id)


@router.put("/{resource_id}/evaluation-policy")
@translate_resource_errors
async def put_evaluation_policy(
    resource_id: str,
    body: EvaluationPolicyRequest,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.put_evaluation_policy(
        actor_from_user(current_user),
        resource_id,
        profile_id=body.profile_id,
        top_k=body.top_k,
        case_ids=body.case_ids,
        min_expected_hit_rate=body.min_expected_hit_rate,
        min_recall_at_k=body.min_recall_at_k,
        min_mrr_at_k=body.min_mrr_at_k,
    )


@router.post("/{resource_id}/retrieval-tests", status_code=201)
@translate_resource_errors
async def create_retrieval_test(
    resource_id: str,
    body: RetrievalTestCreateRequest,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    """Run and archive a bounded retrieval test."""
    return await knowledge.create_retrieval_test(
        actor_from_user(current_user),
        resource_id,
        revision_id=body.revision_id,
        query=body.query,
        top_k=body.top_k,
        profile_id=body.profile_id,
    )


@router.get("/{resource_id}/retrieval-tests")
@translate_resource_errors
async def list_retrieval_tests(
    resource_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    """List archived retrieval tests for a visible knowledge base."""
    return await knowledge.list_retrieval_tests(actor_from_user(current_user), resource_id, offset=offset, limit=limit)


@router.get("/{resource_id}/retrieval-tests/{test_id}")
@translate_resource_errors
async def get_retrieval_test(
    resource_id: str,
    test_id: str,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    """Read one archived retrieval test after rechecking access."""
    return await knowledge.get_retrieval_test(actor_from_user(current_user), resource_id, test_id)


@router.post("/{resource_id}/evaluations", status_code=202)
@translate_resource_errors
async def create_evaluation(
    resource_id: str,
    body: EvaluationCreateRequest,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    """Freeze and enqueue one bounded profile evaluation."""
    return await knowledge.create_evaluation(
        actor_from_user(current_user),
        resource_id,
        revision_id=body.revision_id,
        profile_id=body.profile_id,
        top_k=body.top_k,
        case_ids=body.case_ids,
    )


@router.get("/{resource_id}/evaluations")
@translate_resource_errors
async def list_evaluations(
    resource_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.list_evaluations(actor_from_user(current_user), resource_id, offset=offset, limit=limit)


@router.get("/{resource_id}/evaluations/{run_id}")
@translate_resource_errors
async def get_evaluation(
    resource_id: str,
    run_id: str,
    result_offset: int = Query(default=0, ge=0),
    result_limit: int = Query(default=20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.get_evaluation(
        actor_from_user(current_user),
        resource_id,
        run_id,
        result_offset=result_offset,
        result_limit=result_limit,
    )


@router.post("/{resource_id}/evaluations/{run_id}/retry", status_code=202)
@translate_resource_errors
async def retry_evaluation(
    resource_id: str,
    run_id: str,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.retry_evaluation(actor_from_user(current_user), resource_id, run_id)


@router.post("/{resource_id}/evaluation-comparisons", status_code=202)
@translate_resource_errors
async def create_evaluation_comparison(
    resource_id: str,
    body: EvaluationComparisonCreateRequest,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.create_evaluation_comparison(
        actor_from_user(current_user),
        resource_id,
        left_revision_id=body.left_revision_id,
        left_profile_id=body.left_profile_id,
        right_revision_id=body.right_revision_id,
        right_profile_id=body.right_profile_id,
        top_k=body.top_k,
        case_ids=body.case_ids,
    )


@router.get("/{resource_id}/evaluation-comparisons/{comparison_id}")
@translate_resource_errors
async def get_evaluation_comparison(
    resource_id: str,
    comparison_id: str,
    current_user: UserModel = Depends(get_current_rbac_user),
    knowledge: KnowledgeFacade = Depends(knowledge_facade),
) -> dict[str, Any]:
    return await knowledge.get_evaluation_comparison(actor_from_user(current_user), resource_id, comparison_id)
