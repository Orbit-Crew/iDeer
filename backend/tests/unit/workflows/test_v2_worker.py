from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentplatform.workflows.v2.worker import WorkflowWorker


@pytest.mark.asyncio
async def test_worker_renews_lease_while_executing() -> None:
    store = MagicMock()
    task = MagicMock(task_id="task-1")
    store.claim_next_task = AsyncMock(return_value=task)
    store.renew_lease = AsyncMock(return_value=True)
    store.finish_task = AsyncMock(return_value=True)
    started = asyncio.Event()
    release = asyncio.Event()

    async def execute(_task) -> None:
        started.set()
        await release.wait()

    worker = WorkflowWorker(store, execute, worker_id="worker-1", heartbeat_seconds=0.01)
    running = asyncio.create_task(worker.run_once())
    await started.wait()
    await asyncio.sleep(0.02)
    release.set()
    assert await running is True

    store.renew_lease.assert_awaited_with("task-1", "worker-1", lease_seconds=30)
    store.finish_task.assert_awaited_with("task-1", "completed", None, "worker-1")


@pytest.mark.asyncio
async def test_worker_stops_heartbeat_before_finishing_task() -> None:
    store = MagicMock()
    task = MagicMock(task_id="task-1")
    store.claim_next_task = AsyncMock(return_value=task)
    renew_started = asyncio.Event()
    renew_cancelled = asyncio.Event()

    async def renew_lease(*_args, **_kwargs) -> bool:
        renew_started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            renew_cancelled.set()
            raise

    async def finish_task(*_args) -> bool:
        assert renew_cancelled.is_set()
        return True

    store.renew_lease = renew_lease
    store.finish_task = finish_task

    async def execute(_task) -> None:
        await renew_started.wait()

    worker = WorkflowWorker(store, execute, worker_id="worker-1", heartbeat_seconds=0.001)
    assert await worker.run_once() is True
    assert renew_cancelled.is_set()


@pytest.mark.asyncio
async def test_worker_finishes_cancelled_run_as_cancelled() -> None:
    """WorkflowCancelled escaping the graph must land the run in the
    ``cancelled`` terminal state, not ``failed`` (report 02-M2)."""
    from app.agentplatform.workflows.v2.compiler import WorkflowCancelled

    store = MagicMock()
    task = MagicMock(task_id="task-1")
    store.claim_next_task = AsyncMock(return_value=task)
    store.renew_lease = AsyncMock(return_value=True)
    store.finish_task = AsyncMock(return_value=True)

    async def execute(_task) -> None:
        raise WorkflowCancelled("workflow cancelled during node 'task'")

    worker = WorkflowWorker(store, execute, worker_id="worker-1", heartbeat_seconds=0.01)
    assert await worker.run_once() is True
    store.finish_task.assert_awaited_with("task-1", "cancelled", None, "worker-1")


@pytest.mark.asyncio
async def test_worker_aborts_execution_when_lease_is_lost() -> None:
    store = MagicMock()
    task = MagicMock(task_id="task-1")
    store.claim_next_task = AsyncMock(return_value=task)
    store.renew_lease = AsyncMock(return_value=False)
    store.finish_task = AsyncMock(return_value=True)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def execute(_task) -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    worker = WorkflowWorker(store, execute, worker_id="worker-1", heartbeat_seconds=0.01)
    assert await worker.run_once() is True

    assert cancelled.is_set()
    store.finish_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_forever_survives_db_errors_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-OperationalError DB exception in the claim path must not kill the
    worker coroutine: the loop logs, backs off and keeps polling."""
    from app.agentplatform.workflows.v2 import worker as worker_module

    monkeypatch.setattr(worker_module, "ERROR_BACKOFF_BASE_SECONDS", 0.01)
    monkeypatch.setattr(worker_module, "ERROR_BACKOFF_MAX_SECONDS", 0.02)

    store = MagicMock()
    claims = 0

    async def claim_next_task(*_args, **_kwargs):
        nonlocal claims
        claims += 1
        if claims <= 2:
            raise RuntimeError("database connection lost")
        return None

    store.claim_next_task = claim_next_task

    worker = WorkflowWorker(store, AsyncMock(), worker_id="worker-1", heartbeat_seconds=0.01)
    loop = asyncio.create_task(worker.run_forever(poll_seconds=0.01))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if claims >= 3:
            break

    assert claims >= 3, "worker stopped polling after DB exceptions"
    assert not loop.done(), "worker coroutine died on a DB exception"
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop


@pytest.mark.asyncio
async def test_run_forever_propagates_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation must still terminate the loop (process shutdown)."""
    from app.agentplatform.workflows.v2 import worker as worker_module

    monkeypatch.setattr(worker_module, "ERROR_BACKOFF_BASE_SECONDS", 0.01)

    store = MagicMock()

    async def claim_next_task(*_args, **_kwargs):
        await asyncio.sleep(3600)

    store.claim_next_task = claim_next_task

    worker = WorkflowWorker(store, AsyncMock(), worker_id="worker-1", heartbeat_seconds=0.01)
    loop = asyncio.create_task(worker.run_forever(poll_seconds=0.01))
    await asyncio.sleep(0.05)
    assert not loop.done()
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
