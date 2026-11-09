# Workflow YAML v2

Workflow definitions are governed YAML graphs with `schema_version: 2`.
Definitions are parsed and validated by `app.agentplatform.workflows.v2.parser`, compiled
to LangGraph by `WorkflowGraphCompiler`, and executed by the durable worker.

Every saved definition creates an immutable version. Runs reference the exact
definition version and use `wf:{run_id}` as their checkpoint thread. The API
creates queued runs; the worker owns execution, checkpointing, events, and
terminal state.

The public lifecycle endpoints are:

- `POST /api/resources/{resource_id}/workflow-runs`
- `GET /api/resources/{resource_id}/workflow-runs/{run_id}`
- `GET /api/resources/{resource_id}/workflow-runs/{run_id}/events?after_seq=N`
- `POST /api/resources/{resource_id}/workflow-runs/{run_id}/commands`

Commands are idempotent and currently support `resume` and `cancel`.


Run detail and history snapshots expose `last_event_seq`, the durable event
sequence at the time of the snapshot. Viewers may replay from `after_seq=0`
to reconstruct node details, but must not close on a historical terminal event
before that watermark: a failed run may subsequently have been resumed and
completed. Resume and completion clear the previous run-level error; historical
failure events remain available in the timeline.
