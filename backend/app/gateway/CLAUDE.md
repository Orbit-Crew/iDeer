### Gateway API (`app/gateway/`)

`conversation_access.py` binds an opt-in read-only tool to a run request's
explicit `conversation_references` and effective `runs:read` permission; never
derive grants from message contents or checkpoints. The callback travels
through `RunContext`, not serialized config; `conversation_reader.py` shares
the HTTP transcript visibility/pagination logic without a Request dependency —
ownership remains a caller responsibility — and excludes non-text/internal
content. `RunCreateRequest` also accepts the list as
`context.conversation_references`: a before-validator lifts it into the
top-level field and drops it from `context`, so
`merge_run_context_overrides` never sees it; sending both is a 422.
`conversation_references_enabled()` is the one "tool is configured"
predicate, used by admission and by `/api/features`.

FastAPI listens on port 8001; health: `GET /health` (liveness) and
`GET /health/ready` (readiness; probes the ORM engine and the effective
LangGraph checkpointer/Store backend, 503 while either is unreachable —
probe mechanics: [backend development
reference](../../docs/development-reference.md#gateway-api-appgateway)). Set
`GATEWAY_ENABLE_DOCS=false` to disable the default `/docs`, `/redoc`, and
`/openapi.json` endpoints.

`build_run_config()` resolves the default LangGraph super-step budget from the
hot-reloaded top-level `recursion_limit` setting. A valid request-level value
takes precedence; invalid values fall back to that default, and
`max_recursion_limit` caps both sources.

Durable MCP notifications use internal Agent runs. Keep their trusted delivery
instruction outside the user-input boundary, and frame serialized remote events
as untrusted before model invocation. Strict thread existence/ownership
admission dead-letters events whose task outlives its deleted chat instead of
recreating the thread.

CORS is same-origin by default behind nginx on port 2026. Split-origin or
port-forwarded browser clients must opt in with `GATEWAY_CORS_ORIGINS` (exact
origins); `CORSMiddleware` and `CSRFMiddleware` both read it so browser CORS
and auth-origin checks stay aligned. Those clients also need
`CORS_EXPOSED_HEADERS` (`csrf_middleware.py`): run-creating routes return the
run's id in `Content-Location`, which the LangGraph SDK alone uses to resolve
run metadata.

Browser auth sessions are owned by `app.gateway.auth.session_cookie`; the
Gateway never stores passwords. `SessionCookiePolicy` persists the `HttpOnly
access_token` cookie only for HTTPS/trusted-forwarded HTTPS, direct-host
localhost HTTP, or explicit operator opt-in for insecure persistence; public
HTTP sandbox URLs degrade to session cookies. Session-creating handlers stamp
the final `max_age` on `request.state`; CSRF cookie creation mirrors it so the
double-submit pair expires together (including re-issue after password changes
and OIDC callbacks). An `HttpOnly` preference cookie preserves the remember
choice across re-issues. Logout clears all auth cookies and suppresses CSRF
re-issue.

Personal Access Tokens (`app.gateway.auth.pat`, `Authorization: Bearer dfp_...`)
run as their owning user: an invalid Bearer is a hard 401 with no cookie
fallback, which keeps `CSRFMiddleware`'s Bearer skip safe (origin checks still
run). Scopes narrow within the allowlisted threads/runs/projects routes
(including `POST /api/threads/{id}/move`); every other authenticated route 403s
PAT callers (admin included). PAT management and `/change-password` require
session auth; only SHA-256 digests are stored (`0017`).

Thread→project membership is written by thread creation (`POST /api/threads`
with a validated `project_id`), branch creation (the new row inherits the
source thread's project; an archived/deleted project degrades the branch to
unassigned), and explicit moves (`POST /api/threads/{id}/move`); run admission
never modifies membership, it only pins the resolved project context read-only
into the run context. The server-reserved `deerflow_project_id` metadata key
is a read-only exposure of `threads_meta.project_id`, stripped from client
writes.

Localhost persistence deliberately reads the direct request `Host` and ignores
`Forwarded` / `X-Forwarded-Host`. Scheme and auth-origin reconstruction still
consume forwarding headers. The bundled nginx preserves an upstream HTTPS value
and does not overwrite every forwarded header, so the outer trusted proxy must
replace or strip client-supplied forwarding headers before traffic reaches
DeerFlow.

Standalone local LangGraph Studio is recognized only through the upstream
`Auth.types.StudioUser` principal type, never its reusable identity string
(older SDKs degrade to normal owner scoping). For that
principal's assistant reads/searches, `langgraph_auth.add_owner_filter` selects
genuine server-registered assistants plus Studio-owned ones; all other
resources remain owner-scoped. Assistant create/update handlers make both
`user_id` and `created_by=user` server-owned. `langgraph_studio.py` must
complete its legacy system-assistant sanitization at the pre-runtime import
boundary — before runtime 0.30.0 loads and purges system-marked rows. The
procedure, its no-op/fail-closed modes, and the loader annotation constraint
are in the [backend development
reference](../../docs/development-reference.md#langgraph-studio-integration).
The harness requires in-memory runtime 0.30.0+; a persisted store missing the
expected registered assistant row emits a drift warning; keep the module's
annotations eager and preserve the direct file-loader regression test.

**Routers**: the authoritative endpoint inventory is the source under
`backend/app/gateway/routers/` — do not copy route lists into this guide.
Mechanics cited below ("mechanics reference"): [run delivery and stream
recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics).
Router-level contracts that survive:

- **Console** (`/api/console`): read-only cross-thread observability via a SQL
  reporting layer over `runs`/`threads_meta` (no new `RunStore` methods); 503
  on `database.backend: memory`. Real-cost estimation reads optional
  `models[*].pricing`, cache-aware; all priced models must use one currency —
  mixed currencies disable cost reporting (cost/currency fields null);
  unpriced models yield `cost: null`. Pricing plumbing: mechanics reference
  above.
- **MCP** (`/api/mcp`): validate expanded, save raw; reload/reset; invalid ->
  400.
- **MCP Tasks** (`/api/threads/{id}/mcp-tasks`): durable task detail for one
  owned thread is bounded and excludes remote task IDs and driver
  configuration.
- **Skills** (`/api/skills`): admin-only upload install is authorized before
  parsing and capped at a 100 MiB file plus 1 MiB framing; `POST /reload`
  invalidates the process-local cache after trusted filesystem changes.
- **Integrations** (`/api/integrations`): managed Lark/Feishu CLI integration;
  install is admin-only. Credential switches validate through the official
  CLI's live tenant-token probe, atomically revoke previous OAuth tokens, and
  restore the prior credential tree on failure; config/auth flows carry a
  server-issued per-user generation under the credential lock; stale
  completions return 409.
- **Uploads** (`/api/threads/{id}/uploads`): non-mounted sandbox sync uses a
  non-releasing request lease.
- **Threads** (`/api/threads/{id}`): branch creation follows [Branch workspace
  and history
  seeding](../../docs/THREAD_LIFECYCLE.md#branch-workspace-and-history-seeding);
  `POST /compact` summarizes older active context, deriving memory policy and
  bucket from the state-producing checkpoint rather than request `agent_name`,
  and blocks while a run is in flight; unexpected failures return a generic 500
  detail.
- **Artifacts** (`/api/threads/{id}/artifacts`): active content (`text/html`,
  `text/xml`, `application/xml`, `text/xsl`, any `+xml` type, `.skill`
  members) is always forced as a download attachment to reduce XSS risk. The
  outputs-only rule is `path_utils.resolve_outputs_confined_path`, shared with
  IM-channel attachment delivery: a percent-encoded `..` or a symlink planted
  in `outputs/` must not reach a sibling `uploads/` file. `PUT /{path}`
  atomically replaces an existing UTF-8 text file only when its expected
  SHA-256 still matches; active runs conflict; non-mounted providers get the
  same update under a request lease.
- **Input Polish** (`/api/input-polish`): a short authenticated `runs:create`
  LLM request sharing the non-graph one-shot path
  (`deerflow.utils.oneshot_llm.run_oneshot_llm`) with suggestions; it validates
  the same stripped view of the draft it sends to the model, never creates a
  LangGraph run, persists a message, or modifies thread state, and preserves
  literal `<think>` substrings in the rewrite
  (`strip_think_blocks(truncate_unclosed=False)`).
- **Thread Runs** (`/api/threads/{id}/runs`): before the first journaled run,
  seed an empty feed from a checkpoint so legacy checkpoint-only history keeps
  its order and visibility; skip absent checkpoints or populated feeds.
  `GET /{rid}/stream` hides action/wait (`POST` with `action` needs
  `runs:cancel`). Regenerate/edit-replay preparation
  follows [Regenerate and edit-replay
  preparation](../../docs/THREAD_LIFECYCLE.md#regenerate-and-edit-replay-preparation).
- **Runs** (`/api/runs`): `POST /stream` and `/wait` are stateless and require
  `runs:create`; an optional body `thread_id` is owner-checked.
  Scheduled-task create/update/resume/trigger also require `threads:write` on
  top of `runs:create`.
- **GitHub Webhooks** (`/api/webhooks/github`): authenticity is enforced by
  HMAC (`X-Hub-Signature-256` vs `GITHUB_WEBHOOK_SECRET`), so the route is
  exempt from auth + CSRF and mounted fail-closed — only when
  `GITHUB_WEBHOOK_SECRET` is set or dev opt-in
  `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1`. Recognized-event fan-out
  failures return 503 so the delivery stays recorded failed for redelivery;
  permanent conditions (channel disabled, unknown events, malformed payloads,
  unavailable service) return 200 skipped/handled.
- **GitHub event-driven agents**: custom agents declare a `github:` block in
  their `config.yaml`; webhook fan-out publishes one `InboundMessage` per
  matching binding to the channel bus, routed by `GitHubChannel` through
  `ChannelManager`; the response `dispatch` summarizes matched/fired/skipped.

Thread identifiers use the shared `deerflow.utils.thread_id` contract
`^[A-Za-z0-9_-]{1,64}$`. Caller-provided opaque IDs remain supported; UUIDs
are generated only for `None`; explicit empty strings fail validation. Gateway
creation and state-producing request boundaries, embedded-client entry points,
filesystem/upload/event-store consumers, scheduled launches, and the
standalone Provisioner enforce this before persistence or workspace
initialization. Route-addressable legacy IDs remain accepted by pure reads and
cleanup/control endpoints; deleting one best-effort removes metadata and
checkpoints but skips local filesystem cleanup, so the raw value is never
interpolated into a host path. New runs, workspace/sandbox operations, and
other state-producing mutations remain blocked.

**Message feed seq** (#4666): streaming `values` frames, `GET
/threads/{id}/state`, and `POST /threads/{id}/history` stamp serialized
messages with `additional_kwargs.deerflow_seq` so clients can place
checkpoint-kept messages against the paged feed; the REST reads resolve the
store via `threads.py::_optional_run_event_store` (a feed-less deployment
still reads threads), and `services.py::normalize_input` strips the
server-owned key from client input (#4380). Mechanism and identity rule:
`packages/harness/deerflow/runtime/AGENTS.md`.

**Workspace change review**: `packages/harness/deerflow/workspace_changes/`
captures pre-/post-run snapshots of the thread-owned `workspace` and `outputs`
directories and writes a `workspace_changes` event when changes exist. Uploads
are intentionally excluded. Internal process-feedback directories never count
as changes: `deerflow/constants.py` is the shared source of truth for excluded
dir names, and the configured `tool_output.storage_subdir` is threaded through
snapshot capture as an extra excluded dir name. Scan mechanics: mechanics
reference above.

**Run delivery receipts**: the worker derives delivery requirements from the
run's workspace snapshots (files created/modified under
`/mnt/user-data/outputs` minus internal process-feedback exclusions), never
from a client request option, and idempotently persists a run-scoped
`run.delivery` receipt before the terminal status; missing or unverifiable
`present_files` coverage downgrades the run to error; runs without changed
outputs keep ordinary chat behavior. Journal mechanics (callback attribution,
receipt idempotency and retries, orphan recovery):
`packages/harness/deerflow/runtime/AGENTS.md`. Multi-worker deployments
require `run_events.backend: db`; the startup gate rejects process-local
memory and JSONL event stores when `GATEWAY_WORKERS > 1`.

**RunManager / RunStore contract** (bullets citing "mechanics reference" point
to the link defined under Routers):
- LangGraph-compatible run requests validate their supported subset before
  creating a run. `runtime/stream_modes.py` is the shared backend contract for
  public stream modes: public `messages-tuple` maps to LangGraph's internal
  `messages` mode; public `messages`, `events`, and other unsupported modes
  are rejected, not dropped or replaced with `values`.
  `run_models.py::RunCreateRequest` is shared by HTTP and scheduled launch
  paths, retains only truthful compatibility defaults, returns 422 for
  unsupported values (`on_completion="complete"`, `on_completion="continue"`,
  `multitask_strategy="enqueue"`), and forbids undeclared SDK options so
  `checkpoint_during` and `durability` cannot be silently discarded. The
  boundary must still accept the stock SDK's default payload —
  `stream_resumable=False` is the SDK default and means the non-resumable
  behavior DeerFlow serves;
  `tests/unit/gateway/test_run_request_validation.py::test_gateway_accepts_langgraph_sdk_default_payload`
  pins it.
- `RunManager.get()` is async; direct callers must `await` it.
- The history batch helpers `list_successful_regenerate_sources()`,
  `list_edit_regenerate_runs()`, and `get_many_by_thread()` default to
  `user_id=AUTO`: they resolve the request user and fail closed when no user
  context exists. Migration/admin callers that intentionally need an unscoped
  read must pass `user_id=None` explicitly.
- Edit-and-rerun visibility derives from edit replay runs
  (`metadata.replay_kind="edit"` plus `regenerate_from_run_id`) via
  `RunManager.list_edit_replay_visibility()`: the newest attempt per source run
  is authoritative. Pending/running/success attempts hide the original source
  run; failed, timed-out, or interrupted attempts hide only the failed attempt
  so the original conversation reappears.
- When a persistent `RunStore` is configured, `get()` and `list_by_thread()`
  hydrate historical runs from the store. In-memory records win for the same
  `run_id` so task, abort, and stream-control state stays attached to active
  local runs.
- Thread metadata status switches to `running` only after
  `RunManager.try_start()` succeeds. Pending-cancelled runs therefore skip the
  old `running` projection.
- `cancel()` returns a :class:`~deerflow.runtime.CancelOutcome`:
  `cancelled` (local cancel), `requested` (a non-owning worker durably recorded
  the first cancellation action for the live owner), `taken_over` (non-owning
  worker claimed an expired lease — run marked `error`),
  `lease_valid_elsewhere` (store lacks the durable request primitive — safe
  409 + `Retry-After` fallback), `not_active_locally` (heartbeat disabled —
  old 409 path), `not_cancellable` (terminal state), `unknown` (not found).
  `create_or_reject(..., multitask_strategy="interrupt"|"rollback")` persists
  interrupted status through `RunStore.update_status()`, matching normal
  `set_status()` transitions.
- Interrupt/rollback admission registers the replacement before its best-effort
  persistence of locally interrupted predecessors; if the admitting caller is
  cancelled during that post-registration await, `RunManager` drains a shielded
  replacement cleanup before propagating `CancelledError`, including across
  repeated cancellation; a concurrent peer terminal transition wins and is
  synchronized back into the local record. Cleanup mechanics: mechanics
  reference above.
- Store-only hydrated runs are readable history. In multi-worker mode with
  heartbeat enabled, cancel on a store-only run records `runs.cancel_action` /
  `cancel_requested_at` while the owner's lease is live; the first action
  wins. `RunStore.request_cancel()` and
  owner completion through `finalize_if_not_cancelled()` are competing
  active-row CAS operations, so an accepted cancel cannot be overwritten by a
  later success; the owner runs the normal process-local interrupt/rollback
  and terminal stream path without transferring the lease.
  `wait=true` and cancel-then-stream use the shared bridge to observe owner
  finalization; a non-standard process-local bridge returns accepted 202. In
  single-worker mode (heartbeat off), store-only runs still return 409.
- A local worker's `RunRecord.lease_expires_at` is the last durably confirmed
  ownership deadline; `_renew_leases()` bounds each renewal attempt by it. An
  exception or blocked call that reaches expiry sets the process-local
  `ownership_lost` fence, raises `abort_event`, and cancels the run task.
  Fenced workers perform no subsequent journal/delivery-receipt,
  progress/completion/status, checkpoint/thread-metadata, or
  `on_run_completed` writes; the peer recovery path owns the terminal receipt.
  `RunStore.update_run_completion()` refuses to replace a different terminal
  status. `grace_seconds` delays peer reclamation for clock skew, not extra
  execution time. Renewal-signal and side-effect boundaries: mechanics
  reference above.
- Startup/orphan reconciliation must claim stale active rows with
  `RunStore.claim_for_takeover()`, not a plain `update_status()`. The final
  claim re-checks `status` and lease expiry atomically, so a heartbeat renewal
  between the candidate scan and the recovery write keeps the run active.
- Run admission and independent writes are first-class thread operations:
  `runs.operation_kind` distinguishes `run` from `checkpoint_write`,
  `artifact_write`, `artifact_archive`, `branch`, and `delete`; every active
  kind shares the durable active-thread uniqueness constraint. New operation
  kinds must go through `RunStore.create_thread_operation_atomic()` and
  `RunManager.reserve_thread_operation()`, not another lock or metadata
  marker. Reservations are excluded from run history/reporting and from
  run-only helpers (`list_by_thread()`, `has_inflight()`); release uses the
  captured owner rather than ambient user context.
  `RunStore.create_run_atomic()` stays a deprecated shim for stores that only
  admit normal runs; new stores must implement
  `create_thread_operation_atomic()`. Reservation interruption, lease-loss
  translation, and fail-closed boundaries: mechanics reference above.
- Gateway checkpoint mutations outside run execution must use
  `services.reserve_checkpoint_write()` (process-local thread lock + durable
  `checkpoint_write` reservation): manual compaction, `POST
  /threads/{id}/state`, and both goal mutation routes (`PUT` /
  `DELETE /threads/{id}/goal`, including creation of a missing goal
  checkpoint) use this boundary, so an existing run blocks the write and the
  reservation blocks new reject/interrupt/rollback runs across workers.
- Branch/state-update checkpoints copy only the source checkpoint's persisted
  `deerflow_agent_name`, never request metadata; missing or malformed bindings
  stay unbound so compaction fails closed.
- `DELETE /api/threads/{id}` holds a durable `delete` reservation for the whole
  cleanup and removes thread filesystem data, checkpoints, owner-scoped
  historical runs, run events, feedback and thread metadata best-effort.
  Historical-run cleanup removes only `operation_kind="run"` rows, so internal
  thread-operation rows — including the reservation protecting that request —
  stay durable until `RunManager.reserve_thread_operation()` exits. Preventing
  an already-admitted write from re-creating state for a deleted thread is a
  separate thread-incarnation contract, not part of this cleanup.
- `POST /wait` (both thread-scoped and `/api/runs/wait`) drains the stream
  bridge via `wait_for_run_completion()` instead of bare `await record.task`,
  so it honours the run's `on_disconnect` setting and cancels the background
  run on real client disconnect rather than returning a stale checkpoint
  (issue #3265).
- Memory and Redis `StreamBridge` implementations retain only
  `stream_bridge.queue_maxsize` data events. A syntactically valid
  `Last-Event-ID` older than the retained watermark, or a live subscriber that
  falls behind it, yields `StreamGap` before any partial replay;
  `sse_consumer` maps that to an id-less SSE `gap` payload
  (`stream_replay_gap`) and leaves the run active. Redis `StreamBridge` keys
  use a rolling retained-buffer TTL (`stream_bridge.stream_ttl_seconds`) as a
  leak safety net, not a run timeout. Provisional first-wake, numeric-cursor,
  and replay policies: mechanics reference above.
- Startup and lease-driven periodic orphan recovery share one Gateway
  stream-terminalization path: after `RunManager` durably marks a run `error`
  with `stop_reason=orphan_recovered`, Gateway publishes `END_SENTINEL` and
  schedules stream cleanup as one supervised single-flight task. Only startup
  recovery (before the runtime yields to requests) projects the latest affected
  thread to `error`; periodic recovery avoids that non-atomic projection
  (`ThreadMetaStore` has no `latest_run_id` conditional-update contract). The
  explicit `orphan_recovered` signal is the only heartbeat fallback — it
  supplies the liveness boundary if END publication fails or the retained key
  expires. Keep cross-component recovery orchestration in Gateway through the
  generic `RunManager.on_orphans_recovered` callback; no harness-to-app
  dependency. Orchestration detail: mechanics reference above.
- Thread-scoped run creation accepts an optional `Idempotency-Key` header on
  create, stream, and wait. Gateway hashes the caller key with the
  authenticated owner and `thread_id` before passing it to `RunManager`, whose
  persistence index is process-wide; never pass an unscoped external key to
  that index. The scoped key is shared across `/runs`, `/runs/stream`, and
  `/runs/wait`; a reuse whose stored `input` or `assistant_id` differs returns
  409. Reused `/wait` returns durable `status`/`error`, never the latest
  thread checkpoint. Missing headers keep ordinary non-idempotent admission;
  stateless `/api/runs/*` stays outside this contract (a thread-less request
  creates a fresh temporary thread before admission). Reuse capture, sticky
  `idempotency_reused`, SSE gap emission rules, and 409 matching: mechanics
  reference above.
- Thread-scoped run creation accepts `checkpoint` / `checkpoint_id`; Gateway
  validates the checkpoint belongs to the request thread before writing
  `checkpoint_id` / `checkpoint_ns` into `config.configurable` for LangGraph
  branching. In `delta` checkpoint mode the worker rewrites that fork into a
  linear head write before the graph starts (see "A delta-mode run cannot
  fork" under Checkpoint Channel Modes).
- Thread-scoped Gateway runs evaluate an active `ThreadState.goal` after the
  visible turn completes. `runtime/goal.py` asks a non-thinking evaluator model
  to judge only visible conversation evidence and return a typed blocker. Every
  non-satisfied evaluation is persisted with `last_evaluation`, but only
  `goal_not_met_yet` evaluations stream as hidden `HumanMessage` continuations,
  and only when the turn did not end on an unanswered Human Input Card
  (`ask_clarification` or the sandbox network prompt; the evaluator never sees
  those ToolMessages — such goals stand down with
  `blocker: "needs_user_input"` without calling it), a durable assistant
  end-of-turn checkpoint exists, the run was not aborted, has not hit its
  token-budget hard stop (`stop_reason == "token_capped"`), the thread did not
  change during evaluation, and the no-progress breaker has not fired. The
  continuation cap is 8 — a hard maximum; callers requesting more are clamped
  (`set_goal`/TUI) or rejected 422 (`PUT /goal`). The no-progress breaker keys
  on the latest visible assistant evidence (not the evaluator's free-text
  reason): two consecutive continuations adding no new visible assistant output
  stop the loop after 2 attempts. Evaluator creation/tracing: mechanics
  reference above. Model-response cleanup helpers (think-block/code-fence
  stripping) live in `deerflow.utils.llm_text`, shared by `runtime/goal.py`
  and Gateway suggestion parsing.
- Run event stream changes must keep producer code, `deerflow/constants.py`,
  `runtime/events/catalog.py`, `contracts/run_event_stream_contract.json`,
  `backend/docs/RUN_EVENT_STREAM.md`, and
  `tests/unit/runtime/test_run_event_stream_contract.py` in sync. The dependency-free
  constants module owns the persisted envelope limits (`event_type` 32
  characters, `category` 16) and cross-layer workspace event identity; the
  catalog owns validated runtime definitions and categories; the JSON contract
  owns payload schemas, backend-specific storage semantics, legacy aliases, and
  compatibility rules; conformance tests require both views and all producer
  groups to agree. Dynamic middleware tags are limited to 21 characters after
  the `middleware:` prefix. `run.end.content` remains opaque; consumers must
  not assume backend-identical nested output representations.

Proxied through nginx: `/api/langgraph/*` → Gateway LangGraph-compatible
runtime, all other `/api/*` → Gateway REST APIs.

**Thread lifecycle**: Before changing branching, regeneration, edit replay, or
archive/search behavior, read [Thread lifecycle
invariants](../../docs/THREAD_LIFECYCLE.md). It owns lineage and settled
-checkpoint rules, legacy fallback boundaries, archive filtering before
pagination, owner isolation, and activity-time preservation.
