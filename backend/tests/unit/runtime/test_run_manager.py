"""Tests for RunManager."""

import asyncio
import itertools
import logging
import re
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import DatabaseError as SQLAlchemyDatabaseError

from deerflow.config.run_ownership_config import RunOwnershipConfig
from deerflow.runtime import DisconnectMode, RunManager, RunStatus, ThreadOperationKind
from deerflow.runtime.events.store.memory import MemoryRunEventStore
from deerflow.runtime.runs.manager import CancelOutcome, ConflictError, PersistenceRetryPolicy, RunRecord, RunStartOutcome, UnsupportedStrategyError, _is_retryable_persistence_error
from deerflow.runtime.runs.store.memory import MemoryRunStore

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


@pytest.fixture
def manager() -> RunManager:
    return RunManager()


class FlakyStatusRunStore(MemoryRunStore):
    """Memory run store that simulates transient SQLite status-write failures."""

    def __init__(self, *, status_failures: int) -> None:
        super().__init__()
        self.status_failures = status_failures
        self.status_update_attempts = 0

    async def update_status(self, run_id, status, *, error=None, stop_reason=None):
        self.status_update_attempts += 1
        if self.status_failures > 0:
            self.status_failures -= 1
            raise sqlite3.OperationalError("database is locked")
        return await super().update_status(run_id, status, error=error, stop_reason=stop_reason)


class MissingRowStatusRunStore(MemoryRunStore):
    """Memory run store that reports a missing row for status updates."""

    async def update_status(self, run_id, status, *, error=None, stop_reason=None):
        await super().update_status(run_id, status, error=error, stop_reason=stop_reason)
        return False


class PermanentStatusRunStore(MemoryRunStore):
    """Memory run store that simulates a permanent SQLAlchemy write failure."""

    def __init__(self) -> None:
        super().__init__()
        self.status_update_attempts = 0

    async def update_status(self, run_id, status, *, error=None, stop_reason=None):
        self.status_update_attempts += 1
        raise SQLAlchemyDatabaseError(
            "UPDATE runs SET status = :status WHERE run_id = :run_id",
            {"status": status, "run_id": run_id},
            sqlite3.DatabaseError("no such table: runs"),
        )


class FailingTakeoverRunStore(MemoryRunStore):
    """Memory run store that always fails takeover claims."""

    def __init__(self) -> None:
        super().__init__()
        self.takeover_attempts = 0

    async def claim_for_takeover(self, run_id, *, grace_seconds, error, stop_reason=None):
        self.takeover_attempts += 1
        raise sqlite3.OperationalError("database is locked")


class MissingCompletionRunStore(MemoryRunStore):
    """Memory run store that reports one missing row for completion updates."""

    def __init__(self) -> None:
        super().__init__()
        self.completion_update_attempts = 0

    async def update_run_completion(self, run_id, *, status, **kwargs):
        self.completion_update_attempts += 1
        if self.completion_update_attempts == 1:
            return False
        return await super().update_run_completion(run_id, status=status, **kwargs)


class AlwaysMissingCompletionRunStore(MemoryRunStore):
    """Memory run store that keeps reporting missing rows for completion updates."""

    def __init__(self) -> None:
        super().__init__()
        self.completion_update_attempts = 0

    async def update_run_completion(self, run_id, *, status, **kwargs):
        self.completion_update_attempts += 1
        return False


class FailingDeleteRunStore(MemoryRunStore):
    """Run store that cannot release a persisted thread-operation row."""

    async def delete(self, run_id, *, user_id=None):
        raise RuntimeError("delete failed")


class LostLeaseRunStore(MemoryRunStore):
    """Run store that reports a reservation was taken over."""

    async def update_lease(self, run_id, *, owner_worker_id, lease_expires_at):
        return False


class PausedLostLeaseRunStore(MemoryRunStore):
    """Run store whose failed renewal can be released after reservation cleanup."""

    def __init__(self) -> None:
        super().__init__()
        self.renewal_started = asyncio.Event()
        self.finish_renewal = asyncio.Event()

    async def update_lease(self, run_id, *, owner_worker_id, lease_expires_at):
        self.renewal_started.set()
        await self.finish_renewal.wait()
        return False


async def _stored_statuses(store: MemoryRunStore, *run_ids: str) -> dict[str, Any]:
    rows = {}
    for run_id in run_ids:
        row = await store.get(run_id)
        rows[run_id] = row["status"] if row else None
    return rows


@pytest.mark.anyio
async def test_reservation_delete_failure_preserves_body_error_and_clears_local_record(caplog):
    store = FailingDeleteRunStore()
    manager = RunManager(
        store=store,
        persistence_retry_policy=PersistenceRetryPolicy(max_attempts=1, initial_delay=0),
    )

    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="body failed"):
        async with manager.reserve_thread_operation(
            "thread-1",
            kind=ThreadOperationKind.checkpoint_write,
        ):
            raise ValueError("body failed")

    assert not await manager.has_inflight("thread-1")
    assert manager._runs == {}
    assert manager._runs_by_thread == {}
    assert len(await store.list_inflight()) == 1
    assert "leaving it for orphan reconciliation" in caplog.text


@pytest.mark.anyio
async def test_reservation_lease_loss_surfaces_as_conflict_after_cancelling_body():
    store = LostLeaseRunStore()
    manager = RunManager(
        store=store,
        run_ownership_config=RunOwnershipConfig(
            lease_seconds=30,
            grace_seconds=10,
            heartbeat_enabled=True,
        ),
    )
    entered = asyncio.Event()

    async def hold_reservation() -> None:
        async with manager.reserve_thread_operation(
            "thread-1",
            kind=ThreadOperationKind.checkpoint_write,
        ):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(hold_reservation())
    await entered.wait()

    await manager._renew_leases()

    with pytest.raises(ConflictError, match="reservation lease was lost"):
        await task
    assert not await manager.has_inflight("thread-1")
    assert await store.list_inflight() == []


@pytest.mark.anyio
async def test_reservation_cancelled_while_attaching_task_is_released(monkeypatch):
    store = MemoryRunStore()
    manager = RunManager(store=store)
    admitted = asyncio.Event()
    return_from_admission = asyncio.Event()
    original_admit = manager._admit_thread_operation

    async def pause_after_admission(*args, **kwargs):
        record = await original_admit(*args, **kwargs)
        admitted.set()
        await return_from_admission.wait()
        return record

    monkeypatch.setattr(manager, "_admit_thread_operation", pause_after_admission)

    async def reserve() -> None:
        async with manager.reserve_thread_operation(
            "thread-1",
            kind=ThreadOperationKind.checkpoint_write,
        ):
            raise AssertionError("cancelled reservation must not enter its body")

    task = asyncio.create_task(reserve())
    await admitted.wait()
    await manager._lock.acquire()
    return_from_admission.set()
    await asyncio.sleep(0)
    task.cancel()
    manager._lock.release()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert not await manager.has_inflight("thread-1")
    assert manager._runs == {}
    assert manager._runs_by_thread == {}
    assert await store.list_inflight() == []


@pytest.mark.anyio
async def test_late_failed_renewal_does_not_cancel_released_reservation():
    store = PausedLostLeaseRunStore()
    manager = RunManager(
        store=store,
        run_ownership_config=RunOwnershipConfig(
            lease_seconds=30,
            grace_seconds=10,
            heartbeat_enabled=True,
        ),
    )
    entered = asyncio.Event()
    leave_body = asyncio.Event()
    context_exited = asyncio.Event()
    finish_request = asyncio.Event()

    async def request() -> None:
        async with manager.reserve_thread_operation(
            "thread-1",
            kind=ThreadOperationKind.checkpoint_write,
        ):
            entered.set()
            await leave_body.wait()
        context_exited.set()
        await finish_request.wait()

    request_task = asyncio.create_task(request())
    await entered.wait()
    renewal_task = asyncio.create_task(manager._renew_leases())
    await store.renewal_started.wait()

    leave_body.set()
    await context_exited.wait()
    assert not await manager.has_inflight("thread-1")

    store.finish_renewal.set()
    await renewal_task
    assert not request_task.done()

    finish_request.set()
    await request_task


@pytest.mark.anyio
async def test_create_and_get(manager: RunManager):
    """Created run should be retrievable with new fields."""
    record = await manager.create(
        "thread-1",
        "lead_agent",
        metadata={"key": "val"},
        kwargs={"input": {}},
        multitask_strategy="reject",
    )
    assert record.status == RunStatus.pending
    assert record.thread_id == "thread-1"
    assert record.assistant_id == "lead_agent"
    assert record.metadata == {"key": "val"}
    assert record.kwargs == {"input": {}}
    assert record.multitask_strategy == "reject"
    assert ISO_RE.match(record.created_at)
    assert ISO_RE.match(record.updated_at)

    fetched = await manager.get(record.run_id)
    assert fetched is record


@pytest.mark.anyio
async def test_status_transitions(manager: RunManager):
    """Status should transition pending -> running -> success."""
    record = await manager.create("thread-1")
    assert record.status == RunStatus.pending

    await manager.set_status(record.run_id, RunStatus.running)
    assert record.status == RunStatus.running
    assert ISO_RE.match(record.updated_at)

    await manager.set_status(record.run_id, RunStatus.success)
    assert record.status == RunStatus.success


@pytest.mark.anyio
async def test_cancel(manager: RunManager):
    """Cancel should set abort_event and transition to interrupted."""
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    cancelled = await manager.cancel(record.run_id)
    assert cancelled == CancelOutcome.cancelled
    assert record.abort_event.is_set()
    assert record.status == RunStatus.interrupted


