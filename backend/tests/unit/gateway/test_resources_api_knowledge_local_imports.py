"""Local knowledge import registration endpoints follow Resource Governance (#112).

The Desktop registers one explicit local import as a private KnowledgeBase
Revision manifest: platform UUIDs, owner/visibility and the manifest hash are
the governance identity, while original files and the device index never
upload. These tests inject a facade bound to their own engine instead of
patching route module globals, and compute the expected manifest hash
independently from the frozen protocol instead of reading it back.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.agentplatform.rbac_models import UserModel, UserRole
from app.agentplatform.resource_models import Resource
from app.agentplatform.resources.actors import actor_from_user
from app.agentplatform.resources.service import ResourceService
from app.gateway.routers import resources
from deerflow.persistence.base import Base

DEVICE_ID = "device-112"


def independent_manifest_hash(documents: list[dict]) -> str:
    """Recompute the frozen manifest identity from first principles."""

    ordered = sorted(documents, key=lambda entry: str(entry.get("document_id")))
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def local_document(filename: str, content: bytes) -> dict:
    return {"filename": filename, "content_hash": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content), "mime_type": "text/markdown" if filename.endswith(".md") else "text/plain"}


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple]:
    monkeypatch.setattr("app.agentplatform.knowledge.revisions.get_paths", lambda: SimpleNamespace(base_dir=tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'local-imports-api.db'}")
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

    knowledge = KnowledgeFacade(factory, audit=audit, provider_factory=lambda: object())
    yield factory, knowledge, current_user, audit_calls, tmp_path
    await engine.dispose()


async def _seed_kb(factory, user, slug: str, *, resource_type: str = "knowledge_base") -> str:
    async with factory() as session:
        resource = await ResourceService(session, actor_from_user(user)).create_resource(
            resource_type=resource_type,
            slug=slug,
            display_name=slug.capitalize(),
            storage_kind="database" if resource_type == "knowledge_base" else "filesystem",
        )
        await session.commit()
        return resource.id


@pytest.mark.asyncio
async def test_local_import_registers_private_revision_with_governance_identity(env) -> None:
    """T112-01: one explicit import freezes a platform-owned manifest."""
    factory, knowledge, current_user, audit_calls, _ = env
    kb_id = await _seed_kb(factory, current_user, "imports")

    request = resources.LocalImportRequest(
        documents=[local_document("guide.md", b"# marker\nlocal bytes"),
                   local_document("notes.txt", b"plain text")],
        device_id=DEVICE_ID,
    )
    revision = await resources.register_knowledge_local_import(kb_id, request, current_user, knowledge=knowledge)

    assert revision["status"] == "draft"
    assert revision["revision_no"] == 1
    assert revision["resource_id"] == kb_id
    assert revision["document_count"] == 2
    # The manifest hash is the frozen governance identity: recomputed here from
    # the returned documents, never taken from the implementation's own sum.
    assert revision["manifest_hash"] == independent_manifest_hash(revision["documents"])
    origins = {entry["metadata"]["origin"] for entry in revision["documents"]}
    assert origins == {"local_import"}
    assert {entry["metadata"].get("device_id") for entry in revision["documents"]} == {DEVICE_ID}
    assert {entry["filename"] for entry in revision["documents"]} == {"guide.md", "notes.txt"}
    assert {entry["content_hash"] for entry in revision["documents"]} == {
        hashlib.sha256(b"# marker\nlocal bytes").hexdigest(), hashlib.sha256(b"plain text").hexdigest()}
    assert audit_calls[-1][1] == "knowledge_local_import_registered"
    assert audit_calls[-1][3] == revision["id"]
    assert audit_calls[-1][4]["manifest_hash"] == revision["manifest_hash"]

    listed = await resources.list_knowledge_revisions(kb_id, current_user, knowledge=knowledge)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == revision["id"]

    async with factory() as session:
        kb = await session.get(Resource, kb_id)
        assert kb.owner_id == current_user.id
        assert kb.visibility == "private"


@pytest.mark.asyncio
async def test_local_import_endpoints_enforce_governance(env) -> None:
    """T112-02/T112-04: the unified resource entry guards visibility and modify."""
    factory, knowledge, current_user, _, _ = env
    kb_id = await _seed_kb(factory, current_user, "guarded")
    intruder = UserModel(id="intruder", username="intruder@test.com", role=UserRole.USER, department_id="dept-b", disabled=False)

    request = resources.LocalImportRequest(documents=[local_document("guide.md", b"bytes")], device_id=DEVICE_ID)
    revision = await resources.register_knowledge_local_import(kb_id, request, current_user, knowledge=knowledge)

    with pytest.raises(HTTPException) as hidden:
        await resources.list_knowledge_revisions(kb_id, intruder, knowledge=knowledge)
    assert hidden.value.status_code == 404

    with pytest.raises(HTTPException) as forbidden:
        await resources.register_knowledge_local_import(kb_id, request, intruder, knowledge=knowledge)
    assert forbidden.value.status_code in {403, 404}

    with pytest.raises(HTTPException) as scoped:
        await resources.get_knowledge_revision(kb_id, str(revision["id"]), intruder, knowledge=knowledge)
    assert scoped.value.status_code == 404

    agent_id = await _seed_kb(factory, current_user, "agent-thing", resource_type="agent")
    with pytest.raises(HTTPException) as wrong_type:
        await resources.register_knowledge_local_import(agent_id, request, current_user, knowledge=knowledge)
    assert wrong_type.value.status_code == 404


@pytest.mark.asyncio
async def test_local_import_rejects_invalid_manifests_without_registering(env, monkeypatch: pytest.MonkeyPatch) -> None:
    """T112-02: fixed validation categories; a rejected import leaves no revision."""
    factory, knowledge, current_user, _, _ = env
    kb_id = await _seed_kb(factory, current_user, "validated")
    monkeypatch.setattr("app.agentplatform.knowledge.documents._max_document_size", lambda: 16)

    rejections = [
        (resources.LocalImportRequest(documents=[{"filename": "../escape.md", "content_hash": "a" * 64, "size_bytes": 1}]),
         HTTPException, "plain file name"),
        (resources.LocalImportRequest(documents=[{"filename": "back\\slash.md", "content_hash": "a" * 64, "size_bytes": 1}]),
         HTTPException, "plain file name"),
        (resources.LocalImportRequest(documents=[{"filename": "payload.exe", "content_hash": "a" * 64, "size_bytes": 1}]),
         HTTPException, "Unsupported document type"),
        (resources.LocalImportRequest(documents=[{"filename": "big.md", "content_hash": "a" * 64, "size_bytes": 64}]),
         HTTPException, "maximum"),
        (resources.LocalImportRequest(documents=[local_document("one.md", b"x"), local_document("two.md", b"x")]),
         HTTPException, "duplicate"),
    ]
    for request, exception, message_part in rejections:
        with pytest.raises(exception) as rejection:
            await resources.register_knowledge_local_import(kb_id, request, current_user, knowledge=knowledge)
        assert message_part.lower() in str(rejection.value.detail).lower()

    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        resources.LocalImportRequest(documents=[])

    listed = await resources.list_knowledge_revisions(kb_id, current_user, knowledge=knowledge)
    assert listed["total"] == 0


@pytest.mark.asyncio
async def test_reimport_creates_new_revision_and_never_overwrites_frozen_ones(env) -> None:
    """T112-03: a changed original imports as a new revision; R1 stays frozen."""
    factory, knowledge, current_user, _, _ = env
    kb_id = await _seed_kb(factory, current_user, "versions")

    first_request = resources.LocalImportRequest(documents=[local_document("marked.md", b"# marker v1\n")], device_id=DEVICE_ID)
    first = await resources.register_knowledge_local_import(kb_id, first_request, current_user, knowledge=knowledge)

    second_request = resources.LocalImportRequest(documents=[local_document("marked.md", b"# marker v2 CHANGED\n")], device_id=DEVICE_ID)
    second = await resources.register_knowledge_local_import(kb_id, second_request, current_user, knowledge=knowledge)

    assert second["revision_no"] == first["revision_no"] + 1
    assert second["id"] != first["id"]
    assert second["manifest_hash"] != first["manifest_hash"]
    assert second["manifest_hash"] == independent_manifest_hash(second["documents"])

    detail = await resources.get_knowledge_revision(kb_id, str(first["id"]), current_user, knowledge=knowledge)
    # Reading R1 returns R1's own frozen manifest, never R2 content in its place.
    assert detail["documents"] == first["documents"]
    assert detail["manifest_hash"] == first["manifest_hash"]
    assert detail["revision_no"] == 1

    # Identical content re-imports as a new revision with the same manifest identity.
    replay = await resources.register_knowledge_local_import(kb_id, first_request, current_user, knowledge=knowledge)
    assert replay["revision_no"] == 3
    assert replay["manifest_hash"] == first["manifest_hash"]

    # A fresh session (post-restart view) reads the same frozen identities.
    async with factory() as session:
        from sqlalchemy import select

        from app.agentplatform.knowledge.models import KnowledgeRevision
        rows = list((await session.execute(select(KnowledgeRevision).order_by(KnowledgeRevision.revision_no))).scalars())
        assert [row.manifest_hash for row in rows] == [first["manifest_hash"], second["manifest_hash"], replay["manifest_hash"]]


@pytest.mark.asyncio
async def test_local_import_revisions_are_explicitly_not_publishable(env) -> None:
    """T112-03: device-local content cannot be published; the refusal is explicit."""
    factory, knowledge, current_user, _, _ = env
    kb_id = await _seed_kb(factory, current_user, "localonly")
    request = resources.LocalImportRequest(documents=[local_document("marked.md", b"# marker\n")], device_id=DEVICE_ID)
    revision = await resources.register_knowledge_local_import(kb_id, request, current_user, knowledge=knowledge)

    with pytest.raises(HTTPException) as publish:
        await resources.publish_knowledge_revision(kb_id, str(revision["id"]), BackgroundTasks(), current_user, knowledge=knowledge)
    assert publish.value.status_code == 409
    assert "local import" in str(publish.value.detail).lower()

    with pytest.raises(HTTPException) as prepare:
        await resources.prepare_knowledge_revision(kb_id, str(revision["id"]), BackgroundTasks(), current_user, knowledge=knowledge)
    assert prepare.value.status_code == 409

    listed = await resources.list_knowledge_revisions(kb_id, current_user, knowledge=knowledge)
    assert listed["items"][0]["status"] == "draft"
