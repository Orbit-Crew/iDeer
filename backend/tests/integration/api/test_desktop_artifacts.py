"""Desktop local-result artifact upload contract (issue 105, Server side)."""

import base64
import hashlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from langgraph.store.memory import InMemoryStore

from app.gateway.authz import AuthContext
from deerflow.persistence.thread_meta.memory import MemoryThreadMetaStore

CONTENT = b"T105-UNIQUE-RESULT"
DIGEST = hashlib.sha256(CONTENT).hexdigest()
HANDLE = f"local://{DIGEST}/result-105.txt"
OTHER_DIGEST = hashlib.sha256(b"x" * 65537).hexdigest()


def payload(**overrides):
    body = {
        "version": 1,
        "kind": "local_result",
        "task_id": "task-105",
        "run_id": "run-105",
        "name": "result-105.txt",
        "sha256": DIGEST,
        "bytes": len(CONTENT),
        "content": base64.b64encode(CONTENT).decode("ascii"),
        "handle": HANDLE,
        "grant": {"run_id": "run-105", "task_id": "task-105", "thread_id": "thread-A", "name": "result-105.txt", "token": "grant-token-105"},
    }
    body.update(overrides)
    return body


def build_app(tmp_path, monkeypatch, *, user="owner-A", permissions=("threads:read", "threads:write")):
    """Isolated app: virtual paths resolve into the test tree; one owner."""
    from app.gateway.routers import desktop_artifacts

    def fake_resolve(thread_id, virtual_path, user_id=None):
        # Mirror the real layout: <thread>/user-data/<virtual path>.
        base = tmp_path / str(thread_id) / "user-data" / str(user_id)
        target = base / str(virtual_path).removeprefix("/mnt/user-data/")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(desktop_artifacts, "resolve_thread_virtual_path", fake_resolve)
    app = FastAPI()
    app.include_router(desktop_artifacts.router)
    store = MemoryThreadMetaStore(InMemoryStore())
    app.state.thread_store = store

    @app.middleware("http")
    async def fixture_auth(request, call_next):
        request.state.auth = AuthContext(SimpleNamespace(id=user), permissions=list(permissions))
        return await call_next(request)

    async def seed():
        await store.create("thread-A", user_id="owner-A")
        await store.create("thread-B", user_id="owner-B")

    return app, seed


@pytest.mark.asyncio
async def test_upload_stores_payload_and_replays_the_same_artifact(tmp_path, monkeypatch):
    app, seed = build_app(tmp_path, monkeypatch)
    await seed()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid") as client:
        first = await client.post("/api/threads/thread-A/artifacts", json=payload(), headers={"Idempotency-Key": HANDLE})
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["duplicate"] is False and body["artifact_id"] == f"art-{DIGEST[:12]}"
        assert body["thread_id"] == "thread-A" and body["handle"] == HANDLE
        stored = tmp_path / "thread-A" / "user-data" / "owner-A" / "outputs" / "desktop-artifacts" / f"{DIGEST}-result-105.txt"
        assert stored.read_bytes() == CONTENT
        # The replayed explicit upload with the same handle and digest returns
        # the same artifact and never writes a second payload or record.
        replay = await client.post("/api/threads/thread-A/artifacts", json=payload(), headers={"Idempotency-Key": HANDLE})
        assert replay.status_code == 200, replay.text
        assert replay.json()["duplicate"] is True and replay.json()["artifact_id"] == body["artifact_id"]
        records = list((tmp_path / "thread-A" / "user-data" / "owner-A" / "outputs" / "desktop-artifacts" / ".records").glob("*.json"))
        assert len(records) == 1
        meta = await client.get(f"/api/threads/thread-A/artifacts/{body['artifact_id']}")
        assert meta.status_code == 200
        assert meta.json()["sha256"] == DIGEST and meta.json()["task_id"] == "task-105"


@pytest.mark.asyncio
async def test_rejections_are_fixed_categories_that_never_store(tmp_path, monkeypatch):
    app, seed = build_app(tmp_path, monkeypatch)
    await seed()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid") as client:
        cases = [
            (payload(handle="local://x/y"), {"Idempotency-Key": HANDLE}, 400, "HANDLE_MISMATCH"),
            (payload(), {"Idempotency-Key": "local://other/x"}, 400, "IDEMPOTENCY_KEY_MISMATCH"),
            (payload(version=2), {"Idempotency-Key": HANDLE}, 400, "VERSION_UNSUPPORTED"),
            (payload(kind="other"), {"Idempotency-Key": HANDLE}, 400, "KIND_INVALID"),
            (payload(sha256="z" * 64, handle=f"local://{'z' * 64}/result-105.txt"), {"Idempotency-Key": f"local://{'z' * 64}/result-105.txt"}, 422, None),
            (payload(content=base64.b64encode(b"TAMPERED").decode(), bytes=8), {"Idempotency-Key": HANDLE}, 400, "HASH_MISMATCH"),
            (payload(bytes=len(CONTENT) + 1), {"Idempotency-Key": HANDLE}, 400, "BYTES_MISMATCH"),
            (payload(grant={"run_id": "other", "task_id": "task-105", "thread_id": "thread-A", "name": "result-105.txt", "token": "grant-token-105"}), {"Idempotency-Key": HANDLE}, 400, "GRANT_MISMATCH"),
            (payload(name="../escape.txt", handle=f"local://{DIGEST}/../escape.txt"), {"Idempotency-Key": f"local://{DIGEST}/../escape.txt"}, 400, "NAME_INVALID"),
            (payload(bytes=65537, content=base64.b64encode(b"x" * 65537).decode(), sha256=OTHER_DIGEST, handle=f"local://{OTHER_DIGEST}/result-105.txt"), {"Idempotency-Key": f"local://{OTHER_DIGEST}/result-105.txt"}, 413, "TOO_LARGE"),
        ]
        for body, headers, status, code in cases:
            response = await client.post("/api/threads/thread-A/artifacts", json=body, headers=headers)
            assert response.status_code == status, (status, response.text)
            if code is not None:
                assert response.json()["detail"]["code"] == code, code
        stored = tmp_path / "thread-A" / "user-data" / "owner-A" / "outputs" / "desktop-artifacts"
        assert not any(stored.glob("*-result-105.txt")), "a rejected upload must never store bytes"


@pytest.mark.asyncio
async def test_owner_isolation_and_cross_thread_grant_are_refused(tmp_path, monkeypatch):
    app, seed = build_app(tmp_path, monkeypatch)
    await seed()
    foreign_app, _ = build_app(tmp_path, monkeypatch, user="owner-B")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid") as client, httpx.AsyncClient(transport=httpx.ASGITransport(app=foreign_app), base_url="http://fixture.invalid") as client_b:
        # A different account cannot write thread-A artifacts.
        forbidden = await client_b.post("/api/threads/thread-A/artifacts", json=payload(), headers={"Idempotency-Key": HANDLE})
        # require_existing hides the thread's existence from other accounts.
        assert forbidden.status_code in (403, 404)
        # A grant bound to another thread cannot ride on this thread's upload.
        wrong_thread = payload(grant={"run_id": "run-105", "task_id": "task-105", "thread_id": "thread-B", "name": "result-105.txt", "token": "grant-token-105"})
        response = await client.post("/api/threads/thread-A/artifacts", json=wrong_thread, headers={"Idempotency-Key": HANDLE})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "GRANT_MISMATCH"
