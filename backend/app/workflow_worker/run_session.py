"""Run sessions: execute a claimed task, or resume a paused run.

``execute`` is the queue entry for one claimed task; ``resume`` is the
operator-command entry and owns the fork-interrupt recovery protocol (a plain
operator payload becomes an id-keyed resume map, one pending interrupt per
invocation). Both entries share the graph-driving session below; the fused
``execute_workflow_task`` from the pre-package module stays importable as an
alias of ``execute``.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, contextmanager
from typing import Any

import yaml
from langgraph.types import Command

from app.agentplatform.resources.canonical_sandbox import (
    canonical_sandbox_scope,
)
from app.agentplatform.workflow_runtime import (
    WorkflowCancelled,
    WorkflowGraphCompiler,
    WorkflowInvalidRootsError,
    WorkflowMissingInputRootsError,
    WorkflowPaused,
    WorkflowRunError,
    WorkflowV2Store,
    enforce_result_contract,
    make_host_resolver,
    parse_workflow_v2,
    run_failure_payload,
    validate_read_roots,
    validate_workflow_roots,
    workflow_snapshot,
)
from deerflow.persistence.models.workflow_v2 import WorkflowTaskRow
from deerflow.runtime.checkpointer.async_provider import make_checkpointer

from .registry import build_canonical_registry


@contextmanager
def _workflow_run_evidence_context(run: Any, receipt_archiver: Callable[[dict], Any] | None = None):
    """Bind persisted canonical Run Evidence while the graph is executing."""

    from agentplatform_extension.evidence import (
        AuthorizationContext,
        RunEvidenceBinding,
        bind_receipt_archiver,
        bind_run_evidence,
    )

    snapshot = run.snapshot if isinstance(run.snapshot, dict) else {}
    evidence = snapshot.get("run_evidence")
    if not isinstance(evidence, dict):
        yield
        return
    authorization = evidence.get("authorization_context")
    if not isinstance(authorization, dict):
        yield
        return
    binding = RunEvidenceBinding(
        snapshots=tuple(evidence.get("resource_snapshots", ())),
        authorization=AuthorizationContext(
            caller_user_id=str(authorization.get("caller_user_id", run.created_by)),
            effective_agent_id=str(authorization.get("effective_agent_id", run.workflow_resource_id or run.workflow_name)),
            policy_revision=str(
                authorization.get(
                    "policy_revision",
                    evidence.get("policy_revision", "runtime-default"),
                )
            ),
            allowed_tools=tuple(str(value) for value in authorization.get("allowed_tools", ())),
            memory_scope=str(authorization.get("memory_scope", run.created_by)),
        ),
        runtime_assembly_fingerprint=evidence.get("runtime_assembly_fingerprint"),
        trace_id=evidence.get("trace_id"),
        retrieval_receipts=tuple(evidence.get("retrieval_receipts", ())),
        run_id=str(getattr(run, "run_id", "")) or None,
        knowledge_scope=evidence.get("knowledge_scope") if isinstance(evidence.get("knowledge_scope"), dict) else None,
    )
    with bind_run_evidence(binding), bind_receipt_archiver(receipt_archiver):
        yield


async def load_workflow_definition_for_run(run: Any, store: Any, session_factory: Any, storage: Any) -> dict:
    """Load canonical Runs by frozen UUID; retain name/version for legacy Runs."""

    workflow_resource_id = getattr(run, "workflow_resource_id", None)
    if workflow_resource_id:
        if session_factory is None or storage is None:
            raise RuntimeError("canonical workflow run requires catalog persistence and storage")
        from app.agentplatform.resource_runtime import CanonicalResourceLoader

        async with session_factory() as session:
            frozen = await CanonicalResourceLoader(session, storage).load_workflow(run.run_id, workflow_resource_id)
            return frozen.content
    version = await store.get_definition(run.workflow_name, run.definition_version)
    if version is None:
        raise RuntimeError(f"workflow definition {run.workflow_name}@{run.definition_version} not found")
    return version.definition


async def _pending_interrupt_ids(
    config: Any,
    *,
    thread_id: str,
    checkpointer_factory: Callable[[Any], AbstractAsyncContextManager[Any]] = make_checkpointer,
) -> list[str]:
    """Collect pending langgraph interrupt ids for a paused run.

    The workflow store snapshot renders interrupt payloads without their
    langgraph ids, but a fork where several branches pause on
    ``artifacts_missing`` simultaneously leaves multiple pending interrupts
    that can only be resumed through an id-keyed resume map.
    """

    ids: list[str] = []
    async with checkpointer_factory(config) as checkpointer:
        tup = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    for write in (tup.pending_writes if tup else None) or []:
        if write[1] != "__interrupt__":
            continue
        entries = write[2] if isinstance(write[2], list) else [write[2]]
        for entry in entries:
            interrupt_id = getattr(entry, "id", None)
            if isinstance(interrupt_id, str) and interrupt_id:
                ids.append(interrupt_id)
    return ids


async def _session_assembly(run: Any, store: WorkflowV2Store, config: Any, adapters: Any | None) -> tuple[Any, Any]:
    """Resolve the frozen definition and the adapter registry for one session.

    Resource storage is needed by every canonical-registry build (the frozen
    run skill view is written for any snapshot carrying skills, PATCH-012),
    so construct it unconditionally — legacy name/version runs included.
    """
    from app.agentplatform.resource_runtime import ResourceStorage
    from deerflow.config.paths import get_paths

    storage = ResourceStorage(get_paths().base_dir)
    definition_payload = await load_workflow_definition_for_run(
        run,
        store,
        getattr(store, "session_factory", None),
        storage,
    )
    definition = parse_workflow_v2(yaml.safe_dump(definition_payload))
    registry = (
        adapters
        if adapters is not None
        else await build_canonical_registry(
            run,
            config,
            getattr(store, "session_factory", None),
            storage,
        )
    )
    return definition, registry


async def execute(
    task: WorkflowTaskRow,
    *,
    store: WorkflowV2Store,
    config: Any,
    checkpointer_factory: Callable[[Any], AbstractAsyncContextManager[Any]] = make_checkpointer,
    adapters: Any | None = None,
) -> None:
    """Execute one claimed task through the production graph and event chain.

    A task carrying a resume command delegates to :func:`resume`; ``adapters``
    lets embedded drivers supply the action registry directly (tests drive the
    same seam with a stubbed agent) instead of mocking the registry builder.
    """
    run = await store.get_run(task.run_id)
    if run is None:
        raise RuntimeError(f"workflow run '{task.run_id}' not found")
    if task.resume_command_id is not None:
        command = await store.get_command(task.resume_command_id)
        if command is None:
            raise RuntimeError(f"workflow task '{task.task_id}' has no resume command")
        await resume(
            run,
            command,
            task=task,
            store=store,
            config=config,
            checkpointer_factory=checkpointer_factory,
            adapters=adapters,
        )
        return
    definition, registry = await _session_assembly(run, store, config, adapters)
    evidence = run.snapshot.get("run_evidence", {}) if isinstance(run.snapshot, dict) else {}
    invocation = {
        "run_id": task.run_id,
        "inputs": run.inputs,
        "state": {},
        "outputs": {},
        "model_name": run.model_name,
        "knowledge_scope": evidence.get("knowledge_scope"),
    }
    await _drive_session(
        run,
        invocation,
        resumed=False,
        task=task,
        store=store,
        config=config,
        definition=definition,
        adapters=registry,
        checkpointer_factory=checkpointer_factory,
    )


async def resume(
    run: Any,
    command: Any,
    *,
    task: WorkflowTaskRow | None = None,
    store: WorkflowV2Store,
    config: Any,
    checkpointer_factory: Callable[[Any], AbstractAsyncContextManager[Any]] = make_checkpointer,
    adapters: Any | None = None,
) -> None:
    """Resume a paused run through an operator command.

    Carries the fork-interrupt recovery protocol: LangGraph treats an empty
    dict as a resume map with no entries, and a fork can leave several
    branches pending at once where only an id-keyed resume map is accepted.
    The entry normalizes a payload-less resume, keys the payload by the first
    pending interrupt id, and confirms one interrupt per invocation — the next
    invocation resumes the next pending branch. ``task`` attributes the
    session's events and snapshot writes to the claimed lease when the queue
    drives the resume.
    """
    definition, registry = await _session_assembly(run, store, config, adapters)
    # LangGraph treats an empty dict as a resume map with no entries, so a
    # payload-less resume would never deliver a value and the interrupt gate
    # would re-raise on every attempt. Normalize to an explicit value.
    resume_value = command.payload if command.payload else {"resumed": True}
    thread_id = getattr(run, "checkpoint_thread_id", None) or f"wf-{run.run_id}"
    pending = await _pending_interrupt_ids(config, thread_id=thread_id, checkpointer_factory=checkpointer_factory)
    if pending:
        # A fork can pause on artifacts_missing in several branches at once;
        # langgraph then only accepts an id-keyed resume map, and resuming
        # every branch in one step can collide with their pending writes —
        # so confirm one interrupt per invocation.
        resume_value = {pending[0]: resume_value}
    # Intake confirmations can pause a run before the graph has created a
    # checkpoint.  Carry the immutable run inputs into the resume command
    # so the first graph node can still render file-access and prompt
    # templates.  For an ordinary in-graph interrupt these fields merge
    # harmlessly with the existing checkpoint state.
    invocation = Command(
        update={
            "run_id": run.run_id,
            "inputs": run.inputs,
            "model_name": run.model_name,
        },
        resume=resume_value,
    )
    if task is not None:
        # Consume the resume command only once the invocation is built, just
        # before the graph drives: the attempt-budget exemption applies to the
        # immediate resume only, and a later crash/take-over must count as a
        # fresh attempt again.
        await store.clear_resume_command(task.task_id)
    await _drive_session(
        run,
        invocation,
        resumed=True,
        task=task,
        store=store,
        config=config,
        definition=definition,
        adapters=registry,
        checkpointer_factory=checkpointer_factory,
    )


async def _drive_session(
    run: Any,
    invocation: Any,
    *,
    resumed: bool,
    task: WorkflowTaskRow | None,
    store: WorkflowV2Store,
    config: Any,
    definition: Any,
    adapters: Any,
    checkpointer_factory: Callable[[Any], AbstractAsyncContextManager[Any]] = make_checkpointer,
) -> None:
    """Drive one compiled graph invocation and persist its lifecycle."""
    run_id = run.run_id
    sandbox_scope = canonical_sandbox_scope(run_id, run_id)
    worker_id = getattr(task, "lease_owner", None)
    event_limit = config.workflow_runtime.max_events_per_run

    async def emit_event(event_type: str, payload: dict) -> None:
        event = await store.append_event(
            run_id,
            event_type,
            payload,
            worker_id=worker_id,
            max_events=event_limit - 1,
        )
        if event is None:
            raise WorkflowRunError(
                "event_limit",
                "工作流执行失败：事件数量已达上限",
                detail="workflow_event_limit_exceeded",
            )

    async def emit_terminal_event(event_type: str, payload: dict) -> None:
        await store.append_event(
            run_id,
            event_type,
            payload,
            worker_id=worker_id,
            max_events=event_limit,
        )

    async def archive_retrieval_receipt(receipt: dict) -> bool:
        """Persist each receipt while the worker still owns the run lease."""
        current = run.snapshot if isinstance(run.snapshot, dict) else {}
        evidence = current.get("run_evidence") if isinstance(current.get("run_evidence"), dict) else {}
        receipts = list(evidence.get("retrieval_receipts", ()))
        replaced = False
        for index, existing in enumerate(receipts):
            if isinstance(existing, dict) and existing.get("receipt_id") == receipt.get("receipt_id"):
                receipts[index] = receipt
                replaced = True
                break
        if not replaced:
            receipts.append(receipt)
        snapshot = {
            **current,
            "run_evidence": {**evidence, "retrieval_receipts": receipts},
        }
        if not await store.update_snapshot(run_id, snapshot, worker_id=worker_id):
            return False
        run.snapshot = snapshot
        return True

    runtime_evidence = None
    with _workflow_run_evidence_context(run, archive_retrieval_receipt):
        async with checkpointer_factory(config) as checkpointer:
            graph = WorkflowGraphCompiler(
                definition,
                adapters,
                emit_event=emit_event,
                is_cancelled=lambda: store.is_cancel_requested(run_id),
                node_timeout_seconds=config.workflow_runtime.node_timeout_seconds,
                artifact_resolver=make_host_resolver(run_id, run.created_by, sandbox_scope=sandbox_scope),
            ).compile(checkpointer=checkpointer)
            try:
                invalid_roots = validate_workflow_roots(definition.nodes, run.inputs)
                if invalid_roots:
                    raise WorkflowInvalidRootsError(invalid_roots)
                missing_read_roots = validate_read_roots(
                    definition.nodes,
                    run.inputs,
                    make_host_resolver(run_id, run.created_by, sandbox_scope=sandbox_scope),
                )
                if missing_read_roots:
                    raise WorkflowMissingInputRootsError(missing_read_roots)
                await emit_event(
                    "resumed" if resumed else "run_started",
                    {"definition_version": run.definition_version},
                )
                result = await graph.ainvoke(
                    invocation,
                    config={
                        "configurable": {"thread_id": run.checkpoint_thread_id},
                        "max_concurrency": config.workflow_runtime.max_parallel_actions,
                    },
                )
            except WorkflowCancelled as exc:
                await emit_terminal_event("run_cancelled", {"error": str(exc)})
                raise
            except Exception as exc:
                await emit_terminal_event("run_failed", run_failure_payload(exc))
                raise
        from agentplatform_extension.evidence import current_run_evidence

        binding = current_run_evidence()
        if binding is not None:
            runtime_evidence = binding.as_mapping()
    snapshot = workflow_snapshot(result)
    if runtime_evidence is not None:
        snapshot["run_evidence"] = runtime_evidence
    if not await store.update_snapshot(run_id, snapshot, worker_id=worker_id):
        return
    if "__interrupt__" in result:
        await emit_event("interrupted", {"value": snapshot["interrupt"]})
        raise WorkflowPaused
    # Declared Result Contract gate (unified-kernel ticket 01): after the graph
    # succeeds and before the terminal state is written, the run's declared
    # validator judges the artifacts.  A violation (or a broken validator,
    # fail-closed) ends the run as failed; artifacts are never cleaned up here.
    # The validator judges the persisted run snapshot — the store's recovery
    # merge keeps the kernel-pinned keys (intake record, contract version,
    # entry, unified-kernel ticket 03) that the graph result never carries —
    # and may emit opaque (event_type, payload) audit events (e.g. the shared
    # kernel's contract judgment); the engine only shuttles them into the
    # event log ahead of the terminal event.
    persisted = await store.get_run(run_id)
    persisted_snapshot = persisted.snapshot if persisted is not None and isinstance(persisted.snapshot, dict) and persisted.snapshot else snapshot
    validator_events: list[tuple[str, dict]] = []
    violation = enforce_result_contract(
        definition,
        run_inputs=run.inputs or {},
        run_snapshot=persisted_snapshot,
        resolver=make_host_resolver(run_id, run.created_by, sandbox_scope=sandbox_scope),
        emit_event=lambda event_type, payload: validator_events.append((event_type, payload)),
    )
    for event_type, payload in validator_events:
        await emit_event(event_type, payload)
    if violation is not None:
        await emit_terminal_event("run_failed", run_failure_payload(violation))
        raise violation
    await emit_terminal_event("run_completed", {})


# Backward-compatible name: the pre-package module exposed the queue-task
# entry under this name (scripts and tests still import it).
execute_workflow_task = execute