@pytest.mark.anyio
async def test_cancel_persists_interrupted_status_to_store():
    """Cancel should persist interrupted status to the backing store."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    cancelled = await manager.cancel(record.run_id)

    stored = await store.get(record.run_id)
    assert cancelled == CancelOutcome.cancelled
    assert stored is not None
    assert stored["status"] == "interrupted"


@pytest.mark.anyio
async def test_status_persistence_retries_transient_sqlite_lock():
    """Transient SQLite lock errors should not leave a final status stale."""
    store = FlakyStatusRunStore(status_failures=2)
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    await manager.set_status(record.run_id, RunStatus.success)

    stored = await store.get(record.run_id)
    assert stored is not None
    assert stored["status"] == "success"
    assert store.status_update_attempts >= 4


@pytest.mark.anyio
async def test_status_persistence_recreates_missing_store_row():
    """A final status update should recreate a run row if initial persistence was lost."""
    store = MissingRowStatusRunStore()
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await store.delete(record.run_id)

    await manager.set_status(record.run_id, RunStatus.error, error="boom")

    stored = await store.get(record.run_id)
    assert stored is not None
    assert stored["status"] == "error"
    assert stored["error"] == "boom"


@pytest.mark.anyio
async def test_status_persistence_does_not_retry_permanent_sqlalchemy_errors():
    """Permanent SQLAlchemy failures should not be retried as SQLite pressure."""
    store = PermanentStatusRunStore()
    manager = RunManager(
        store=store,
        persistence_retry_policy=PersistenceRetryPolicy(max_attempts=5, initial_delay=0),
    )
    record = await manager.create("thread-1")

    await manager.set_status(record.run_id, RunStatus.error, error="boom")

    assert store.status_update_attempts == 1


@pytest.mark.anyio
async def test_try_start_respects_durable_and_racing_cancels():
    """Startup must not resurrect durable or locally racing cancels."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    record = await manager.create_or_reject("thread-1")
    await store.update_status(record.run_id, RunStatus.interrupted.value)

    assert await manager.try_start(record.run_id) == RunStartOutcome.cancelled
    assert record.status == RunStatus.interrupted
    assert (await store.get(record.run_id))["status"] == RunStatus.interrupted.value

    record = await manager.create_or_reject("thread-2")
    original_start_run = store.start_run

    async def start_then_cancel(run_id):
        updated = await original_start_run(run_id)
        await manager.cancel(record.run_id)
        return updated

    store.start_run = start_then_cancel

    assert await manager.try_start(record.run_id) == RunStartOutcome.cancelled
    assert record.status == RunStatus.interrupted
    assert (await store.get(record.run_id))["status"] == RunStatus.interrupted.value


@pytest.mark.anyio
async def test_fail_start_if_pending_marks_pending_run_error_and_persists():
    """Worker attach failures should finalize only runs still pending startup."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    record = await manager.create_or_reject("thread-1")
    error = "Failed to attach run worker: boom"

    assert await manager.fail_start_if_pending(record.run_id, error=error) is True

    stored = await store.get(record.run_id)
    assert record.status == RunStatus.error
    assert record.error == error
    assert record.abort_event.is_set()
    assert stored is not None
    assert stored["status"] == RunStatus.error.value
    assert stored["error"] == error

    running = await manager.create_or_reject("thread-2")
    assert await manager.try_start(running.run_id) == RunStartOutcome.started

    assert await manager.fail_start_if_pending(running.run_id, error="late") is False

    stored_running = await store.get(running.run_id)
    assert running.status == RunStatus.running
    assert running.error is None
    assert stored_running is not None
    assert stored_running["status"] == RunStatus.running.value
    assert stored_running["error"] is None


@pytest.mark.anyio
async def test_completion_persistence_recreates_missing_store_row():
    """Completion updates should recreate a missing row and persist final counters."""
    store = MissingCompletionRunStore()
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)
    await manager.set_status(record.run_id, RunStatus.success)
    await store.delete(record.run_id)

    await manager.update_run_completion(
        record.run_id,
        status="success",
        total_tokens=42,
        llm_call_count=2,
        last_ai_message="done",
    )

    stored = await store.get(record.run_id)
    assert stored is not None
    assert stored["status"] == "success"
    assert stored["total_tokens"] == 42
    assert stored["llm_call_count"] == 2
    assert stored["last_ai_message"] == "done"
    assert store.completion_update_attempts == 2


@pytest.mark.anyio
async def test_completion_persistence_warns_when_recreated_row_still_missing(caplog):
    """A second zero-row completion update after recreation should not be silent."""
    store = AlwaysMissingCompletionRunStore()
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.success)
    caplog.set_level(logging.WARNING, logger="deerflow.runtime.runs.manager")

    await manager.update_run_completion(record.run_id, status="success", total_tokens=42)

    assert store.completion_update_attempts == 2
    assert "affected no rows after row recreation" in caplog.text


@pytest.mark.anyio
async def test_reconcile_orphaned_inflight_runs_marks_stale_rows_error():
    """Startup recovery should turn persisted active rows into explicit errors."""
    store = MemoryRunStore()
    await store.put("pending-run", thread_id="thread-1", status="pending", created_at="2026-01-01T00:00:00+00:00")
    await store.put("running-run", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:01+00:00")
    await store.put("success-run", thread_id="thread-1", status="success", created_at="2026-01-01T00:00:02+00:00")
    manager = RunManager(store=store)

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
        before="2026-01-01T00:00:02+00:00",
    )

    assert {record.run_id for record in recovered} == {"pending-run", "running-run"}
    assert await _stored_statuses(store, "pending-run", "running-run", "success-run") == {
        "pending-run": "error",
        "running-run": "error",
        "success-run": "success",
    }


@pytest.mark.anyio
async def test_reconcile_orphaned_run_backfills_delivery_after_atomic_takeover():
    """Lease recovery must durably backfill the terminal receipt exactly once."""
    store = MemoryRunStore()
    events = MemoryRunEventStore()
    await store.put("running-run", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")
    manager = RunManager(store=store, event_store=events)

    first = await manager.reconcile_orphaned_inflight_runs(error="worker crashed", before="2026-01-01T00:00:01+00:00")
    second = await manager.reconcile_orphaned_inflight_runs(error="worker crashed", before="2026-01-01T00:00:01+00:00")

    assert [record.run_id for record in first] == ["running-run"]
    assert second == []
    delivery = await events.list_events("thread-1", "running-run", event_types=["run.delivery"])
    assert len(delivery) == 1
    assert delivery[0]["content"] == {"presented": 0, "paths": [], "by_tool": {}}
    assert (await store.get("running-run"))["status"] == "error"


@pytest.mark.anyio
async def test_reconcile_preserves_delivery_written_before_worker_crash():
    """A crash after the receipt but before status persistence keeps its facts."""
    store = MemoryRunStore()
    events = MemoryRunEventStore()
    await store.put("running-run", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")
    await events.put_if_absent(
        thread_id="thread-1",
        run_id="running-run",
        event_type="run.delivery",
        category="outputs",
        content={"presented": 1, "paths": ["report.md"], "by_tool": {"present_files": ["report.md"]}},
    )
    manager = RunManager(store=store, event_store=events)

    recovered = await manager.reconcile_orphaned_inflight_runs(error="worker crashed", before="2026-01-01T00:00:01+00:00")

    assert [record.run_id for record in recovered] == ["running-run"]
    delivery = await events.list_events("thread-1", "running-run", event_types=["run.delivery"])
    assert len(delivery) == 1
    assert delivery[0]["content"]["presented"] == 1


@pytest.mark.anyio
async def test_reconcile_preserves_terminal_takeover_when_delivery_backfill_fails():
    """A receipt-store outage must not undo an atomically claimed orphan."""

    class FailingReceiptStore(MemoryRunEventStore):
        async def put_if_absent(self, **kwargs):
            raise RuntimeError("event store unavailable")

    store = MemoryRunStore()
    await store.put("running-run", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")
    manager = RunManager(store=store, event_store=FailingReceiptStore())

    recovered = await manager.reconcile_orphaned_inflight_runs(error="worker crashed", before="2026-01-01T00:00:01+00:00")

    assert [record.run_id for record in recovered] == ["running-run"]
    assert (await store.get("running-run"))["status"] == "error"


@pytest.mark.anyio
async def test_reconcile_orphaned_inflight_runs_skips_live_local_run():
    """Startup recovery should not mark an active row orphaned when this worker owns it."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    stored = await store.get(record.run_id)
    assert recovered == []
    assert stored["status"] == "running"


@pytest.mark.anyio
async def test_reconcile_orphaned_inflight_runs_skips_rows_when_takeover_claim_fails():
    """Startup recovery must not report a row as recovered if the takeover claim failed."""
    store = FailingTakeoverRunStore()
    await store.put("running-run", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")
    manager = RunManager(
        store=store,
        persistence_retry_policy=PersistenceRetryPolicy(max_attempts=2, initial_delay=0),
    )

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
        before="2026-01-01T00:00:01+00:00",
    )

    stored = await store.get("running-run")
    assert recovered == []
    assert stored["status"] == "running"
    assert store.takeover_attempts == 2


@pytest.mark.anyio
async def test_cancel_not_inflight(manager: RunManager):
    """Cancelling a completed run should return not_cancellable."""
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.success)

    cancelled = await manager.cancel(record.run_id)
    assert cancelled == CancelOutcome.not_cancellable


@pytest.mark.anyio
async def test_list_by_thread(manager: RunManager, monkeypatch: pytest.MonkeyPatch):
    """Same thread should return multiple runs."""
    # Advance the fake clock 1ms per call so r2 gets a strictly newer
    # created_at than r1 even on hosts with coarse wall-clock granularity
    # (Windows timestamps can repeat across consecutive creates).
    base = datetime.now(UTC)
    calls = itertools.count()
    monkeypatch.setattr(
        "deerflow.runtime.runs.manager._now_iso",
        lambda: (base + timedelta(milliseconds=next(calls))).isoformat(),
    )

    r1 = await manager.create("thread-1")
    r2 = await manager.create("thread-1")
    await manager.create("thread-2")

    runs = await manager.list_by_thread("thread-1")
    assert len(runs) == 2
    # Newest first: r2 was created after r1.
    assert runs[0].run_id == r2.run_id
    assert runs[1].run_id == r1.run_id


