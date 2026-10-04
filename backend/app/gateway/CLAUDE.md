### Gateway API (`app/gateway/`)

`conversation_access.py` binds an opt-in read-only tool to a run request's
explicit `conversation_references` and effective `runs:read` permission. Never
derive grants from message contents or checkpoints. The callback travels through
`RunContext`, not serialized config; `conversation_reader.py` shares the
existing HTTP transcript visibility/pagination logic without a Request
dependency — ownership remains a caller responsibility — and excludes
non-text/internal content. `RunCreateRequest` also accepts the list as
`context.conversation_references` (LangGraph SDK clients cannot send top-level
extras): a before-validator lifts it into the top-level field, so bounds and
error locations are shared, and drops it from `context`, so
`merge_run_context_overrides` never sees it; sending both is a 422.
`conversation_references_enabled()` is the one "tool is configured" predicate,
used by admission and by `/api/features`.

FastAPI listens on port 8001; health: `GET /health` (liveness) and
`GET /health/ready` (readiness; concurrently probes the ORM engine behind
`database:` plus the effective LangGraph checkpointer/Store backend — the legacy
`checkpointer:` section, otherwise derived from `database:`, resolved from the
startup config snapshot recorded on `app.state` — beneath a single bounded
deadline, with connection-opening probes serialized behind a strict per-process
gate; 503 while either is unreachable or the startup backend cannot be resolved,
`not_configured` for process-local backends such as `backend=memory`). Set
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

CORS is same-origin by default when requests enter through nginx on port 2026.
Split-origin or port-forwarded browser clients must opt in with
`GATEWAY_CORS_ORIGINS` (exact origins); Gateway `CORSMiddleware` and
`CSRFMiddleware` both read that variable so browser CORS and auth-origin checks
stay aligned. Those clients also need `CORS_EXPOSED_HEADERS`
(`csrf_middleware.py`): run-creating routes return the run's id in
`Content-Location`, which is not CORS-safelisted, and the LangGraph SDK resolves
run metadata from that header alone.

Browser auth sessions are owned by `app.gateway.auth.session_cookie`. Login
accepts a `remember_me` form flag, but the Gateway never stores passwords.
`SessionCookiePolicy` persists the `HttpOnly access_token` cookie only for
HTTPS/trusted-forwarded HTTPS, direct-host localhost HTTP, or explicit operator
opt-in for insecure persistence; public HTTP sandbox URLs degrade to session
cookies. Session-creating handlers stamp the final `max_age` on
`request.state`; CSRF cookie creation mirrors it so the double-submit pair
expires together, including re-issue after password changes and OIDC callbacks.
A small `HttpOnly` preference cookie preserves the remember choice across
re-issues. Logout clears all auth cookies and suppresses CSRF re-issue on the
logout response.

Personal Access Tokens (`app.gateway.auth.pat`, `Authorization: Bearer dfp_...`)
run as their owning user: an invalid Bearer is a hard 401 with no cookie
fallback, which keeps `CSRFMiddleware`'s Bearer skip safe (origin checks still
run). Scopes narrow within the allowlisted threads/runs/projects routes
(including `POST /api/threads/{id}/move`); every other authenticated route 403s
PAT callers (admin included). PAT management and `/change-password` require
session auth; only SHA-256 digests are stored (`0017`).

Thread→project membership is written by thread creation (`POST /api/threads`
with a validated `project_id`), branch creation (the new row inherits the source
thread's project; an archived/deleted project degrades the branch to unassigned
instead of failing), and explicit moves (`POST /api/threads/{id}/move`); run
admission never modifies membership, it only pins the resolved project context
read-only into the run context. The server-reserved `deerflow_project_id`
metadata key is a read-only exposure of the `threads_meta.project_id` column and
is stripped from client writes.

Localhost persistence deliberately reads the direct request `Host` and ignores
`Forwarded` / `X-Forwarded-Host`. Scheme and auth-origin reconstruction still
consume forwarding headers. The bundled nginx sets `X-Forwarded-Proto`, but
preserves an upstream HTTPS value and does not overwrite every forwarded header,
so the outer trusted proxy must replace or strip client-supplied forwarding
headers before traffic reaches DeerFlow.

