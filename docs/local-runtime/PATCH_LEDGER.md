---
id: docs-local-runtime-patch-ledger
kind: reference
status: current
owner: repository maintainers
scope: Local Runtime line (M7–M9) patch ledger — harness-adjacent patch registrations and per-milestone no-patch records for the device control plane, local file/Python hardening, local MCP, secrets, and tray lines
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 4d2496136
---

# Local Runtime patch ledger (M7–M9)

The M7 control plane does not modify the shared harness package.

> **Authority note (2026-10-01 起).** Harness patches are registered in the root
> [`UPSTREAM_PATCH_LEDGER.md`](../../UPSTREAM_PATCH_LEDGER.md), the sole
> harness-patch authority; the `subagents/registry.py` patch below is tracked
> there as PATCH-029. This ledger remains the record of Local Runtime line
> patches and their patch-specific validation; new harness edits register in
> the root ledger, not here.

| Change | Reason | Scope | Validation |
| --- | --- | --- | --- |
| `7ae6b5907 fix(testing): make backend and smoke lanes hermetic` | Prevent the backend lane and frontend smoke lane from depending on pre-existing runtime state; create required sandbox paths before Uvicorn starts | Test harness and lane scripts only | Backend standard lane and frontend smoke lane passed before M7 implementation |
| `fix(subagents): preserve runtime overrides during managed-store lookup` | Prevent `list_subagents()` from losing a caller-provided global timeout/max-turns override when resolving the default managed-subagent store reloads AppConfig | `backend/packages/harness/deerflow/subagents/registry.py` | Timeout/config regression tests and backend-standard lane passed |
| `fix(scripts): reclaim stopped-stack ports without lsof` (#21) | On WSL2 (lsof 4.93.2) `lsof` exits 1 silently for the Next.js process, so `make stop` missed `next-server`, left port 3000 occupied, and still printed `✓ All services stopped`. Process ownership now resolves through `/proc` (environ marker, cwd, fds) before lsof, port PIDs fall back to `ss` (mirroring `wait-for-port.sh`), foreground services also export `DEERFLOW_DAEMON_ROOT`, and `stop_all` re-verifies 8001/3000/2026 and reports survivors instead of unconditionally succeeding; `run-local-services.sh stop` gets the same `ss` fallback plus a repo-nginx ownership check for its port-2026 sweep. Because the stop paths can now fail, start/restart abort fail-fast with the same survivor report instead of proceeding into a port conflict; `run-local-services.sh` additionally stops killing foreign listeners on port 2026 (it now reports them and exits non-zero) | `scripts/serve.sh`, `scripts/run-local-services.sh` — local runtime scripts, outside the harness package and `UPSTREAM_LOCK.md`, so no root-ledger harness patch | Shell-level regression `backend/tests/unit/scripts/test_stop_cleanup_fallbacks.py` runs both stop paths with a silently-failing fake `lsof` on PATH and a sandboxed `REPO_ROOT`; backend standard lane |

Device control-plane code remains under `backend/app/device_control/`, its
router and migration, and `local-runtime/`. Future edits to shared harness code
must be registered in the root
[`UPSTREAM_PATCH_LEDGER.md`](../../UPSTREAM_PATCH_LEDGER.md) before
implementation.

M8 local file and Python hardening remains outside the shared harness. The
runtime changes use only local-runtime seams and the existing broker protocol;
no new harness patch is required.

M9 local secrets (OS store, `local:` references, redaction gate) also remains
inside `local-runtime/` plus its tests; the broker protocol is unchanged and no
harness patch is required.

M9 `local.mcp.*` model-side integration lives in `local-runtime/core/mcp.py`,
the `agentplatform-extension` local_runtime tools, and their tests; the harness
package is untouched and no harness patch is required.

M9 production closure adds the tray/pairing CLI, secure session references,
policy-hash capability updates, HTTP MCP session-header replay, Windows Job
Object handle correction, and the canonical Agent assembly seam. These edits
remain outside `backend/packages/harness/deerflow/`; the only shared test
surface change is the bounded frontend lane (`--no-file-parallelism`) and the
independent `local-runtime` lane.

The shared extension notifier also now stops immediately when one hook consumes
the shared timeout budget. This preserves the existing timeout contract by
preventing later extensions from starting after the budget has expired; it is
covered by `backend/tests/test_extension_task_lifecycle.py`.

M9 security closure also binds production local-tool assembly to the signed
broker connection. Device online state, owner, announced capabilities, MCP
descriptions, and schema hashes now come from the authenticated websocket;
request context cannot forge them, and unannounced `local.*` operations are
rejected before dispatch.

M9 session invalidation now closes live broker sockets and marks pending tasks
offline when an owner disconnects or revokes a device. The tray treats server
close codes for revoked or superseded sessions as `pairing_required` and stops
automatic reconnects, preventing an expired credential from dialing forever.

M9 configuration closure now creates file/Python services when the first root
is added, removes them when the last root is removed, and swaps the MCP
supervisor when its config path changes; active sessions receive the resulting
capability update immediately.

M9 Streamable HTTP handling validates the negotiated protocol version, preserves
`Mcp-Session-Id` across requests, and clears an invalid session without
replaying the failed request. Regression tests cover JSON responses and session
expiry without replaying a side-effecting call.

On Windows, the device signing key now uses the same Credential Manager seam as
session credentials. A legacy adjacent key file is migrated only after the
secure write succeeds; Linux development keeps the restricted file fallback.