@pytest.mark.anyio
async def test_list_by_thread_is_stable_when_timestamps_tie(manager: RunManager, monkeypatch: pytest.MonkeyPatch):
    """Timestamp ties break on run_id so keyset pagination has a total order."""
    monkeypatch.setattr("deerflow.runtime.runs.manager._now_iso", lambda: "2026-01-01T00:00:00+00:00")

    r1 = await manager.create("thread-1")
    r2 = await manager.create("thread-1")

    runs = await manager.list_by_thread("thread-1")
    assert [run.run_id for run in runs] == sorted([r1.run_id, r2.run_id], reverse=True)


@pytest.mark.anyio
async def test_has_inflight(manager: RunManager):
    """has_inflight should be True when a run is pending or running."""
    record = await manager.create("thread-1")
    assert await manager.has_inflight("thread-1") is True

    await manager.set_status(record.run_id, RunStatus.success)
    assert await manager.has_inflight("thread-1") is False


@pytest.mark.anyio
async def test_has_inflight_ignores_checkpoint_write_reservation(manager: RunManager):
    """Internal checkpoint writers are not user-visible runs."""
    async with manager.reserve_thread_operation(
        "thread-1",
        kind=ThreadOperationKind.checkpoint_write,
    ):
        assert await manager.has_inflight("thread-1") is False


@pytest.mark.anyio
async def test_cleanup_evicts_with_store(manager_with_store: RunManager):
    """With a store, cleanup releases the record and history stays readable."""
    mgr = manager_with_store
    record = await mgr.create("thread-1")
    run_id = record.run_id
    # Mirrors the production sequence: run_agent only schedules cleanup once
    # the run is terminal and its store row has been finalized.
    await mgr.set_status(run_id, RunStatus.success)

    await mgr.cleanup(run_id, delay=0)
    assert run_id not in mgr._runs
    hydrated = await mgr.get(run_id, user_id=record.user_id)
    assert hydrated is not None
    assert hydrated.run_id == run_id
    assert hydrated.status is RunStatus.success


@pytest.mark.anyio
async def test_cleanup_without_store_preserves_history(manager: RunManager):
    """Without a store there is no fallback, so cleanup must not erase history.

    ``run_agent`` schedules cleanup for every terminal run. Evicting in
    memory-only mode would drop the record from ``_runs`` with nothing left to
    hydrate it from, making completed runs disappear from history instead of
    being released from a durable copy.
    """
    record = await manager.create("thread-1")
    run_id = record.run_id
    await manager.set_status(run_id, RunStatus.success)

    await manager.cleanup(run_id, delay=0)

    assert await manager.get(run_id) is record
    assert [r.run_id for r in await manager.list_by_thread("thread-1")] == [run_id]


@pytest.mark.anyio
async def test_set_status_with_error(manager: RunManager):
    """Error message should be stored on the record."""
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.error, error="Something went wrong")
    assert record.status == RunStatus.error
    assert record.error == "Something went wrong"


@pytest.mark.anyio
async def test_get_nonexistent(manager: RunManager):
    """Getting a nonexistent run should return None."""
    assert await manager.get("does-not-exist") is None


@pytest.mark.anyio
async def test_get_hydrates_store_only_run():
    """Store-only runs should be readable after process restart."""
    store = MemoryRunStore()
    await store.put(
        "run-store-only",
        thread_id="thread-1",
        assistant_id="lead_agent",
        status="success",
        multitask_strategy="reject",
        metadata={"source": "store"},
        kwargs={"input": "value"},
        created_at="2026-01-01T00:00:00+00:00",
        model_name="model-a",
    )
    manager = RunManager(store=store)

    record = await manager.get("run-store-only")

    assert record is not None
    assert record.run_id == "run-store-only"
    assert record.thread_id == "thread-1"
    assert record.assistant_id == "lead_agent"
    assert record.status == RunStatus.success
    assert record.on_disconnect == DisconnectMode.cancel
    assert record.metadata == {"source": "store"}
    assert record.kwargs == {"input": "value"}
    assert record.model_name == "model-a"
    assert record.task is None
    assert record.store_only is True


