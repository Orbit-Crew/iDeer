---
id: backend-docs-thread-lifecycle
kind: reference
status: current
owner: repository maintainers
scope: gateway thread lifecycle invariants: checkpoint lineage, branching, regenerate/edit replay, and archive metadata
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 3cd547c26
---

# Gateway thread lifecycle invariants

Read this guide before changing thread branching, regeneration, edit replay, or
archive/search metadata behavior. It supplements the Gateway module guide.

**Branch/regenerate checkpoint invariant**: `app/gateway/checkpoint_lineage.py`
walks `parent_config` rather than globally ordered checkpoint history so replay
anchors stay on the selected lineage after regenerations create sibling branches.
New conversation branches persist the pre-user replay anchor before their visible
head through the state mutation graph, which preserves materialized state in both
full and delta checkpoint modes. Only an explicitly absent legacy parent link may
use chronological compatibility lookup; cycles, dangling links, and depth-limit
exhaustion fail closed. Existing single-checkpoint branches are never repaired by
copying a raw checkpoint because delta state is not self-contained in one tuple.
Both lookups additionally require the replay base to be a **settled** checkpoint
(`has_pending_tasks` — no scheduled `next` tasks). A checkpoint with pending tasks
is a mid-run snapshot: resuming from it replays the writes of the node that was
about to run. Message ids alone cannot exclude those, because middleware may
rewrite a message's id inside the run that produced it — `DynamicContextMiddleware`
moves the first user turn to `{id}__user` and gives `{id}` to the injected
reminder, so every checkpoint written before it holds the same prompt under an
unmatched id. Selecting one of those re-added the original prompt *after* the
edited one, and the model answered the question the edit was replacing (#4531).
`next` is not derivable on the degraded raw-checkpoint read path, which reports no
tasks; absence of evidence stays permissive there rather than failing closed.
Edit replay resolves its base through the same lineage-first path as regenerate;
it must pass `head_checkpoint` or it silently degrades to the chronological scan
that cannot tell sibling branches apart.

## Branch workspace and history seeding

Branch admission is durable and rejects races. Inherited titles take the
next-free displayed sibling suffix (including explicit/renamed ones), while
explicit titles stay unchanged.

Workspace files are not checkpointed, so `POST /api/threads/{id}/branches` only
best-effort copies the current workspace when branching from the **latest** turn
(`workspace_clone_mode="current_thread_best_effort"`); branching from an
older/historical turn skips the copy
(`workspace_clone_mode="skipped_historical_turn"`) so the branch never inherits
files that only exist in a later timeline. Thread-scoped runtime channels
(`sandbox`, `thread_data`) are not copied onto the branch: the parent's
`sandbox_id` binds path mappings and the release lifecycle to the parent's
workspace, so the branch lazily acquires its own sandbox instead.

Branch creation also seeds the new thread's run-event feed from the branch
checkpoint's visible messages (`history_seed_mode` in the response). The thread
feed reads run_events, not checkpoints, so without the seed the inherited
history disappears from the UI after the branch's first run (#4380). Seeded rows
are grouped into one synthetic run per inherited turn
(`branch-seed-{thread_id}-{n}`, a new turn opening at every persisted human
message, including an allowlisted hidden `ask_clarification` reply) because
`run_id` is a turn identity to the feed's consumers, not a provenance tag:
regenerating an inherited answer supersedes that row's whole `run_id` in
`GET /messages/page`, so one shared id for the entire seed deleted the complete
inherited history on a branch's first regenerate (#4458).

## Regenerate and edit-replay preparation

`POST /api/threads/{id}/runs/regenerate/prepare` prepares clean input plus
checkpoint metadata for regenerating the latest completed or interrupted
assistant answer, carrying the latest non-empty thread title in graph input so
resuming an older checkpoint cannot roll back a later manual rename (#4457).
`POST /edit-regenerate/prepare` prepares a checkpoint replay from the latest
editable human turn with a replacement user message and edit replay metadata; it
carries the current thread title the same way, but only when the replay base
already has one — an untitled base belongs to a thread the title middleware has
not named yet, so pinning the current title there would keep a name generated
from the prompt the edit just replaced.

### Chat archive

`POST /api/threads/search` accepts an optional strict boolean `archived`: omitted
or null preserves the unfiltered API, true selects only JSON boolean
`metadata.deerflow_archived=true`, and false includes missing/null/non-true legacy
flags. Both SQL and Memory thread stores filter before limit/offset and retain
owner isolation. PATCH validates archive flags as booleans; pin/archive-only
boolean metadata writes use `touch=False` to preserve activity ordering. Archive
never changes runtime status, checkpoints, files, schedules, or read permissions.