Standalone local LangGraph Studio is recognized only through the upstream
`Auth.types.StudioUser` principal type, never by its reusable identity string
(an older SDK without it degrades to normal owner scoping). For that principal's
assistant reads/searches, `langgraph_auth.add_owner_filter` selects genuine
server-registered assistants plus assistants owned by Studio; all other
resources remain owner-scoped. Assistant create/update handlers make both
`user_id` and `created_by=user` server-owned, because LangGraph gives
`created_by=system` privileged ownership semantics during run creation.
`langgraph_studio.py` must complete its legacy system-assistant sanitization at
the pre-runtime import boundary — before runtime 0.30.0 loads and purges
system-marked rows; a user application lifespan is too late. The sanitization
procedure, its no-op/fail-closed modes, and the loader annotation constraint are
in the [backend development reference](../../docs/development-reference.md#langgraph-studio-integration).
The harness requires in-memory runtime 0.30.0 or newer; a persisted store
containing no expected registered assistant row emits a drift warning so changes
to LangGraph's internal persistence contract are observable; keep the module's
annotations eager (LangGraph executes the file-backed custom app without
registering it in `sys.modules`) and preserve the direct file-loader regression
test.

**Routers**:

| Router | Endpoints |
|--------|-----------|
| **Models** (`/api/models`) | `GET /` - list models; `GET /{name}` - model details |
| **Features** (`/api/features`) | `GET /` - UI capabilities: hot-reloaded agents, guarded browser, startup MCP tasks, separate batch repository/worker states so history stays readable without a worker, and `conversation_references` (whether `read_conversation` is configured, plus the per-run reference cap) |
| **Console** (`/api/console`) | Read-only cross-thread observability for the current user: `GET /stats` - headline counters (runs/threads/agents/tokens/cost); `GET /runs` - paginated run history joined with thread titles (per-run cost); `GET /usage` - zero-filled daily token series + per-model breakdown with spend. Queries `runs`/`threads_meta` directly as a reporting layer (no new `RunStore` methods); requires a SQL database backend — returns 503 on `database.backend: memory`. Real-cost estimation reads optional `models[*].pricing` (`currency`, `input_per_million`, `output_per_million`, `input_cache_hit_per_million`) and is cache-aware: cache-hit input tokens are billed at `input_cache_hit_per_million` (omitted → billed at the miss price, a conservative upper bound). All priced models must use one currency; mixed currencies disable cost reporting and leave cost/currency fields null instead of producing invalid aggregates. Legacy rows fall back to run-level totals at `model_name`; unpriced models yield `cost: null` |
| **MCP** (`/api/mcp`) | GET /config - raw/masked; PUT /config - bulk; PATCH /config - toggle; POST /config/servers - add; PUT /config/server - replace; DELETE /config/servers/{server_name:path} - bodyless. Validate expanded, save raw; reload/reset; invalid -> 400. |
| **MCP Tasks** (`/api/threads/{id}/mcp-tasks`) | `GET /` - current user's durable tasks for one owned thread; `GET /{task_id}` - bounded result/input/status-error/cancellation-error detail, including cancellation attempt count, without remote task IDs or driver configuration |
| **Skills** (`/api/skills`) | `GET /` - list; `GET /{name}` - inspect; `PUT /{name}` - toggle; `POST /install` - install a thread-local .skill archive; `POST /install/upload` - admin-only multipart, authorized before parsing and capped at a 100 MiB file plus 1 MiB framing; `POST /reload` - invalidate process-local cache after trusted filesystem changes |
| **Subagents** (`/api/subagents`) | Admin managed-worker CRUD and listing. |
| **Integrations** (`/api/integrations`) | Managed Lark/Feishu CLI integration: `GET /lark/status` - integration state incl. `sandbox_runtime_mode` / `sandbox_runtime_ready`; `POST /lark/install` - admin-only skill-pack install; `POST /lark/config/start` / `/lark/config/complete` - internal first-time connection setup; `POST /lark/config/credentials` - atomically switch the caller's per-user Lark app after validating through the official CLI's live tenant-token probe, revoke previous OAuth tokens, and restore the prior credential tree if the switch fails; `POST /lark/auth/start` / `/lark/auth/complete` - browser device-flow authorization without terminal access, with optional `domains` / exact `scope` grants. Config and auth flows carry a server-issued, per-user generation persisted under the credential lock; a rejected direct switch leaves the generation unchanged and stale completions return 409 |
| **Memory** (`/api/memory`) | `GET /` - memory data; `POST /reload` - force reload; `GET /config` - config; `GET /status` - config + data |
| **Uploads** (`/api/threads/{id}/uploads`) | `POST /` - upload files (auto-converts PDF/PPT/Excel/Word); non-mounted sandbox sync uses a non-releasing request lease; `GET /list` - list; `DELETE /{filename}` - delete |
| **Threads** (`/api/threads/{id}`) | `DELETE /` - remove DeerFlow-managed local thread data after LangGraph thread deletion; `POST /branches` - branch a completed assistant turn with a replay checkpoint (workspace copy, history seeding, and title rules: [Branch workspace and history seeding](../../docs/THREAD_LIFECYCLE.md#branch-workspace-and-history-seeding)); `GET /goal`, `PUT /goal`, `DELETE /goal` - read, set, and clear the active thread goal; `POST /compact` - summarize older active context, deriving memory policy and bucket from the state-producing checkpoint rather than request `agent_name`, and block while a run is in flight; unexpected failures return a generic 500 detail |
| **Artifacts** (`/api/threads/{id}/artifacts`) | `GET /{path}` - stream artifacts with `FileResponse`, including byte-`Range` 206/416 behavior; active content (`text/html`, `text/xml`, `application/xml`, `text/xsl`, any `+xml` type such as XHTML/SVG; `.skill` members too) is always forced as a download attachment to reduce XSS risk; `?download=true` still forces download for other file types. `PUT /{path}` atomically replaces an existing UTF-8 text file under `/mnt/user-data/outputs` when its expected SHA-256 still matches; active runs conflict, and non-mounted sandbox providers receive the same update under a request lease. The outputs-only rule is `path_utils.resolve_outputs_confined_path`, shared with IM-channel attachment delivery: a percent-encoded `..` or a symlink planted in `outputs/` must not reach a sibling `uploads/` file. Atomic replacement keeps existing POSIX permission handling where descriptor-based APIs exist and platform-native temporary-file permissions otherwise (Windows) |
| **Suggestions** (`/api/suggestions`) | `GET /config` - global suggestions config boolean; `POST /threads/{id}/suggestions` - generate follow-up questions; rich list/block model content is normalized and inline reasoning (`<think>...</think>`, including unclosed/truncated blocks from reasoning models like MiniMax-M3) is stripped before JSON parsing |
| **Input Polish** (`/api/input-polish`) | `POST /` - rewrite a composer draft before it is sent. A short authenticated `runs:create` LLM request using `input_polish` config; it does not create a LangGraph run, persist a message, or modify thread state. Shares the non-graph one-shot LLM path (`deerflow.utils.oneshot_llm.run_oneshot_llm`) with the suggestions route; validates the same stripped view of the draft it sends to the model, and preserves literal `<think>` substrings in the rewrite (`strip_think_blocks(truncate_unclosed=False)`) |
| **Thread Runs** (`/api/threads/{id}/runs`) | `POST /` - create background run; `POST /stream` - create + SSE stream; `POST /wait` - create + block. Before the first journaled run, seed an empty feed from a checkpoint so legacy checkpoint-only history keeps its order and visibility; skip absent checkpoints or populated feeds. `POST /regenerate/prepare` / `POST /edit-regenerate/prepare` - clean input + checkpoint metadata for regenerating or edit-replaying, carrying the thread title per the title-preservation rules in [Regenerate and edit-replay preparation](../../docs/THREAD_LIFECYCLE.md#regenerate-and-edit-replay-preparation); `GET /` - newest 100 runs; `GET /page` - keyset history page `{data, has_more, next_before_created_at, next_before_run_id}`; `GET /{rid}` - run details; `POST /{rid}/cancel` - cancel; `GET /{rid}/join` - join SSE; `GET /{rid}/stream` hides action/wait (GET action 405 pre-owner; POST needs `runs:cancel`); `GET /{rid}/messages` - paginated per-run messages `{data, has_more}`; `GET /{rid}/events` - full event stream; `GET /{rid}/workspace-changes` - workspace/output file change summary and optional diffs; `GET/POST /{rid}/artifacts/archive` - receipt manifest / bounded ZIP; `GET /../messages` - legacy thread message array; `GET /../messages/page` - backward thread-global `seq` history page with middleware/subagent-AI/successful-regenerate/edit-replay filtering and page-run-scoped feedback enrichment (subagent AI callbacks remain available through run events while parent `task` ToolMessages stay visible for card restoration); `GET /../token-usage` - aggregate tokens plus an optional `context_usage` percentage (counts messages from the latest materialized thread state through `build_thread_checkpoint_state_accessor`, so full and delta checkpoint modes expose the same input; percentage uses the latest run's model and its `context_window`) |
| **Feedback** (`/api/threads/{id}/runs/{rid}/feedback`) | `PUT /` - upsert feedback; `DELETE /` - delete user feedback; `POST /` - create feedback; `GET /` - list feedback; `GET /stats` - aggregate stats; `DELETE /{fid}` - delete specific |
| **Runs** (`/api/runs`) | `POST /stream`, `/wait` - stateless runs requiring `runs:create`; optional body `thread_id` is owner-checked. Scheduled-task create/update/resume/trigger also require `threads:write` plus `runs:create`. `GET /{rid}/messages`, `/feedback` - run messages/feedback |
| **GitHub Webhooks** (`/api/webhooks/github`) | `POST /` - receive GitHub App / repo webhook deliveries. Verifies `X-Hub-Signature-256` against `GITHUB_WEBHOOK_SECRET`; exempt from auth + CSRF because authenticity is enforced by HMAC. Fail-closed: mounted only when `GITHUB_WEBHOOK_SECRET` is set, or when explicit dev opt-in `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1` is set. Recognized events: `ping`, `issues`, `issue_comment`, `pull_request`, `pull_request_review`, `pull_request_review_comment`; unknown events return 200 with `handled=false`. Fan-out runtime failures return 503, keeping the delivery recorded as failed for manual/API/scripted redelivery (GitHub does not automatically retry any failed delivery, 5xx included); permanent/non-retryable conditions such as `channels.github.enabled: false`, unknown events, malformed payloads, or unavailable channel service return 200 with a skipped/handled response |
| **GitHub Event-Driven Agents** | Custom agents declare a `github:` block in their `config.yaml` to bind to repos and event triggers. Webhook fan-out publishes one `InboundMessage` per matching binding to the channel bus; `GitHubChannel` routes those messages through `ChannelManager`. The response `dispatch` summarizes matched/fired/skipped agents |

Thread identifiers use the shared `deerflow.utils.thread_id` contract
`^[A-Za-z0-9_-]{1,64}$`. Caller-provided opaque IDs remain supported; UUIDs
are generated only for `None`, while explicit empty strings fail validation.
Gateway creation and state-producing request boundaries, embedded-client
entry points, filesystem/upload/event-store consumers, scheduled launches,
and the standalone Provisioner enforce the same contract before persistence
or workspace initialization. Route-addressable legacy IDs remain accepted by
pure reads and cleanup/control endpoints; deleting one best-effort removes
metadata and checkpoints but skips local filesystem cleanup, so the raw value
is never interpolated into a host path. New runs, workspace/sandbox
operations, and other state-producing mutations remain blocked.

**Message feed seq** (#4666): streaming `values` frames, `GET
/threads/{id}/state`, and `POST /threads/{id}/history` stamp serialized
messages with `additional_kwargs.deerflow_seq` so clients can place
checkpoint-kept messages against the paged feed; the REST reads resolve the
store via `threads.py::_optional_run_event_store` (a feed-less deployment
still reads threads), and `services.py::normalize_input` strips the
server-owned key from client input (#4380). Mechanism and identity rule:
`packages/harness/deerflow/runtime/AGENTS.md`.

**Workspace change review**: `packages/harness/deerflow/workspace_changes/`
captures a pre-run and post-run snapshot of the thread-owned `workspace` and
`outputs` directories. `runtime/runs/worker.py` performs the filesystem scan via
`asyncio.to_thread` and writes a `workspace_changes` event with category
`workspace` when changes exist. Uploads are intentionally excluded. Text diffs
are size-limited; binary, large, and sensitive-looking paths are persisted as
metadata only. Internal process-feedback directories never count as changes:
the scanner's `EXCLUDED_DIR_NAMES` drops `BROWSER_FRAMES_DIRNAME` (transient
browser screenshots) and `TOOL_RESULTS_DIRNAME` (the tool-output budget
middleware's default externalization subdir; `constants.py` is the shared
source of truth for both writers and the scanner), and the worker threads the
configured `tool_output.storage_subdir` through the snapshot capture as an
extra excluded dir name so custom storage locations stay excluded too.

**Run delivery receipts**: the worker derives delivery requirements from the
run's workspace snapshots rather than a client request option (files
created/modified under `/mnt/user-data/outputs`, minus internal
process-feedback exclusions) and idempotently persists a run-scoped
`run.delivery` receipt before the terminal run status; missing or
unverifiable `present_files` coverage downgrades the run to error, while runs
without changed outputs keep ordinary chat behavior. Journal mechanics
(callback attribution, receipt idempotency and retries, orphan recovery):
`packages/harness/deerflow/runtime/AGENTS.md`. Multi-worker deployments
require `run_events.backend: db` for shared, ordered delivery events; the
startup gate rejects process-local memory and JSONL event stores when
`GATEWAY_WORKERS > 1`.

**RunManager / RunStore contract**:
- LangGraph-compatible run requests validate their supported subset before creating a run. `runtime/stream_modes.py` is the shared backend contract for public stream modes and the worker's `graph.astream` mapping; the public `messages-tuple` mode maps to LangGraph's internal `messages` mode, while public `messages`, `events`, and other unsupported modes are rejected instead of being dropped or replaced with `values`. `run_models.py::RunCreateRequest` is shared by HTTP and internal scheduled launch paths, retains only truthful compatibility defaults for unimplemented options (`if_not_exists="create"` plus `None` placeholders), returns 422 for unsupported values including `on_completion="complete"`, `on_completion="continue"`, and `multitask_strategy="enqueue"`, and forbids undeclared SDK options so fields such as `checkpoint_during` and `durability` cannot be silently discarded. A placeholder must still accept the stock SDK's own default: `langgraph_sdk` drops only `None` from its run payload, so `stream_resumable=False` reaches every request and means "non-resumable", which is what DeerFlow serves — rejecting it 422'd every IM channel run (#4466). `tests/test_run_request_validation.py::test_gateway_accepts_langgraph_sdk_default_payload` pins the real SDK payload against this boundary; channel tests mock the SDK client and cannot catch this class of drift.
- `RunManager.get()` is async; direct callers must `await` it.
- The history batch helpers `list_successful_regenerate_sources()`, `list_edit_regenerate_runs()`, and `get_many_by_thread()` default to `user_id=AUTO`: they resolve the request user and fail closed when no user context exists. Migration/admin callers that intentionally need an unscoped read must pass `user_id=None` explicitly.
- Edit-and-rerun visibility is derived from edit replay runs (`metadata.replay_kind="edit"` plus `regenerate_from_run_id`) by `RunManager.list_edit_replay_visibility()`: the newest attempt for each source run is authoritative. Pending/running/success attempts hide the original source run; failed, timed-out, or interrupted attempts hide only the failed attempt so the original conversation reappears.
- When a persistent `RunStore` is configured, `get()` and `list_by_thread()` hydrate historical runs from the store. In-memory records win for the same `run_id` so task, abort, and stream-control state stays attached to active local runs.
- Thread metadata status switches to `running` only after `RunManager.try_start()` succeeds. Pending-cancelled runs therefore skip the old `running` projection.
- `cancel()` returns a :class:`~deerflow.runtime.CancelOutcome` enum: `cancelled` (local cancel), `requested` (the non-owning worker durably recorded the first cancellation action for the live owner), `taken_over` (non-owning worker claimed the run because the owner's lease expired — marks it as `error`), `lease_valid_elsewhere` (legacy/custom store lacks the durable request primitive — caller retains the safe 409 + `Retry-After` fallback), `not_active_locally` (heartbeat disabled, preserving the old 409 path), `not_cancellable` (terminal state), or `unknown` (not found in memory or store). `create_or_reject(..., multitask_strategy="interrupt"|"rollback")` persists interrupted status through `RunStore.update_status()`, matching normal `set_status()` transitions.
- Interrupt/rollback admission registers the replacement before its best-effort persistence of locally interrupted predecessors. If the admitting caller is cancelled during that post-registration await, `RunManager` drains a shielded replacement cleanup before propagating `CancelledError`, including across repeated cancellation: the cleanup normally persists `interrupted`, and if that best-effort transition fails it retries the active-to-`interrupted` store transition strictly and verifies the result with the replacement's captured owner identity. A concurrent peer terminal transition wins and is synchronized back into the local record rather than being overwritten or deleted.
- Store-only hydrated runs are readable history. In multi-worker mode with heartbeat enabled, cancel on a store-only run records `runs.cancel_action` / `cancel_requested_at` while the owner's lease is live; the first action wins even if a retry later lands on the owner. `RunStore.request_cancel()` and owner completion through `finalize_if_not_cancelled()` are competing active-row CAS operations, so an accepted cancel cannot be overwritten by a later success; `RunStore.renew_lease()` renews and observes the request atomically in the SQL implementation. The owner then executes the normal process-local interrupt/rollback and terminal stream path without transferring the lease; an expired owner is still taken over and marked `error`. `wait=true` and cancel-then-stream use the shared bridge to observe owner finalization; a non-standard process-local bridge returns accepted 202 instead of subscribing to an unreachable stream. In single-worker mode (heartbeat off), store-only runs still return 409.
- A local worker's `RunRecord.lease_expires_at` is the last durably confirmed ownership deadline. `_renew_leases()` bounds each renewal attempt by that deadline: transient store exceptions remain retryable while it is valid, but an exception or blocked call that reaches expiry sets the process-local `ownership_lost` fence, raises `abort_event`, and cancels the run task. Fenced workers do not perform subsequent journal/delivery-receipt, progress/completion/status, checkpoint/thread-metadata, or `on_run_completed` writes; the peer recovery path owns the terminal receipt. `RunStore.update_run_completion()` also refuses to replace a different terminal status, closing the peer-takeover/late-finalization race. `grace_seconds` delays peer reclamation for clock skew but is not extra execution time for an owner that can no longer confirm its lease. Renewal-signal and side-effect boundaries beyond these: [run delivery and stream recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics).
- Startup/orphan reconciliation must claim stale active rows with `RunStore.claim_for_takeover()`, not a plain `update_status()`. The final claim re-checks `status` and lease expiry atomically, so a heartbeat renewal between the candidate scan and the recovery write keeps the run active.
- Run admission and independent writes are first-class thread operations. `runs.operation_kind` distinguishes `run` from `checkpoint_write`, `artifact_write`, `artifact_archive`, `branch`, and `delete`; every active kind shares the durable active-thread uniqueness constraint. New operation kinds must go through `RunStore.create_thread_operation_atomic()` and `RunManager.reserve_thread_operation()` rather than adding another lock or metadata marker. Reservations are excluded from run history/reporting and from run-only helpers such as `list_by_thread()` and `has_inflight()`; release uses the captured owner rather than ambient user context. `RunStore.create_run_atomic()` remains a deprecated compatibility shim for external stores that only admit normal runs; new stores must implement `create_thread_operation_atomic()` to support internal operation kinds. Reservation interruption, lease-loss translation, and fail-closed boundaries: [run delivery and stream recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics).
- Gateway checkpoint mutations outside run execution must use `services.reserve_checkpoint_write()`, which composes the process-local thread lock with the durable `checkpoint_write` reservation. Manual compaction, `POST /threads/{id}/state`, and both goal mutation routes (`PUT` / `DELETE /threads/{id}/goal`, including creation of a missing goal checkpoint) use this boundary, so an existing run blocks the write and the reservation blocks new reject/interrupt/rollback runs across workers.
- Branch/state-update checkpoints copy only the source checkpoint's persisted `deerflow_agent_name`, never request metadata; missing or malformed bindings stay unbound so compaction fails closed.
- `DELETE /api/threads/{id}` holds a durable `delete` reservation for the whole cleanup and removes thread filesystem data, checkpoints, owner-scoped historical runs, run events, feedback and thread metadata best-effort. Historical-run cleanup removes only `operation_kind="run"` rows, so internal thread-operation rows — including the reservation protecting that request — stay durable until `RunManager.reserve_thread_operation()` exits. This cleans persisted rows; preventing an already-admitted write from re-creating state for a deleted thread is a separate thread-incarnation contract, not part of this cleanup.
- `POST /wait` (both thread-scoped and `/api/runs/wait`) drains the stream bridge via `wait_for_run_completion()` instead of bare `await record.task`, so it honours the run's `on_disconnect` setting and cancels the background run on real client disconnect rather than returning a stale checkpoint (issue #3265).
- Memory and Redis `StreamBridge` implementations retain only `stream_bridge.queue_maxsize` data events. A syntactically valid `Last-Event-ID` older than the retained watermark, or a live subscriber that falls behind it, yields `StreamGap` before any partial replay; `sse_consumer` maps that control item to an id-less SSE `gap` payload (`stream_replay_gap`) and intentionally leaves the run active. Redis checks bounds plus the non-blocking read in one transaction, using blocking `XREAD` only as a wake-up before repeating the atomic snapshot; malformed cursor behavior remains backend-specific. Redis `StreamBridge` keys use a rolling retained-buffer TTL (`stream_bridge.stream_ttl_seconds`, refreshed on `publish()` / `publish_end()`) as a leak safety net, not as a run timeout. Provisional first-wake, numeric-cursor, and replay policies: [run delivery and stream recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics).
- Startup and lease-driven periodic orphan recovery share one Gateway stream-terminalization path: after `RunManager` durably marks a run `error` with `stop_reason=orphan_recovered`, Gateway publishes `END_SENTINEL` and schedules stream cleanup, run as one supervised single-flight task. Only startup recovery, before the runtime yields to requests, projects the latest affected thread to `error`; periodic recovery deliberately avoids that non-atomic projection because `ThreadMetaStore` has no `latest_run_id` conditional-update contract. The explicit `orphan_recovered` signal is the only heartbeat fallback: its publisher is known to be gone, so it supplies the liveness boundary if END publication fails or the retained key expires. Keep cross-component recovery orchestration in Gateway through the generic `RunManager.on_orphans_recovered` callback; do not introduce a harness-to-app dependency. Orchestration detail (shutdown priority, delayed cleanups, callback warnings): [run delivery and stream recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics).
- Thread-scoped run creation accepts an optional `Idempotency-Key` header on create, stream, and wait. Gateway hashes the caller key with the authenticated owner and `thread_id` before passing it to `RunManager`, whose persistence index is process-wide; never pass an unscoped external key to that index. The same scoped key is shared across `/runs`, `/runs/stream`, and `/runs/wait`; a reused admission whose stored `input` or `assistant_id` differs from the retry returns 409. Reused `/wait` returns durable `status`/`error`, never the latest thread checkpoint (a later run on the same thread may have advanced the head). Reuse decision capture, sticky `idempotency_reused`, SSE `gap`/`recovery: reload_durable_state` emission rules, and 409 matching: [run delivery and stream recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics). Missing headers preserve ordinary non-idempotent admission; stateless `/api/runs/*` stays outside this contract because a request without an explicit thread creates a fresh temporary thread before admission.
- Thread-scoped run creation accepts `checkpoint` / `checkpoint_id`; Gateway validates the checkpoint belongs to the request thread before writing `checkpoint_id` / `checkpoint_ns` into `config.configurable` for LangGraph branching. In `delta` checkpoint mode the worker rewrites that fork into a linear head write before the graph starts (see "A delta-mode run cannot fork" under Checkpoint Channel Modes), because delta state for a fork replays the abandoned sibling's writes.
- Thread-scoped Gateway runs evaluate an active `ThreadState.goal` after the visible turn completes. `runtime/goal.py` asks a non-thinking evaluator model to judge only visible conversation evidence and return a typed blocker. Every non-satisfied evaluation — continuable or stand-down — is persisted with `last_evaluation` (the blocker, reason, and evidence summary; outcomes that stop the loop additionally record a `stand_down_reason` for observability), but only `goal_not_met_yet` evaluations are streamed as hidden `HumanMessage` continuations, and only when the turn did not end on an unanswered Human Input Card (`ask_clarification` or the sandbox network prompt; the evaluator never sees those ToolMessages, so the goal stands down with `blocker: "needs_user_input"` without calling it), a durable assistant end-of-turn checkpoint exists, the run has not been aborted, the run has not hit its token-budget hard stop (`stop_reason == "token_capped"`, standing down with `stand_down_reason: "token_capped"`), the thread did not change during evaluation, and the no-progress breaker has not fired. The continuation cap is 8 — a hard maximum in the `0`–`8` range; callers requesting more are clamped (`set_goal`/TUI) or rejected with 422 (`PUT /goal`). The no-progress breaker keys on the latest visible assistant evidence (not the evaluator's free-text reason, which an LLM rewords every turn), so two consecutive continuations that add no new visible assistant output stop the loop after 2 attempts. Evaluator creation/tracing: [run delivery and stream recovery mechanics](../../docs/development-reference.md#run-delivery-and-stream-recovery-mechanics). Model-response cleanup helpers such as think-block stripping and code-fence stripping live in `deerflow.utils.llm_text` so `runtime/goal.py` and Gateway suggestion parsing share the same JSON-prep behavior.
- Run event stream changes must keep producer code, `deerflow/constants.py`, `runtime/events/catalog.py`, `contracts/run_event_stream_contract.json`, `backend/docs/RUN_EVENT_STREAM.md`, and `tests/test_run_event_stream_contract.py` in sync. The dependency-free constants module owns the persisted envelope limits (`event_type` 32 characters, `category` 16) and cross-layer workspace event identity; the catalog owns validated runtime definitions and categories. Dynamic middleware tags are limited to 21 characters after the `middleware:` prefix. The JSON contract owns payload schemas, backend-specific storage semantics, legacy aliases, and compatibility rules; conformance tests require both views and all producer groups to agree. `run.end.content` remains opaque and may retain nested Python values in memory while JSONL/database stores stringify non-JSON nested values, so consumers must not assume backend-identical nested output representations.

Proxied through nginx: `/api/langgraph/*` → Gateway LangGraph-compatible runtime, all other `/api/*` → Gateway REST APIs.

**Thread lifecycle**: Before changing branching, regeneration, edit replay, or
archive/search behavior, read [Thread lifecycle invariants](../../docs/THREAD_LIFECYCLE.md).
It owns lineage and settled-checkpoint rules, legacy fallback boundaries, archive
filtering before pagination, owner isolation, and activity-time preservation.
