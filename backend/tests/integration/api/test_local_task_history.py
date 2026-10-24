"""Thread task history HTTP contract, pagination, and owner isolation."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.device_control.broker import DeviceBroker
from app.device_control.receipt_archive import ReceiptArchive
from app.device_control.receipt_models import DeviceTaskReceiptModel
from app.gateway.authz import AuthContext
from deerflow.persistence.thread_meta.memory import MemoryThreadMetaStore


@pytest.mark.asyncio
async def test_owned_thread_history_is_bounded_sanitized_and_never_dispatches(tmp_path, monkeypatch):
    from app.gateway.routers import local_tasks

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'history.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(DeviceTaskReceiptModel.__table__.create)
    archive = ReceiptArchive(async_sessionmaker(engine, expire_on_commit=False))
    binding = {"user_id": "owner-A", "device_id": "device-A", "server_origin": "https://fixture.invalid", "device_public_key": "secret-binding", "broker_public_key": "secret-broker"}
    for index in range(3):
        await archive.admit(
            binding,
            {
                "task_id": f"task-{index}",
                "run_id": f"run-{index}",
                "tool_call_id": f"call-{index}",
                "capability": "local.files.write",
                "logical_target": "/workspace/12345678-1234-4234-8234-123456789abc/report.txt",
                "task_signature": "secret-signature",
            },
            thread_id="thread-A",
        )
    broker = DeviceBroker(receipt_archive=archive)
    monkeypatch.setattr(local_tasks, "get_device_broker", lambda: broker)
    app = FastAPI()
    app.include_router(local_tasks.router)
    app.state.thread_store = MemoryThreadMetaStore(InMemoryStore())
    await app.state.thread_store.create("thread-A", user_id="owner-A")
    await app.state.thread_store.create("thread-B", user_id="owner-B")

    @app.middleware("http")
    async def fixture_auth(request, call_next):
        owner = request.headers.get("x-fixture-user", "owner-A")
        permissions = [] if owner == "no-permission" else ["threads:read"]
        request.state.auth = AuthContext(SimpleNamespace(id=owner), permissions=permissions)
        return await call_next(request)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid") as client:
        response = await client.get("/api/threads/thread-A/local-tasks?limit=2&offset=0")
        assert response.status_code == 200
        page = response.json()
        assert [task["task_id"] for task in page["tasks"]] == ["task-0", "task-1"]
        assert page["has_more"] is True and page["next_offset"] == 2
        assert all(task["status"] == "result_not_verified" for task in page["tasks"])
        assert "secret-" not in response.text
        assert "task_signature" not in response.text
        last = (await client.get("/api/threads/thread-A/local-tasks?limit=2&offset=2")).json()
        assert [task["task_id"] for task in last["tasks"]] == ["task-2"]
        assert last["has_more"] is False and last["next_offset"] is None
        assert (await client.get("/api/threads/thread-A/local-tasks", headers={"x-fixture-user": "owner-B"})).status_code == 404
        assert (await client.get("/api/threads/thread-B/local-tasks")).status_code == 404
        assert (await client.get("/api/threads/missing/local-tasks")).status_code == 404
        assert (await client.get("/api/threads/thread-A/local-tasks?limit=101")).status_code == 422
        assert (await client.get("/api/threads/thread-A/local-tasks", headers={"x-fixture-user": "no-permission"})).status_code == 403
    assert broker.tasks == {}
    await engine.dispose()