@pytest.mark.anyio
async def test_get_hydrates_run_with_null_enum_fields():
    """Rows with NULL status/on_disconnect must hydrate with safe defaults, not raise."""
    store = MemoryRunStore()
    # Simulate a SQL row where the nullable status column is NULL
    await store.put(
        "run-null-status",
        thread_id="thread-1",
        status=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    manager = RunManager(store=store)

    record = await manager.get("run-null-status")

    assert record is not None
    assert record.status == RunStatus.pending
    assert record.on_disconnect == DisconnectMode.cancel
    assert record.store_only is True


@pytest.mark.anyio
async def test_list_by_thread_hydrates_run_with_null_enum_fields():
    """list_by_thread must not skip rows with NULL status; applies safe defaults."""
    store = MemoryRunStore()
    await store.put(
        "run-null-status-list",
        thread_id="thread-null",
        status=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    manager = RunManager(store=store)

    runs = await manager.list_by_thread("thread-null")

    assert len(runs) == 1
    assert runs[0].run_id == "run-null-status-list"
    assert runs[0].status == RunStatus.pending
    assert runs[0].on_disconnect == DisconnectMode.cancel


@pytest.mark.anyio
async def test_create_record_is_not_store_only(manager: RunManager):
    """In-memory records created via create() must have store_only=False."""
    record = await manager.create("thread-1")
    assert record.store_only is False


@pytest.mark.anyio
async def test_create_rolls_back_in_memory_record_on_store_failure():
    """create() must fail and hide the run when the initial store write fails."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.put = AsyncMock(side_effect=RuntimeError("db down"))
    manager = RunManager(store=store)

    with pytest.raises(RuntimeError, match="db down"):
        await manager.create("thread-1")

    assert manager._runs == {}
    assert await manager.list_by_thread("thread-1") == []


@pytest.mark.anyio
async def test_create_rolls_back_in_memory_record_on_store_cancellation():
    """create() must also roll back when cancelled during the initial store write."""
    store = MemoryRunStore()

    async def cancelled_put(run_id, **kwargs):
        raise asyncio.CancelledError

    store.put = cancelled_put
    manager = RunManager(store=store)

    with pytest.raises(asyncio.CancelledError):
        await manager.create("thread-1")

    assert manager._runs == {}
    assert await manager.list_by_thread("thread-1") == []


@pytest.mark.anyio
async def test_create_does_not_expose_run_until_store_persist_completes():
    """Concurrent readers must wait until the new run has been persisted."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    original_put = store.put
    put_started = asyncio.Event()
    allow_put = asyncio.Event()

    async def blocking_put(run_id, **kwargs):
        put_started.set()
        await allow_put.wait()
        return await original_put(run_id, **kwargs)

    store.put = blocking_put
    create_task = asyncio.create_task(manager.create("thread-1"))
    list_task = None

    try:
        await put_started.wait()
        list_task = asyncio.create_task(manager.list_by_thread("thread-1"))
        await asyncio.sleep(0)
        assert not list_task.done()

        allow_put.set()
        record = await create_task
        runs = await list_task

        assert [run.run_id for run in runs] == [record.run_id]
    finally:
        allow_put.set()
        cleanup_tasks = []
        for task in (list_task, create_task):
            if task is None:
                continue
            if not task.done():
                task.cancel()
            cleanup_tasks.append(task)
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)


@pytest.mark.anyio
async def test_get_prefers_in_memory_record_over_store():
    """In-memory records retain task/control state when store has same run."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    record = await manager.create("thread-1")
    await store.update_status(record.run_id, "success")

    fetched = await manager.get(record.run_id)

    assert fetched is record
    assert fetched.status == RunStatus.pending


@pytest.mark.anyio
async def test_list_by_thread_merges_store_runs_newest_first():
    """list_by_thread should merge memory and store rows with memory precedence."""
    store = MemoryRunStore()
    await store.put("old-store", thread_id="thread-1", status="success", created_at="2026-01-01T00:00:00+00:00")
    await store.put("other-thread", thread_id="thread-2", status="success", created_at="2026-01-03T00:00:00+00:00")
    manager = RunManager(store=store)
    memory_record = await manager.create("thread-1")

    runs = await manager.list_by_thread("thread-1")

    assert [run.run_id for run in runs] == [memory_record.run_id, "old-store"]
    assert runs[0] is memory_record


@pytest.mark.anyio
async def test_list_by_thread_limit_does_not_let_old_memory_hide_new_store_run():
    """A local row must not consume the store query's newest-run limit."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    old_memory = await manager.create("thread-1")
    old_memory.created_at = "2026-01-01T00:00:00+00:00"
    await store.put(
        "new-store",
        thread_id="thread-1",
        status="success",
        created_at="2026-01-02T00:00:00+00:00",
    )

    runs = await manager.list_by_thread("thread-1", limit=1)

    assert [run.run_id for run in runs] == ["new-store"]


@pytest.mark.anyio
async def test_list_by_thread_keyset_returns_older_page():
    """A (created_at, run_id) cursor walks past the newest page."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    for run_id, created_at in (
        ("r1", "2026-01-01T00:00:00+00:00"),
        ("r2", "2026-01-02T00:00:00+00:00"),
        ("r3", "2026-01-03T00:00:00+00:00"),
    ):
        await store.put(run_id, thread_id="thread-1", status="success", created_at=created_at)

    first = await manager.list_by_thread("thread-1", limit=2)
    assert [run.run_id for run in first] == ["r3", "r2"]

    second = await manager.list_by_thread(
        "thread-1",
        limit=2,
        before_created_at=first[-1].created_at,
        before_run_id=first[-1].run_id,
    )
    assert [run.run_id for run in second] == ["r1"]


@pytest.mark.anyio
async def test_list_by_thread_keyset_is_stable_when_timestamps_tie():
    """Tied created_at values must not skip or duplicate across pages."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    tied = "2026-01-01T00:00:00+00:00"
    for run_id in ("a", "b", "c"):
        await store.put(run_id, thread_id="thread-1", status="success", created_at=tied)

    first = await manager.list_by_thread("thread-1", limit=2)
    assert [run.run_id for run in first] == ["c", "b"]
    second = await manager.list_by_thread(
        "thread-1",
        limit=2,
        before_created_at=first[-1].created_at,
        before_run_id=first[-1].run_id,
    )
    assert [run.run_id for run in second] == ["a"]


@pytest.mark.anyio
async def test_list_by_thread_rejects_one_sided_keyset_cursor():
    """A one-sided cursor would silently drop the bound; fail instead of paging from the start."""
    manager = RunManager()
    with pytest.raises(
        ValueError,
        match="before_created_at and before_run_id must be provided together",
    ):
        await manager.list_by_thread(
            "thread-1",
            before_created_at="2026-01-02T00:00:00+00:00",
        )
    with pytest.raises(
        ValueError,
        match="before_created_at and before_run_id must be provided together",
    ):
        await manager.list_by_thread("thread-1", before_run_id="r2")
    with pytest.raises(
        ValueError,
        match="before_created_at and before_run_id must be provided together",
    ):
        await manager.list_by_thread(
            "thread-1",
            before_created_at="2026-01-02T00:00:00+00:00",
            before_run_id="",
        )
    with pytest.raises(
        ValueError,
        match="before_created_at must be an ISO-8601 timestamp",
    ):
        await manager.list_by_thread(
            "thread-1",
            before_created_at="not-a-timestamp",
            before_run_id="r2",
        )


@pytest.mark.anyio
async def test_list_by_thread_keyset_accepts_space_decoded_offset():
    """Query-decoded '+00:00' (a space) must still walk to the older page."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    for run_id, created_at in (
        ("r1", "2026-01-01T00:00:00+00:00"),
        ("r2", "2026-01-02T00:00:00+00:00"),
        ("r3", "2026-01-03T00:00:00+00:00"),
    ):
        await store.put(run_id, thread_id="thread-1", status="success", created_at=created_at)

    older = await manager.list_by_thread(
        "thread-1",
        limit=2,
        before_created_at="2026-01-02T00:00:00 00:00",
        before_run_id="r2",
    )
    assert [run.run_id for run in older] == ["r1"]


@pytest.mark.anyio
async def test_create_defaults(manager: RunManager):
    """Create with no optional args should use defaults."""
    record = await manager.create("thread-1")
    assert record.metadata == {}
    assert record.kwargs == {}
    assert record.multitask_strategy == "reject"
    assert record.assistant_id is None


@pytest.mark.anyio
async def test_model_name_create_or_reject():
    """create_or_reject should accept and persist model_name."""
    from deerflow.runtime.runs.schemas import DisconnectMode

    store = MemoryRunStore()
    mgr = RunManager(store=store)

    record = await mgr.create_or_reject(
        "thread-1",
        assistant_id="lead_agent",
        on_disconnect=DisconnectMode.cancel,
        metadata={"key": "val"},
        kwargs={"input": {}},
        multitask_strategy="reject",
        model_name="anthropic.claude-sonnet-4-20250514-v1:0",
    )
    assert record.model_name == "anthropic.claude-sonnet-4-20250514-v1:0"
    assert record.status == RunStatus.pending

    # Verify model_name was persisted to store
    stored = await store.get(record.run_id)
    assert stored is not None
    assert stored["model_name"] == "anthropic.claude-sonnet-4-20250514-v1:0"

    # Verify retrieval returns the model_name via in-memory record
    fetched = await mgr.get(record.run_id)
    assert fetched is not None
    assert fetched.model_name == "anthropic.claude-sonnet-4-20250514-v1:0"


@pytest.mark.anyio
async def test_create_or_reject_interrupt_persists_interrupted_status_to_store():
    """interrupt strategy should persist interrupted status for old runs."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)

    new = await manager.create_or_reject("thread-1", multitask_strategy="interrupt")

    stored_old = await store.get(old.run_id)
    assert new.run_id != old.run_id
    assert old.status == RunStatus.interrupted
    assert stored_old is not None
    assert stored_old["status"] == "interrupted"


@pytest.mark.anyio
async def test_create_or_reject_does_not_interrupt_old_run_when_new_run_store_write_fails():
    """A failed new-run persist must not cancel the existing inflight run."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)
    store.create_thread_operation_atomic = AsyncMock(side_effect=RuntimeError("db down"))

    with pytest.raises(RuntimeError, match="db down"):
        await manager.create_or_reject("thread-1", multitask_strategy="interrupt")

    stored_old = await store.get(old.run_id)
    assert list(manager._runs) == [old.run_id]
    assert old.status == RunStatus.running
    assert old.abort_event.is_set() is False
    assert stored_old is not None
    assert stored_old["status"] == "running"


@pytest.mark.anyio
async def test_create_or_reject_does_not_interrupt_old_run_when_new_run_store_write_is_cancelled():
    """Cancellation during new-run persist must not cancel the existing run."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)

    async def cancelled_create(run_id, **kwargs):
        raise asyncio.CancelledError

    store.create_thread_operation_atomic = cancelled_create

    with pytest.raises(asyncio.CancelledError):
        await manager.create_or_reject("thread-1", multitask_strategy="interrupt")

    stored_old = await store.get(old.run_id)
    assert list(manager._runs) == [old.run_id]
    assert old.status == RunStatus.running
    assert old.abort_event.is_set() is False
    assert stored_old is not None
    assert stored_old["status"] == "running"


@pytest.mark.anyio
@pytest.mark.parametrize("strategy", ["interrupt", "rollback"])
async def test_create_or_reject_cancellation_after_registration_interrupts_replacement(
    monkeypatch: pytest.MonkeyPatch,
    strategy: str,
) -> None:
    """Cancellation after admission must not leave the replacement active."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)
    persist_started = asyncio.Event()
    release_persist = asyncio.Event()
    original_persist_status = manager._persist_status

    async def blocking_persist_status(record: Any, status: RunStatus, **kwargs: Any) -> bool:
        persist_started.set()
        await asyncio.wait_for(release_persist.wait(), timeout=1)
        return await original_persist_status(record, status, **kwargs)

    monkeypatch.setattr(manager, "_persist_status", blocking_persist_status)
    create_task = asyncio.create_task(manager.create_or_reject("thread-1", multitask_strategy=strategy))
    await asyncio.wait_for(persist_started.wait(), timeout=1)
    create_task.cancel()
    release_persist.set()

    with pytest.raises(asyncio.CancelledError):
        _ = await create_task

    records = await manager.list_by_thread("thread-1")
    replacement = next(record for record in records if record.run_id != old.run_id)
    stored_replacement = await store.get(replacement.run_id)
    assert not await manager.has_inflight("thread-1")
    assert replacement.status == RunStatus.interrupted
    assert replacement.abort_event.is_set()
    assert stored_replacement is not None
    assert stored_replacement["status"] == RunStatus.interrupted.value


@pytest.mark.anyio
async def test_create_or_reject_repeated_cancellation_drains_replacement_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated cancellation must not abandon the durable cleanup task."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)
    old_persist_started = asyncio.Event()
    release_old_persist = asyncio.Event()
    replacement_persist_started = asyncio.Event()
    release_replacement_persist = asyncio.Event()
    original_persist_status = manager._persist_status

    async def staged_persist_status(record: Any, status: RunStatus, **kwargs: Any) -> bool:
        if record.run_id == old.run_id:
            old_persist_started.set()
            await asyncio.wait_for(release_old_persist.wait(), timeout=1)
        else:
            replacement_persist_started.set()
            await asyncio.wait_for(release_replacement_persist.wait(), timeout=1)
        return await original_persist_status(record, status, **kwargs)

    monkeypatch.setattr(manager, "_persist_status", staged_persist_status)
    create_task = asyncio.create_task(manager.create_or_reject("thread-1", multitask_strategy="interrupt"))
    await asyncio.wait_for(old_persist_started.wait(), timeout=1)
    replacement = next(record for record in manager._runs.values() if record.run_id != old.run_id)

    create_task.cancel()
    release_old_persist.set()
    await asyncio.wait_for(replacement_persist_started.wait(), timeout=1)
    create_task.cancel()
    await asyncio.sleep(0)
    assert not create_task.done()

    release_replacement_persist.set()
    with pytest.raises(asyncio.CancelledError):
        _ = await asyncio.wait_for(create_task, timeout=1)

    stored_replacement = await store.get(replacement.run_id)
    assert replacement.status == RunStatus.interrupted
    assert stored_replacement is not None
    assert stored_replacement["status"] == RunStatus.interrupted.value


@pytest.mark.anyio
async def test_create_or_reject_retries_replacement_when_cancel_status_cannot_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed best-effort update must get a strict durable retry."""

    class FailFirstReplacementInterruptStore(MemoryRunStore):
        failed = False

        async def get(self, run_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
            raw = await super().get(run_id)
            if raw is not None and raw.get("status") == RunStatus.pending.value and raw.get("user_id") is not None and user_id != raw.get("user_id"):
                raise RuntimeError("replacement lookup was not owner-scoped")
            return await super().get(run_id, user_id=user_id)

        async def update_status(self, run_id: str, status: str, **kwargs: Any) -> bool:
            row = await super().get(run_id)
            if not self.failed and status == RunStatus.interrupted.value and row is not None and row.get("status") == RunStatus.pending.value:
                self.failed = True
                raise RuntimeError("replacement status write failed")
            return await super().update_status(run_id, status, **kwargs)

    store = FailFirstReplacementInterruptStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1", user_id="owner-1")
    await manager.set_status(old.run_id, RunStatus.running)
    old_persist_started = asyncio.Event()
    release_old_persist = asyncio.Event()
    original_persist_status = manager._persist_status

    async def block_old_persist(record: Any, status: RunStatus, **kwargs: Any) -> bool:
        if record.run_id != old.run_id:
            return await original_persist_status(record, status, **kwargs)
        old_persist_started.set()
        await asyncio.wait_for(release_old_persist.wait(), timeout=1)
        return await original_persist_status(record, status, **kwargs)

    monkeypatch.setattr(manager, "_persist_status", block_old_persist)
    create_task = asyncio.create_task(manager.create_or_reject("thread-1", multitask_strategy="interrupt", user_id="owner-1"))
    await asyncio.wait_for(old_persist_started.wait(), timeout=1)
    replacement = next(record for record in manager._runs.values() if record.run_id != old.run_id)
    create_task.cancel()
    release_old_persist.set()

    with pytest.raises(asyncio.CancelledError):
        _ = await asyncio.wait_for(create_task, timeout=1)

    stored_replacement = await store.get(replacement.run_id, user_id="owner-1")
    assert stored_replacement is not None
    assert stored_replacement["status"] == RunStatus.interrupted.value
    assert replacement.status == RunStatus.interrupted
    assert not await manager.has_inflight("thread-1")


@pytest.mark.anyio
async def test_create_or_reject_cleanup_failure_preserves_caller_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup IO failure must not replace the caller's CancelledError."""

    class FailingReplacementCleanupStore(MemoryRunStore):
        replacement_update_failed = False

        async def update_status(self, run_id: str, status: str, **kwargs: Any) -> bool:
            row = await super().get(run_id)
            if status == RunStatus.interrupted.value and row is not None and row.get("status") == RunStatus.pending.value:
                self.replacement_update_failed = True
                raise RuntimeError("replacement status unavailable")
            return await super().update_status(run_id, status, **kwargs)

        async def get(self, run_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
            row = await super().get(run_id, user_id=user_id)
            if self.replacement_update_failed and row is not None and row.get("status") == RunStatus.pending.value:
                raise RuntimeError("replacement verification unavailable")
            return row

    store = FailingReplacementCleanupStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)
    old_persist_started = asyncio.Event()
    release_old_persist = asyncio.Event()
    original_persist_status = manager._persist_status

    async def block_old_persist(record: Any, status: RunStatus, **kwargs: Any) -> bool:
        if record.run_id != old.run_id:
            return await original_persist_status(record, status, **kwargs)
        old_persist_started.set()
        await asyncio.wait_for(release_old_persist.wait(), timeout=1)
        return await original_persist_status(record, status, **kwargs)

    monkeypatch.setattr(manager, "_persist_status", block_old_persist)
    create_task = asyncio.create_task(manager.create_or_reject("thread-1", multitask_strategy="interrupt"))
    await asyncio.wait_for(old_persist_started.wait(), timeout=1)
    create_task.cancel()
    release_old_persist.set()

    with pytest.raises(asyncio.CancelledError):
        _ = await asyncio.wait_for(create_task, timeout=1)


@pytest.mark.anyio
async def test_create_or_reject_preserves_peer_terminal_status_during_cancel_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A peer terminal transition must win the strict cancellation retry."""

    class PeerWinsReplacementInterruptStore(MemoryRunStore):
        replacement_attempts = 0

        async def update_status(self, run_id: str, status: str, **kwargs: Any) -> bool:
            row = await self.get(run_id)
            if status == RunStatus.interrupted.value and row is not None and row.get("status") == RunStatus.pending.value:
                self.replacement_attempts += 1
                if self.replacement_attempts == 1:
                    raise RuntimeError("replacement status write failed")
                await super().update_status(run_id, RunStatus.error.value, error="peer takeover")
                return False
            return await super().update_status(run_id, status, **kwargs)

    store = PeerWinsReplacementInterruptStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)
    old_persist_started = asyncio.Event()
    release_old_persist = asyncio.Event()
    original_persist_status = manager._persist_status

    async def block_old_persist(record: Any, status: RunStatus, **kwargs: Any) -> bool:
        if record.run_id != old.run_id:
            return await original_persist_status(record, status, **kwargs)
        old_persist_started.set()
        await asyncio.wait_for(release_old_persist.wait(), timeout=1)
        return await original_persist_status(record, status, **kwargs)

    monkeypatch.setattr(manager, "_persist_status", block_old_persist)
    create_task = asyncio.create_task(manager.create_or_reject("thread-1", multitask_strategy="interrupt"))
    await asyncio.wait_for(old_persist_started.wait(), timeout=1)
    replacement = next(record for record in manager._runs.values() if record.run_id != old.run_id)
    create_task.cancel()
    release_old_persist.set()

    with pytest.raises(asyncio.CancelledError):
        _ = await asyncio.wait_for(create_task, timeout=1)

    stored_replacement = await store.get(replacement.run_id)
    assert stored_replacement is not None
    assert stored_replacement["status"] == RunStatus.error.value
    assert stored_replacement["error"] == "peer takeover"
    assert replacement.status == RunStatus.error
    assert replacement.error == "peer takeover"
    assert not await manager.has_inflight("thread-1")


@pytest.mark.anyio
async def test_create_or_reject_rollback_persists_interrupted_status_to_store():
    """rollback strategy should persist interrupted status for old runs."""
    store = MemoryRunStore()
    manager = RunManager(store=store)
    old = await manager.create("thread-1")
    await manager.set_status(old.run_id, RunStatus.running)

    new = await manager.create_or_reject("thread-1", multitask_strategy="rollback")

    stored_old = await store.get(old.run_id)
    assert new.run_id != old.run_id
    assert old.status == RunStatus.interrupted
    assert stored_old is not None
    assert stored_old["status"] == "interrupted"


@pytest.mark.anyio
async def test_model_name_default_is_none():
    """create_or_reject without model_name should default to None."""
    from deerflow.runtime.runs.schemas import DisconnectMode

    store = MemoryRunStore()
    mgr = RunManager(store=store)

    record = await mgr.create_or_reject(
        "thread-1",
        on_disconnect=DisconnectMode.cancel,
        model_name=None,
    )
    assert record.model_name is None

    stored = await store.get(record.run_id)
    assert stored["model_name"] is None


# ---------------------------------------------------------------------------
# Store fallback tests (simulates gateway restart scenario)
# ---------------------------------------------------------------------------


@pytest.fixture
def manager_with_store() -> RunManager:
    """RunManager backed by a MemoryRunStore."""
    return RunManager(store=MemoryRunStore())


@pytest.mark.anyio
async def test_list_by_thread_returns_store_records_after_restart(manager_with_store: RunManager):
    """After in-memory state is cleared (simulating restart), list_by_thread
    should still return runs from the persistent store."""
    mgr = manager_with_store
    r1 = await mgr.create("thread-1", "agent-1")
    await mgr.set_status(r1.run_id, RunStatus.success)
    r2 = await mgr.create("thread-1", "agent-2")
    await mgr.set_status(r2.run_id, RunStatus.error, error="boom")

    # Clear in-memory dict to simulate a restart
    mgr._runs.clear()

    runs = await mgr.list_by_thread("thread-1")
    assert len(runs) == 2
    statuses = {r.run_id: r.status for r in runs}
    assert statuses[r1.run_id] == RunStatus.success
    assert statuses[r2.run_id] == RunStatus.error
    # Verify other fields survive the round-trip
    for r in runs:
        assert r.thread_id == "thread-1"
        assert ISO_RE.match(r.created_at)


@pytest.mark.anyio
async def test_list_by_thread_merges_in_memory_and_store(manager_with_store: RunManager):
    """In-memory runs should be included alongside store-only records."""
    mgr = manager_with_store

    # Create a run and let it complete (will be in both memory and store)
    r1 = await mgr.create("thread-1")
    await mgr.set_status(r1.run_id, RunStatus.success)

    # Simulate restart: clear memory, then create a new in-memory run
    mgr._runs.clear()
    r2 = await mgr.create("thread-1")

    runs = await mgr.list_by_thread("thread-1")
    assert len(runs) == 2
    run_ids = {r.run_id for r in runs}
    assert r1.run_id in run_ids
    assert r2.run_id in run_ids

    # r2 should be the in-memory record (has live state)
    r2_record = next(r for r in runs if r.run_id == r2.run_id)
    assert r2_record is r2  # same object reference


@pytest.mark.anyio
async def test_list_by_thread_no_store():
    """Without a store, list_by_thread should only return in-memory runs."""
    mgr = RunManager()
    await mgr.create("thread-1")

    mgr._runs.clear()
    runs = await mgr.list_by_thread("thread-1")
    assert runs == []


@pytest.mark.anyio
async def test_aget_returns_in_memory_record(manager_with_store: RunManager):
    """aget should return the in-memory record when available."""
    mgr = manager_with_store
    r1 = await mgr.create("thread-1", "agent-1")

    result = await mgr.aget(r1.run_id)
    assert result is r1  # same object


@pytest.mark.anyio
async def test_aget_falls_back_to_store(manager_with_store: RunManager):
    """aget should return a record from the store when not in memory."""
    mgr = manager_with_store
    r1 = await mgr.create("thread-1", "agent-1")
    await mgr.set_status(r1.run_id, RunStatus.success)

    mgr._runs.clear()

    result = await mgr.aget(r1.run_id)
    assert result is not None
    assert result.run_id == r1.run_id
    assert result.status == RunStatus.success
    assert result.thread_id == "thread-1"
    assert result.assistant_id == "agent-1"


@pytest.mark.anyio
async def test_aget_falls_back_to_store_with_user_filter():
    """aget should honor user_id when reading store-only records."""
    store = MemoryRunStore()
    await store.put("run-1", thread_id="thread-1", user_id="user-1", status="success")
    mgr = RunManager(store=store)

    allowed = await mgr.aget("run-1", user_id="user-1")
    denied = await mgr.aget("run-1", user_id="user-2")
    assert allowed is not None
    assert denied is None


@pytest.mark.anyio
async def test_aget_returns_none_for_unknown(manager_with_store: RunManager):
    """aget should return None for a run ID that doesn't exist anywhere."""
    result = await manager_with_store.aget("nonexistent-run-id")
    assert result is None


@pytest.mark.anyio
async def test_aget_store_failure_is_graceful():
    """If the store raises, aget should return None instead of propagating."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.get = AsyncMock(side_effect=RuntimeError("db down"))
    mgr = RunManager(store=store)

    result = await mgr.aget("some-id")
    assert result is None


@pytest.mark.anyio
async def test_get_can_surface_store_failure_for_lifecycle_callers():
    """Lifecycle code must distinguish a missing run from an unavailable store."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.get = AsyncMock(side_effect=RuntimeError("db down"))
    mgr = RunManager(store=store)

    with pytest.raises(RuntimeError, match="db down"):
        await mgr.get("some-id", raise_on_store_error=True)


@pytest.mark.anyio
async def test_list_by_thread_store_failure_is_graceful():
    """If the store raises, list_by_thread should return only in-memory runs."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.list_by_thread = AsyncMock(side_effect=RuntimeError("db down"))
    mgr = RunManager(store=store)

    r1 = await mgr.create("thread-1")
    runs = await mgr.list_by_thread("thread-1")
    assert len(runs) == 1
    assert runs[0].run_id == r1.run_id


@pytest.mark.anyio
async def test_list_by_thread_falls_back_to_store_with_user_filter():
    """list_by_thread should return only the requesting user's store records."""
    store = MemoryRunStore()
    await store.put("run-1", thread_id="thread-1", user_id="user-1", status="success")
    await store.put("run-2", thread_id="thread-1", user_id="user-2", status="success")
    mgr = RunManager(store=store)

    runs = await mgr.list_by_thread("thread-1", user_id="user-1")
    assert [r.run_id for r in runs] == ["run-1"]


# ---------------------------------------------------------------------------
# Per-thread index (thread_id -> run_ids): keeps per-thread queries
# O(runs-in-thread) instead of scanning every in-memory run, and stays
# consistent with ``_runs`` across create / cleanup / rollback.
# ---------------------------------------------------------------------------


class _FailingPutRunStore(MemoryRunStore):
    """Memory run store whose every ``put`` and atomic operation create fails."""

    async def put(self, run_id, **kwargs):
        raise ValueError("simulated persist failure")

    async def create_thread_operation_atomic(self, run_id, **kwargs):
        raise ValueError("simulated persist failure")


@pytest.mark.anyio
async def test_thread_index_scopes_runs_per_thread(manager: RunManager):
    a1 = await manager.create("thread-a")
    a2 = await manager.create("thread-a")
    b1 = await manager.create("thread-b")

    # The index mirrors _runs membership, bucketed by thread.
    assert set(manager._runs_by_thread["thread-a"]) == {a1.run_id, a2.run_id}
    assert set(manager._runs_by_thread["thread-b"]) == {b1.run_id}

    # Per-thread queries return only that thread's runs (no cross-thread leak).
    assert {r.run_id for r in await manager.list_by_thread("thread-a")} == {a1.run_id, a2.run_id}
    assert {r.run_id for r in await manager.list_by_thread("thread-b")} == {b1.run_id}
    assert await manager.list_by_thread("thread-missing") == []


@pytest.mark.anyio
async def test_thread_index_preserves_insertion_order(manager: RunManager):
    # The index is insertion-ordered (dict-as-ordered-set) so list_by_thread
    # keeps the stable tie-breaking the full-scan implementation guaranteed.
    first = await manager.create("thread-a")
    second = await manager.create("thread-a")
    assert list(manager._runs_by_thread["thread-a"]) == [first.run_id, second.run_id]


@pytest.mark.anyio
async def test_thread_index_cleanup_prunes_run_and_empty_bucket(manager_with_store: RunManager):
    mgr = manager_with_store
    a1 = await mgr.create("thread-a")
    a2 = await mgr.create("thread-a")

    await mgr.cleanup(a1.run_id, delay=0)
    assert a1.run_id not in mgr._runs
    assert set(mgr._runs_by_thread["thread-a"]) == {a2.run_id}

    await mgr.cleanup(a2.run_id, delay=0)
    # Empty buckets are pruned so the index cannot grow without bound.
    assert "thread-a" not in mgr._runs_by_thread
    # Both records survive as store-only history; the store does not promise
    # to preserve the in-memory insertion order.
    assert {r.run_id for r in await mgr.list_by_thread("thread-a")} == {a1.run_id, a2.run_id}


@pytest.mark.anyio
async def test_has_inflight_reflects_index(manager: RunManager):
    record = await manager.create("thread-a")
    assert await manager.has_inflight("thread-a") is True
    assert await manager.has_inflight("thread-b") is False

    await manager.set_status(record.run_id, RunStatus.success)
    assert await manager.has_inflight("thread-a") is False


@pytest.mark.anyio
async def test_create_or_reject_inflight_is_thread_scoped(manager: RunManager):
    await manager.create_or_reject("thread-a", multitask_strategy="reject")
    # A different thread is unaffected by thread-a's active run.
    await manager.create_or_reject("thread-b", multitask_strategy="reject")
    # A second active run on the same thread is rejected.
    with pytest.raises(ConflictError):
        await manager.create_or_reject("thread-a", multitask_strategy="reject")


@pytest.mark.anyio
async def test_failed_create_unindexes_run():
    manager = RunManager(store=_FailingPutRunStore())
    with pytest.raises(ValueError):
        await manager.create("thread-a")
    # A rolled-back run must leave no trace in either _runs or the index.
    assert manager._runs == {}
    assert "thread-a" not in manager._runs_by_thread


@pytest.mark.anyio
async def test_failed_create_or_reject_unindexes_run():
    # Symmetric to test_failed_create_unindexes_run: create_or_reject has its own
    # insert + rollback-unindex site, so a persist failure there must also leave
    # neither _runs nor the index holding the rolled-back run. This closes the last
    # mutation path not exercised by an index-consistency test.
    manager = RunManager(store=_FailingPutRunStore())
    with pytest.raises(ValueError):
        await manager.create_or_reject("thread-a", multitask_strategy="reject")
    assert manager._runs == {}
    assert "thread-a" not in manager._runs_by_thread


# --- merged from test_run_manager.py (subdir-only tests; root copy is the dedup base) ---
class FailingTakeoverStore(MemoryRunStore):
    """Memory run store whose takeover claim always fails with a transient error."""

    def __init__(self) -> None:
        super().__init__()
        self.takeover_attempts = 0

    async def claim_for_takeover(self, run_id, *, grace_seconds, error, stop_reason=None):
        self.takeover_attempts += 1
        raise sqlite3.OperationalError("database is locked")


def _make_record(
    run_id: str = "r1",
    thread_id: str = "t1",
    status: RunStatus = RunStatus.pending,
    **overrides: Any,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id="a1",
        status=status,
        on_disconnect=DisconnectMode.cancel,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        **overrides,
    )


@pytest.mark.anyio
async def test_reconcile_orphaned_inflight_runs_skips_rows_when_error_status_is_not_persisted():
    """Startup recovery must not report a row as recovered if the error update failed."""
    store = FailingTakeoverStore()
    await store.put("running-run", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")
    manager = RunManager(
        store=store,
        persistence_retry_policy=PersistenceRetryPolicy(max_attempts=2, initial_delay=0),
    )

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
        before="2026-01-01T00:00:01+00:00",
    )

    stored = await store.get("running-run")
    assert recovered == []
    assert stored["status"] == "running"
    assert store.takeover_attempts == 2


@pytest.mark.anyio
async def test_cleanup(manager_with_store: RunManager):
    """Upstream cleanup contract: eviction is store-gated.

    With a RunStore behind the manager, cleanup drops the live in-memory entry
    while history stays readable through the store fallback in ``get()``.
    A store-less manager keeps the record (retain-forever).
    """
    record = await manager_with_store.create("thread-1")
    run_id = record.run_id

    await manager_with_store.cleanup(run_id, delay=0)
    assert run_id not in manager_with_store._runs
    # History remains readable through the store fallback (rehydrated copy).
    hydrated = await manager_with_store.get(run_id)
    assert hydrated is not None and hydrated.run_id == run_id

    storeless = RunManager()
    stale = await storeless.create("thread-1")
    await storeless.cleanup(stale.run_id, delay=0)
    assert stale.run_id in storeless._runs


@pytest.mark.anyio
async def test_create_or_reject_generates_uuid_run_id() -> None:
    """Upstream admission generates a fresh UUID run_id internally."""
    manager = RunManager()

    record = await manager.create_or_reject("thread-generated")

    assert record.run_id
    assert str(uuid.UUID(record.run_id)) == record.run_id


def test_retryable_error_cycle_detection():
    """Circular exception __context__ chain should terminate (line 48)."""
    exc_a = RuntimeError("a")
    exc_b = RuntimeError("b")
    exc_a.__context__ = exc_b
    exc_b.__context__ = exc_a
    # Neither has a retryable message, so should return False without hanging
    assert _is_retryable_persistence_error(exc_a) is False


def test_retryable_error_sqlite_error_code_path():
    """sqlite3.OperationalError with retryable sqlite_errorcode (line 57)."""
    exc = sqlite3.OperationalError("some lock issue")
    exc.sqlite_errorcode = sqlite3.SQLITE_BUSY
    assert _is_retryable_persistence_error(exc) is True


def test_retryable_error_sqlite_locked_code():
    """sqlite3.OperationalError with SQLITE_LOCKED code (line 57)."""
    exc = sqlite3.OperationalError("table locked")
    exc.sqlite_errorcode = sqlite3.SQLITE_LOCKED
    assert _is_retryable_persistence_error(exc) is True


def test_retryable_error_non_retryable_code():
    """sqlite3.OperationalError with non-retryable code should return False."""
    exc = sqlite3.OperationalError("syntax error")
    exc.sqlite_errorcode = 1  # SQLITE_ERROR
    assert _is_retryable_persistence_error(exc) is False


@pytest.mark.anyio
async def test_persist_snapshot_to_store_no_store():
    """_persist_snapshot_to_store returns True when no store is configured (line 172)."""
    mgr = RunManager()
    result = await mgr._persist_snapshot_to_store("r1", {"thread_id": "t1"})
    assert result is True


@pytest.mark.anyio
async def test_persist_snapshot_to_store_exception_returns_false():
    """_persist_snapshot_to_store returns False when put raises (lines 180-182)."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    # Make put raise a non-retryable error
    store.put = AsyncMock(side_effect=RuntimeError("permanent failure"))
    mgr = RunManager(store=store)
    result = await mgr._persist_snapshot_to_store("r1", {"thread_id": "t1"})
    assert result is False


@pytest.mark.anyio
async def test_persist_to_store_delegates_to_snapshot():
    """_persist_to_store delegates to _persist_snapshot_to_store (line 203)."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    record = _make_record()
    result = await mgr._persist_to_store(record)
    assert result is True


@pytest.mark.anyio
async def test_persist_to_store_with_error():
    """_persist_to_store passes error to payload."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    record = _make_record()
    result = await mgr._persist_to_store(record, error="some error")
    assert result is True


@pytest.mark.anyio
async def test_update_run_completion_no_store():
    """update_run_completion returns early when no store (line 273)."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    await mgr.update_run_completion(record.run_id, total_tokens=100)
    assert record.total_tokens == 100


@pytest.mark.anyio
async def test_update_run_completion_unknown_run_no_store():
    """update_run_completion with unknown run and no store returns immediately."""
    mgr = RunManager()
    await mgr.update_run_completion("nonexistent", total_tokens=100)


@pytest.mark.anyio
async def test_update_run_completion_missing_run_in_memory_store_returns_false():
    """When run is not in _runs and store returns False, warn and return (lines 282-283)."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.update_run_completion = AsyncMock(return_value=False)
    mgr = RunManager(store=store)
    # Call with a run_id that was never created in memory
    await mgr.update_run_completion("nonexistent", status="success", total_tokens=42)


@pytest.mark.anyio
async def test_update_run_completion_recovery_snapshot_persist_fails():
    """When recovery snapshot persist also fails, return early (line 285)."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    record_holder = {}

    original_put = store.put

    async def put_then_fail(run_id, **kwargs):
        # First put (during create) succeeds
        if run_id not in record_holder:
            record_holder[run_id] = True
            return await original_put(run_id, **kwargs)
        # Subsequent puts (recovery) fail
        raise ValueError("put failed")

    store.put = put_then_fail
    store.update_run_completion = AsyncMock(return_value=False)
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    await mgr.update_run_completion(record.run_id, status="success", total_tokens=42)


@pytest.mark.anyio
async def test_update_run_completion_store_exception():
    """Non-retryable exception in update_run_completion is caught (lines 293-294)."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.update_run_completion = AsyncMock(side_effect=ValueError("bad data"))
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    # Should not raise
    await mgr.update_run_completion(record.run_id, status="success")


@pytest.mark.anyio
async def test_update_run_progress_running_run():
    """update_run_progress persists token data for running runs (lines 298-312)."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    await mgr.set_status(record.run_id, RunStatus.running)

    await mgr.update_run_progress(record.run_id, total_tokens=42, message_count=3)
    assert record.total_tokens == 42
    assert record.message_count == 3


@pytest.mark.anyio
async def test_update_run_progress_non_running_run():
    """update_run_progress skips persist for non-running runs."""
    store = MemoryRunStore()
    original_progress = store.update_run_progress
    called = False

    async def tracking_progress(run_id, **kwargs):
        nonlocal called
        called = True
        return await original_progress(run_id, **kwargs)

    store.update_run_progress = tracking_progress
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    # record is pending, not running
    await mgr.update_run_progress(record.run_id, total_tokens=42)
    assert called is False


@pytest.mark.anyio
async def test_update_run_progress_unknown_run():
    """update_run_progress is a no-op for unknown run IDs."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    await mgr.update_run_progress("nonexistent", total_tokens=42)


@pytest.mark.anyio
async def test_update_run_progress_no_store():
    """update_run_progress without store just updates in-memory record."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    record.status = RunStatus.running
    await mgr.update_run_progress(record.run_id, total_tokens=42)
    assert record.total_tokens == 42


@pytest.mark.anyio
async def test_update_run_progress_store_exception():
    """update_run_progress handles store exceptions gracefully."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.update_run_progress = AsyncMock(side_effect=RuntimeError("db error"))
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    record.status = RunStatus.running
    # Should not raise
    await mgr.update_run_progress(record.run_id, total_tokens=42)


@pytest.mark.anyio
async def test_update_run_progress_skips_none_values():
    """update_run_progress skips kwargs with None values."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    record.status = RunStatus.running
    await mgr.update_run_progress(record.run_id, total_tokens=None, message_count=5)
    assert record.total_tokens == 0  # unchanged
    assert record.message_count == 5


@pytest.mark.anyio
async def test_get_returns_in_memory_record_after_store_fetch():
    """When a concurrent create() inserts the record during store fetch,
    the in-memory record should win (line 378)."""

    store = MemoryRunStore()
    original_get = store.get
    get_started = asyncio.Event()
    allow_get = asyncio.Event()

    async def blocking_get(run_id, *, user_id=None):
        get_started.set()
        await allow_get.wait()
        return await original_get(run_id, user_id=user_id)

    store.get = blocking_get
    mgr = RunManager(store=store)

    # First, put a run in the store (simulating old run from before restart)
    await store.put("old-run", thread_id="thread-1", status="success", created_at="2026-01-01T00:00:00+00:00")

    # Start a get task that will block on the store
    get_task = asyncio.create_task(mgr.get("old-run"))
    try:
        await get_started.wait()

        # While get is blocked, create the run in memory (simulating concurrent create)
        mgr._runs["old-run"] = _make_record(run_id="old-run", thread_id="thread-1")

        allow_get.set()
        result = await get_task
        # Should return the in-memory record, not the store-only one
        assert result is not None
        assert result.store_only is False
    finally:
        allow_get.set()
        if not get_task.done():
            get_task.cancel()
        await asyncio.gather(get_task, return_exceptions=True)


@pytest.mark.anyio
async def test_get_record_from_store_exception():
    """get() should return None when _record_from_store raises (lines 383-385)."""
    from unittest.mock import patch

    store = MemoryRunStore()
    await store.put("bad-row", thread_id="thread-1", status="success")
    mgr = RunManager(store=store)

    with patch.object(RunManager, "_record_from_store", side_effect=ValueError("bad row")):
        result = await mgr.get("bad-row")
    assert result is None


@pytest.mark.anyio
async def test_list_by_thread_store_row_mapping_failure():
    """list_by_thread should skip store rows that fail to map (lines 423-424)."""
    from unittest.mock import patch

    store = MemoryRunStore()
    await store.put("bad-row", thread_id="thread-1", status="success")
    await store.put("good-row", thread_id="thread-1", status="success")
    mgr = RunManager(store=store)

    original_from_store = RunManager._record_from_store

    def selective_fail(row):
        if row.get("run_id") == "bad-row":
            raise ValueError("bad row")
        return original_from_store(row)

    with patch.object(RunManager, "_record_from_store", side_effect=selective_fail):
        runs = await mgr.list_by_thread("thread-1")

    run_ids = [r.run_id for r in runs]
    assert "bad-row" not in run_ids
    assert "good-row" in run_ids


@pytest.mark.anyio
async def test_set_status_unknown_run():
    """set_status for unknown run should log warning and return (lines 432-433)."""
    mgr = RunManager()
    # Should not raise
    await mgr.set_status("nonexistent", RunStatus.running)


@pytest.mark.anyio
async def test_persist_model_name_no_store():
    """_persist_model_name is a no-op when no store (line 443-444)."""
    mgr = RunManager()
    await mgr._persist_model_name("r1", "gpt-4")


@pytest.mark.anyio
async def test_persist_model_name_success():
    """_persist_model_name calls store.update_model_name (lines 445-450)."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    await mgr._persist_model_name(record.run_id, "gpt-4")
    stored = await store.get(record.run_id)
    assert stored["model_name"] == "gpt-4"


@pytest.mark.anyio
async def test_persist_model_name_exception():
    """_persist_model_name handles store exceptions (lines 451-452)."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.update_model_name = AsyncMock(side_effect=RuntimeError("db error"))
    mgr = RunManager(store=store)
    # Should not raise
    await mgr._persist_model_name("r1", "gpt-4")


@pytest.mark.anyio
async def test_update_model_name_unknown_run():
    """update_model_name for unknown run logs warning and returns (lines 458-460)."""
    mgr = RunManager()
    # Should not raise
    await mgr.update_model_name("nonexistent", "gpt-4")


@pytest.mark.anyio
async def test_update_model_name_success():
    """update_model_name updates in-memory record and persists (lines 461-464)."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    await mgr.update_model_name(record.run_id, "gpt-4")
    assert record.model_name == "gpt-4"
    stored = await store.get(record.run_id)
    assert stored["model_name"] == "gpt-4"


@pytest.mark.anyio
async def test_cancel_unknown_run():
    """cancel for unknown run reports the run is not active locally."""
    mgr = RunManager()
    result = await mgr.cancel("nonexistent")
    assert result is CancelOutcome.not_active_locally


@pytest.mark.anyio
async def test_cancel_already_interrupted():
    """cancel for already-interrupted run is idempotent."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    await mgr.set_status(record.run_id, RunStatus.running)
    await mgr.cancel(record.run_id)
    assert record.status == RunStatus.interrupted

    # Second cancel should be idempotent
    result = await mgr.cancel(record.run_id)
    assert result is CancelOutcome.cancelled


@pytest.mark.anyio
async def test_cancel_with_active_task():
    """cancel calls task.cancel() when task is not done (line 490)."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    await mgr.set_status(record.run_id, RunStatus.running)

    task_started = asyncio.Event()

    async def dummy_coro():
        task_started.set()
        while True:
            await asyncio.sleep(1)

    task = asyncio.create_task(dummy_coro())
    await task_started.wait()
    record.task = task

    result = await mgr.cancel(record.run_id)
    assert result is CancelOutcome.cancelled
    # task.cancel() was called; the task should be in cancelling state
    assert task.cancelling() > 0

    # Cleanup
    task.uncancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.anyio
async def test_cancel_pending_run():
    """cancel on a pending (not yet running) run should work."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    result = await mgr.cancel(record.run_id)
    assert result is CancelOutcome.cancelled
    assert record.status == RunStatus.interrupted


@pytest.mark.anyio
async def test_create_or_reject_unsupported_strategy():
    """create_or_reject with unsupported strategy raises (line 525)."""
    mgr = RunManager()
    with pytest.raises(UnsupportedStrategyError, match="not yet supported"):
        await mgr.create_or_reject("thread-1", multitask_strategy="invalid_strategy")


@pytest.mark.anyio
async def test_create_or_reject_reject_with_inflight():
    """create_or_reject with reject strategy and inflight run raises ConflictError (line 530)."""
    mgr = RunManager()
    await mgr.create("thread-1")

    with pytest.raises(ConflictError, match="already has an active run"):
        await mgr.create_or_reject("thread-1", multitask_strategy="reject")


@pytest.mark.anyio
async def test_create_or_reject_interrupt_with_active_task():
    """create_or_reject interrupt calls task.cancel() on inflight runs (line 571)."""
    mgr = RunManager()
    old = await mgr.create("thread-1")
    await mgr.set_status(old.run_id, RunStatus.running)

    task_started = asyncio.Event()

    async def dummy_coro():
        task_started.set()
        while True:
            await asyncio.sleep(1)

    task = asyncio.create_task(dummy_coro())
    await task_started.wait()
    old.task = task

    await mgr.create_or_reject("thread-1", multitask_strategy="interrupt")
    assert old.status == RunStatus.interrupted
    assert task.cancelling() > 0

    # Cleanup
    task.uncancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.anyio
async def test_create_or_reject_rollback_no_inflight():
    """create_or_reject with rollback and no inflight runs creates normally."""
    mgr = RunManager()
    record = await mgr.create_or_reject("thread-1", multitask_strategy="rollback")
    assert record.status == RunStatus.pending


@pytest.mark.anyio
async def test_reconcile_no_store():
    """reconcile_orphaned_inflight_runs returns [] when no store (line 597)."""
    mgr = RunManager()
    result = await mgr.reconcile_orphaned_inflight_runs(error="test")
    assert result == []


@pytest.mark.anyio
async def test_reconcile_list_inflight_exception():
    """reconcile_orphaned_inflight_runs handles list_inflight exceptions (lines 604-606)."""
    from unittest.mock import AsyncMock

    store = MemoryRunStore()
    store.list_inflight = AsyncMock(side_effect=RuntimeError("db error"))
    mgr = RunManager(store=store)
    result = await mgr.reconcile_orphaned_inflight_runs(error="test")
    assert result == []


@pytest.mark.anyio
async def test_reconcile_record_from_store_exception():
    """reconcile skips rows that fail _record_from_store (lines 613-615)."""
    from unittest.mock import patch

    store = MemoryRunStore()
    await store.put("bad-row", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")
    await store.put("good-row", thread_id="thread-1", status="pending", created_at="2026-01-01T00:00:01+00:00")
    mgr = RunManager(store=store)

    original_from_store = RunManager._record_from_store

    def selective_fail(row):
        if row.get("run_id") == "bad-row":
            raise ValueError("bad row")
        return original_from_store(row)

    with patch.object(RunManager, "_record_from_store", side_effect=selective_fail):
        recovered = await mgr.reconcile_orphaned_inflight_runs(error="test")

    recovered_ids = [r.run_id for r in recovered]
    assert "bad-row" not in recovered_ids
    assert "good-row" in recovered_ids


@pytest.mark.anyio
async def test_reconcile_no_orphans_found():
    """reconcile returns [] when list_inflight returns empty list."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    result = await mgr.reconcile_orphaned_inflight_runs(error="test")
    assert result == []


@pytest.mark.anyio
async def test_cleanup_with_delay():
    """cleanup with positive delay should sleep before removing (line 643).

    Upstream evicts only when a RunStore backs the manager, so this uses one.
    """
    mgr = RunManager(store=MemoryRunStore())
    record = await mgr.create("thread-1")
    run_id = record.run_id

    cleanup_task = asyncio.create_task(mgr.cleanup(run_id, delay=0.05))
    # Should still exist immediately
    assert run_id in mgr._runs
    await cleanup_task
    assert run_id not in mgr._runs


def test_retryable_error_with_chained_cause():
    """Exception with __cause__ that has retryable message."""
    inner = sqlite3.OperationalError("database is locked")
    outer = RuntimeError("wrapper")
    outer.__cause__ = inner
    assert _is_retryable_persistence_error(outer) is True


def test_retryable_error_with_orig():
    """Exception with .orig attribute that has retryable message."""
    inner = RuntimeError("database is locked")
    outer = RuntimeError("wrapper")
    outer.orig = inner
    assert _is_retryable_persistence_error(outer) is True


def test_retryable_error_deeply_nested():
    """Retryable error buried deep in chain should be found."""
    level3 = RuntimeError("database is locked")
    level2 = RuntimeError("mid")
    level2.__context__ = level3
    level1 = RuntimeError("top")
    level1.__context__ = level2
    assert _is_retryable_persistence_error(level1) is True


@pytest.mark.anyio
async def test_update_run_completion_all_fields():
    """update_run_completion should update all token-related fields."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    await mgr.update_run_completion(
        record.run_id,
        status="success",
        total_input_tokens=100,
        total_output_tokens=50,
        total_tokens=150,
        llm_call_count=3,
        lead_agent_tokens=80,
        subagent_tokens=40,
        middleware_tokens=30,
        message_count=5,
        last_ai_message="done",
        first_human_message="hello",
    )
    assert record.total_input_tokens == 100
    assert record.total_output_tokens == 50
    assert record.total_tokens == 150
    assert record.llm_call_count == 3
    assert record.lead_agent_tokens == 80
    assert record.subagent_tokens == 40
    assert record.middleware_tokens == 30
    assert record.message_count == 5
    assert record.last_ai_message == "done"
    assert record.first_human_message == "hello"


@pytest.mark.anyio
async def test_update_run_progress_all_fields():
    """update_run_progress should update all token-related fields."""
    store = MemoryRunStore()
    mgr = RunManager(store=store)
    record = await mgr.create("thread-1")
    await mgr.set_status(record.run_id, RunStatus.running)

    await mgr.update_run_progress(
        record.run_id,
        total_input_tokens=100,
        total_output_tokens=50,
        total_tokens=150,
        llm_call_count=3,
        lead_agent_tokens=80,
        subagent_tokens=40,
        middleware_tokens=30,
        message_count=5,
        last_ai_message="hello",
        first_human_message="hi",
    )
    assert record.total_input_tokens == 100
    assert record.total_output_tokens == 50
    assert record.total_tokens == 150
    assert record.llm_call_count == 3
    assert record.lead_agent_tokens == 80
    assert record.subagent_tokens == 40
    assert record.middleware_tokens == 30
    assert record.message_count == 5
    assert record.last_ai_message == "hello"
    assert record.first_human_message == "hi"


@pytest.mark.anyio
async def test_create_or_reject_interrupt_logs_cancellation_count():
    """Interrupt strategy logs the count of inflight runs to cancel."""
    mgr = RunManager()
    r1 = await mgr.create("thread-1")
    r1.status = RunStatus.running
    r2 = await mgr.create("thread-1")
    r2.status = RunStatus.running

    new = await mgr.create_or_reject("thread-1", multitask_strategy="interrupt")
    assert r1.status == RunStatus.interrupted
    assert r2.status == RunStatus.interrupted
    assert new.status == RunStatus.pending


@pytest.mark.anyio
async def test_create_or_reject_rollback_with_task():
    """rollback strategy calls task.cancel() on inflight runs."""
    mgr = RunManager()
    old = await mgr.create("thread-1")
    await mgr.set_status(old.run_id, RunStatus.running)

    task_started = asyncio.Event()

    async def dummy_coro():
        task_started.set()
        while True:
            await asyncio.sleep(1)

    task = asyncio.create_task(dummy_coro())
    await task_started.wait()
    old.task = task

    await mgr.create_or_reject("thread-1", multitask_strategy="rollback")
    assert old.status == RunStatus.interrupted
    assert old.abort_action == "rollback"
    assert task.cancelling() > 0

    task.uncancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.anyio
async def test_reconcile_persist_status_non_retryable_failure():
    """reconcile skips rows when the takeover claim fails with a non-retryable error."""

    store = MemoryRunStore()
    await store.put("run-1", thread_id="thread-1", status="running", created_at="2026-01-01T00:00:00+00:00")

    call_count = 0

    async def failing_claim(run_id, *, grace_seconds, error, stop_reason=None):
        nonlocal call_count
        call_count += 1
        raise ValueError("permanent failure")

    store.claim_for_takeover = failing_claim
    mgr = RunManager(store=store)
    result = await mgr.reconcile_orphaned_inflight_runs(error="test")
    assert result == []
    assert call_count == 1


@pytest.mark.anyio
async def test_update_run_progress_ignores_unknown_attrs():
    """update_run_progress should skip kwargs that aren't record attributes."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    record.status = RunStatus.running
    await mgr.update_run_progress(record.run_id, unknown_field="val")
    assert not hasattr(record, "unknown_field")


@pytest.mark.anyio
async def test_update_run_completion_skips_status_in_record_update():
    """update_run_completion should not change record.status via setattr."""
    mgr = RunManager()
    record = await mgr.create("thread-1")
    assert record.status == RunStatus.pending
    await mgr.update_run_completion(record.run_id, status="success", total_tokens=10)
    # status should remain pending (the status key is skipped in the setattr loop)
    assert record.status == RunStatus.pending
    assert record.total_tokens == 10
