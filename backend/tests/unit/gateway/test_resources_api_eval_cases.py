"""Eval case endpoints follow Resource Governance and the canonical API (M6 ticket 03).

The document and eval-case endpoints are thin: they resolve the request into
an actor plus an intent and delegate to the injected :class:`KnowledgeFacade`
seam, which owns service construction, commits, and audit. These tests inject
a facade bound to their own engine instead of patching route module globals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.agentplatform.audit_model  # noqa: F401 - register audit_logs
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
import app.agentplatform.resource_models  # noqa: F401 - register resource tables
import app.agentplatform.visibility_models  # noqa: F401 - register visibility tables
from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.knowledge.models import KnowledgeDocument
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resources.actors import actor_from_user
from app.agentplatform.resources.service import ResourceService
from app.gateway.routers import resources
from deerflow.persistence.base import Base


@pytest_asyncio.fixture
async def env(tmp_path) -> AsyncIterator[tuple]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'eval-cases-api.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    current_user = UserModel(
        id="owner",
        username="owner@test.com",
        role=UserRole.USER,
        department_id="dept-a",
        disabled=False,
    )
    async with factory() as session:
        session.add(current_user)
        await session.commit()
    audit_calls: list[tuple] = []

    async def audit(actor_id, action, resource_type=None, resource_id=None, detail=None, ip_address=None) -> None:
        audit_calls.append((actor_id, action, resource_type, resource_id, detail))

    knowledge = KnowledgeFacade(factory, audit=audit)
    yield factory, knowledge, current_user, audit_calls
    await engine.dispose()


async def _seed_kb(factory, user, slug: str = "eval-api") -> str:
    async with factory() as session:
        resource = await ResourceService(session, actor_from_user(user)).create_resource(
            resource_type="knowledge_base",
            slug=slug,
            display_name=slug,
            storage_kind="database",
        )
        await session.commit()
        return resource.id


async def _seed_document(factory, kb_id: str, owner_id: str, filename: str = "guide.txt") -> KnowledgeDocument:
    async with factory() as session:
        row = KnowledgeDocument(
            id=str(uuid.uuid4()),
            resource_id=kb_id,
            original_filename=filename,
            size_bytes=8,
            mime_type="text/plain",
            content_hash="0" * 64,
            storage_key=f"knowledge-documents/{kb_id}/{uuid.uuid4()}-{filename}",
            metadata_json={},
            status="ready",
            created_by=owner_id,
        )
        session.add(row)
        await session.commit()
        return row


def _create_request(question: str = "What is the retry policy?", document_ids: list[str] | None = None, tags: list[str] | None = None) -> resources.EvalCaseCreateRequest:
    return resources.EvalCaseCreateRequest(
        question=question,
        expected_document_ids=document_ids or [],
        tags=tags or [],
    )


@pytest.mark.asyncio
async def test_eval_case_crud_endpoints_with_audit(env) -> None:
    factory, knowledge, current_user, audit_calls = env
    kb_id = await _seed_kb(factory, current_user)
    document = await _seed_document(factory, kb_id, current_user.id)

    created = await resources.create_eval_case(kb_id, _create_request(document_ids=[document.id], tags=["regression"]), current_user, knowledge=knowledge)
    assert created["resource_id"] == kb_id
    assert created["expected_document_ids"] == [document.id]
    assert created["version_no"] == 1
    assert audit_calls[-1][1] == "eval_case_created"
    assert audit_calls[-1][3] == created["id"]
    # Case content stays in controlled storage; the audit trail records
    # identity and hash only, never the question text.
    assert "question" not in (audit_calls[-1][4] or {})

    listed = await resources.list_eval_cases(kb_id, current_user, knowledge=knowledge)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]

    detail = await resources.get_eval_case(kb_id, str(created["id"]), current_user, knowledge=knowledge)
    assert detail["versions"][0]["change_type"] == "created"

    updated = await resources.update_eval_case(
        kb_id,
        str(created["id"]),
        resources.EvalCaseUpdateRequest(tags=["regression", "smoke"]),
        current_user,
        knowledge=knowledge,
    )
    assert updated["version_no"] == 2
    assert updated["tags"] == ["regression", "smoke"]
    assert audit_calls[-1][1] == "eval_case_updated"

    await resources.delete_eval_case(kb_id, str(created["id"]), current_user, knowledge=knowledge)
    assert audit_calls[-1][1] == "eval_case_deleted"
    listed = await resources.list_eval_cases(kb_id, current_user, knowledge=knowledge)
    assert listed["total"] == 0


@pytest.mark.asyncio
async def test_eval_case_endpoint_reports_revision_applicability(env) -> None:
    factory, knowledge, current_user, _ = env
    from app.agentplatform.knowledge.models import KnowledgeRevision

    kb_id = await _seed_kb(factory, current_user)
    document = await _seed_document(factory, kb_id, current_user.id)
    async with factory() as session:
        revision_id = str(uuid.uuid4())
        session.add(
            KnowledgeRevision(
                id=revision_id,
                knowledge_base_id=kb_id,
                revision_no=1,
                status="published",
                manifest_hash="a" * 64,
                manifest_json=[{"document_id": document.id}],
                provider_doc_map_json={},
                document_count=1,
                created_by=current_user.id,
            )
        )
        await session.commit()

    created = await resources.create_eval_case(kb_id, _create_request(document_ids=[document.id]), current_user, knowledge=knowledge)
    report = await resources.get_eval_case_revision_applicability(kb_id, revision_id, current_user, knowledge=knowledge)
    assert report["revision_id"] == revision_id
    assert report["items"][0]["case_id"] == created["id"]
    assert report["items"][0]["applicable"] is True

    with pytest.raises(HTTPException) as missing_revision:
        await resources.get_eval_case_revision_applicability(kb_id, str(uuid.uuid4()), current_user, knowledge=knowledge)
    assert missing_revision.value.status_code == 404


@pytest.mark.asyncio
async def test_eval_case_endpoints_enforce_governance_and_validation(env) -> None:
    factory, knowledge, current_user, _ = env
    kb_id = await _seed_kb(factory, current_user)
    document = await _seed_document(factory, kb_id, current_user.id)
    created = await resources.create_eval_case(kb_id, _create_request(document_ids=[document.id]), current_user, knowledge=knowledge)

    with pytest.raises(HTTPException) as empty_question:
        await resources.create_eval_case(kb_id, _create_request(question="   ", document_ids=[document.id]), current_user, knowledge=knowledge)
    assert empty_question.value.status_code == 400

    with pytest.raises(HTTPException) as empty_expected:
        await resources.create_eval_case(kb_id, _create_request(), current_user, knowledge=knowledge)
    assert empty_expected.value.status_code == 400

    with pytest.raises(HTTPException) as unknown_document:
        await resources.create_eval_case(kb_id, _create_request(document_ids=[str(uuid.uuid4())]), current_user, knowledge=knowledge)
    assert unknown_document.value.status_code == 400

    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)
    with pytest.raises(HTTPException) as hidden:
        await resources.list_eval_cases(kb_id, intruder, knowledge=knowledge)
    assert hidden.value.status_code == 404

    with pytest.raises(HTTPException) as forbidden:
        await resources.create_eval_case(kb_id, _create_request(document_ids=[document.id]), intruder, knowledge=knowledge)
    assert forbidden.value.status_code in {403, 404}

    with pytest.raises(HTTPException) as guessed:
        await resources.get_eval_case(kb_id, str(created["id"]), UserModel(id="reader", username="reader@test.com", role=UserRole.VIEWER, department_id="dept-b", disabled=False), knowledge=knowledge)
    assert guessed.value.status_code == 404

    with pytest.raises(HTTPException) as scoped:
        await resources.get_eval_case(str(uuid.uuid4()), str(created["id"]), current_user, knowledge=knowledge)
    assert scoped.value.status_code == 404


def test_document_upload_route_serves_through_the_injected_seam(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FastAPI resolves the seam dependency and the route serves end to end.

    The direct-call tests above cover handler-to-facade delegation; this one
    proves the production injection wiring (``Depends(_knowledge_facade)``)
    resolves and dispatches a real request. The facade is swapped through
    FastAPI's dependency-overrides seam, not by patching module globals.
    """
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.agentplatform.knowledge.documents  # noqa: F401 - patch target
    from app.gateway.authz import get_current_rbac_user
    from app.gateway.routers.resources import _knowledge_facade
    from app.gateway.routers.resources import router as resources_router

    async def _prepare() -> tuple:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seam-http.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        owner = UserModel(id="owner", username="owner@test.com", role=UserRole.USER, department_id="dept-a", disabled=False)
        async with factory() as session:
            session.add(owner)
            await session.commit()
            kb_id = (await ResourceService(session, actor_from_user(owner)).create_resource(resource_type="knowledge_base", slug="seam-http", display_name="Seam HTTP", storage_kind="database")).id
            await session.commit()
        await engine.dispose()
        return factory, kb_id

    factory, kb_id = asyncio.run(_prepare())
    monkeypatch.setattr("app.agentplatform.knowledge.documents.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))

    audit_calls: list[tuple] = []

    async def audit(actor_id, action, resource_type=None, resource_id=None, detail=None, ip_address=None) -> None:
        audit_calls.append((actor_id, action, resource_type, resource_id, detail))

    app = FastAPI()
    app.include_router(resources_router)
    app.dependency_overrides[get_current_rbac_user] = lambda: UserModel(id="owner", username="owner@test.com", role=UserRole.USER, department_id="dept-a", disabled=False)
    app.dependency_overrides[_knowledge_facade] = lambda: KnowledgeFacade(factory, audit=audit)

    with TestClient(app) as client:
        response = client.post(f"/api/resources/{kb_id}/documents", files={"file": ("guide.txt", b"hello knowledge", "text/plain")})

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "guide.txt"
    assert audit_calls == [
        (
            "owner",
            "knowledge_document_uploaded",
            "knowledge_document",
            payload["id"],
            {"resource_id": kb_id, "content_hash": payload["content_hash"], "size": 15},
        )
    ]
