"""Durable queue loop for the single workflow worker process."""

from __future__ import annotations

import asyncio
import os
from functools import partial

from app.agentplatform.resources.canonical_sandbox import (
    canonical_sandbox_scope,
)
from app.agentplatform.workflow_runtime import (
    RunRecordWriter,
    WorkflowV2Store,
    WorkflowWorker,
    make_host_resolver,
    workflow_log_root,
)
from deerflow.config import get_app_config
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)

from .run_session import execute


async def run_worker() -> None:
    config = get_app_config()
    if config.database.backend == "memory":
        raise RuntimeError("workflow-worker requires a durable database backend")
    await init_engine_from_config(config.database)
    sf = get_session_factory()
    if sf is None:
        raise RuntimeError("workflow-worker could not initialize persistence")
    store = WorkflowV2Store(sf)
    writers: dict[str, RunRecordWriter] = {}

    async def record_sink(run, event) -> None:
        writer = writers.get(run.run_id)
        if writer is None:
            writer = RunRecordWriter(
                make_host_resolver(
                    run.run_id,
                    str(run.created_by),
                    sandbox_scope=canonical_sandbox_scope(run.run_id, run.run_id),
                ),
                workflow_log_root(),
            )
            writers[run.run_id] = writer
        if event is not None:
            await writer.on_event(event)
        if run.status in {"completed", "failed", "cancelled"}:
            await writer.finalize(store, run)
            writers.pop(run.run_id, None)

    store.event_sink = record_sink

    try:
        runtime = config.workflow_runtime
        # Default to a per-process id: two workers on one machine must never
        # share the default lease owner, or they race to claim the same task.
        await WorkflowWorker(
            store,
            partial(execute, store=store, config=config),
            os.getenv("WORKFLOW_WORKER_ID") or f"workflow-worker-{os.getpid()}",
            lease_seconds=runtime.lease_seconds,
            heartbeat_seconds=runtime.heartbeat_seconds,
            max_attempts=runtime.max_attempts,
        ).run_forever()
    finally:
        await close_engine()


def main() -> None:
    asyncio.run(run_worker())
