from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway import deps
from app.gateway.authz import AuthContext
from app.gateway.routers import scheduled_tasks
from deerflow.persistence.scheduled_task_runs.model import ScheduledTaskRunRow
from deerflow.persistence.scheduled_tasks import ScheduledTaskRepository
from deerflow.persistence.scheduled_tasks.model import ScheduledTaskRow


@pytest_asyncio.fixture
async def thread_tasks(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(ScheduledTaskRow.__table__.create)
            await connection.run_sync(ScheduledTaskRunRow.__table__.create)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        async with sf() as session:
            for task_id, owner, thread_id in [
                ("fresh", "user-1", None),
                ("reuse", "user-1", "thread-history"),
                ("foreign", "user-2", None),
                ("unrelated", "user-1", "thread-other"),
            ]:
                session.add(ScheduledTaskRow(id=task_id, user_id=owner, thread_id=thread_id, title=task_id, prompt="Example", schedule_type="cron", schedule_spec={"cron": "0 9 * * *"}, timezone="UTC"))
            for record_id, task_id, thread_id in [
                ("old-fresh", "fresh", "thread-history"),
                ("new-fresh", "fresh", "thread-new"),
                ("reuse-a", "reuse", "thread-history"),
                ("reuse-b", "reuse", "thread-history"),
                ("foreign-run", "foreign", "thread-history"),
            ]:
                session.add(ScheduledTaskRunRow(id=record_id, task_id=task_id, thread_id=thread_id, run_id=f"run-{record_id}", scheduled_for=datetime.now(UTC), trigger="scheduled", status="success"))
            await session.commit()
        monkeypatch.setattr(scheduled_tasks, "get_scheduled_task_repo", lambda request: ScheduledTaskRepository(sf))
        monkeypatch.setattr(scheduled_tasks, "get_optional_user_from_request", AsyncMock(return_value=SimpleNamespace(id="user-1")))
        store = SimpleNamespace(check_access=AsyncMock(return_value=True))
        monkeypatch.setattr(deps, "get_thread_store", lambda request: store)
        app = FastAPI()
        app.include_router(scheduled_tasks.router)

        @app.middleware("http")
        async def authenticate(request, call_next):
            mode = request.headers.get("x-test-auth")
            user = None if mode == "anonymous" else SimpleNamespace(id="user-1")
            request.state.auth = AuthContext(user=user, permissions=[] if mode == "denied" else ["threads:read"])
            return await call_next(request)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, store
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_thread_tasks_include_historical_generated_threads_without_duplicates_or_foreign_tasks(thread_tasks):
    client, _store = thread_tasks
    response = await client.get("/api/threads/thread-history/scheduled-tasks")
    assert response.status_code == 200
    assert sorted(task["id"] for task in response.json()) == ["fresh", "reuse"]
    assert [task["id"] for task in (await client.get("/api/threads/thread-new/scheduled-tasks")).json()] == ["fresh"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "status"), [("anonymous", 401), ("denied", 403)])
async def test_thread_task_lookup_requires_existing_read_permission(thread_tasks, mode, status):
    client, _store = thread_tasks
    response = await client.get("/api/threads/thread-history/scheduled-tasks", headers={"x-test-auth": mode})
    assert response.status_code == status


@pytest.mark.asyncio
async def test_thread_task_lookup_preserves_thread_ownership_check(thread_tasks):
    client, store = thread_tasks
    store.check_access.return_value = False
    response = await client.get("/api/threads/thread-history/scheduled-tasks")
    assert response.status_code == 404
