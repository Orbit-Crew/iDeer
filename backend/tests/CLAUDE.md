# Backend Tests

Backend tests must preserve the runtime invariants they exercise without changing production execution topology.

## Executor starvation tests

`test_executor_starvation.py` covers the deterministic starvation semantics from RFC #4560:

- default-executor saturation and queueing;
- cancellation of an awaiter while an already-started synchronous worker continues;
- isolation between the asyncio default executor and DeerFlow's dedicated file-I/O executor.

Use explicit synchronization such as `threading.Event` rather than sleep-based timing thresholds for worker lifecycle assertions. Every test must release blocked workers and restore any process-global monkeypatches so teardown cannot leak threads or state into later tests.

Stress/soak testing, AnyIO worker instrumentation, Uvicorn multi-process behavior, and broad production executor redesign are separate concerns and should not be folded into these deterministic regressions.

## Run-scoped paths in integration tests

Resolve run-scoped filesystem locations through the run's own sandbox scope — `make_host_resolver(run.run_id, str(run.created_by), sandbox_scope=canonical_sandbox_scope(run.run_id, run.run_id))("/mnt/user-data/...")` — the same seam `_outputs_host` uses. Run ids and thread ids are distinct identities (run incarnations); never reuse an id in a thread-path constructor such as `sandbox_uploads_dir(<run_id>)`.
