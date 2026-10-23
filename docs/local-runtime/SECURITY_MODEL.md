---
id: docs-local-runtime-security-model
kind: reference
status: current
owner: repository maintainers
scope: Local Runtime security model — two-layer server/device authorization, required security controls, capability risk levels and redaction rules, and the threat register with observable rejection codes
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 4d2496136
---

# Local Runtime security model

The server authorizes delegation; the device authorizes execution. These are
separate decisions and both must succeed.

## Two-layer authorization

| Decision | Server control plane | Device Local Runtime |
| --- | --- | --- |
| Who is acting? | Authenticated AgentPlatform user and bound Device public key | Authenticated device session and local operator context |
| What is requested? | Run/tool-call identity, task type, payload hash, target device identity | Exact task payload, local capability, allowed roots, consent level |
| Allow condition | User may delegate, Device is owned/active, capability is registered, session is current | Capability is locally enabled, roots/policy match, consent is present when required |
| Deny rule | Missing/expired/revoked identity or authorization rejects delivery | Local DENY always wins, even when the server allowed delegation |
| Evidence | Audit event and server-side task state | Local execution receipt with policy, consent, status, and hashes |

The effective capability is the intersection of agent declaration, caller
authorization, registered device capability, Local Policy, and platform policy.
Filtering occurs before model tool assembly. The model receives no hidden or
unauthorized device capability.

## Required security controls

- Device keys are generated on the device; the server stores only the public
  key and key metadata. Permanent plaintext device tokens are never returned.
- Pairing codes are random, short-lived, single-use, owner-scoped, and consumed
  atomically. Browser confirmation requires the authenticated owner; an
  arbitrary logged-in user cannot confirm another user's device.
- WSS sessions are initiated by the device. The server maintains a registry but
  never dials a user device.
- Each task envelope has a unique task ID, protocol version, issued time,
  `expires_at`, session ID, payload hash, and signature. The receiver rejects
  duplicate IDs, expired envelopes, session mismatches, invalid signatures, and
  hash mismatches before execution.
- Revoke and block are checked on every handshake and task transition. An
  already-open session is closed or fenced when the identity changes state.
- Protocol incompatibility is explicit: a critical mismatch becomes BLOCKED;
  an older but understood runtime becomes OUTDATED and cannot receive tasks
  until its compatibility policy permits it.
- Task cancellation is idempotent and propagates to the device. Offline tasks
  carry an expiry and become `DEVICE_OFFLINE` after the delivery deadline.
- `local.files.list` and `local.files.read` are Level 0 operations. They run
  automatically only below configured logical roots; every request is
  canonicalized and opened through a verified directory handle. Traversal,
  UNC, drive syntax, symlink, and junction escapes are rejected, and errors
  expose stable codes without physical paths.
- `local.files.write` is a Level 1 operation. It accepts a logical workspace
  relative path and UTF-8 text up to 65,536 bytes without NUL. The parent directory
  must exist. Every write requires a fresh local Desktop approval for the exact
  task, payload hash, Thread, and Run. Web approval returns
  `LOCAL_APPROVAL_REQUIRED`; local DENY and boundary restrictions still apply.
  `IDEER_LOCAL_WRITE_CAPABILITIES` defaults to `local.files.write`; setting it to
  an empty value disables Server delegation. The read capability setting does
  not grant writes.
- A write is admitted durably before any file effect, then verified by actual
  readback. A completion-storage failure pauses further writes. Disconnect,
  timeout, or cancellation cannot prove that a write had no effect. Unknown
  write outcomes are never redispatched. A valid late receipt stays attached to
  its original Run and does not resume a cancelled Run. A signed terminal
  receipt remains authoritative if the transport subsequently reports an error.
- Local Python output is redacted incrementally per stream. Long logs are kept
  on disk with incremental hashes and only a bounded preview is returned; a
  timeout, cancellation, or disconnect terminates the process group before a
  terminal receipt is produced.
- Local secrets are stored only in the device OS secure store (Windows
  Credential Manager first, behind a replaceable backend). Tasks and MCP
  configs carry `local:<name>` references; the runtime resolves them on the
  device and injects values into the local process environment only. Secret
  slots reject literal values, so plaintext cannot enter a protocol field by
  that route. A missing reference or an unavailable backend fails the task
  with a stable code (`SECRET_REF_NOT_FOUND` / `SECRET_BACKEND_UNAVAILABLE`);
  there is no plaintext fallback. Stream output, bounded previews, receipts,
  and error messages are scrubbed against the resolved values, so Server DB,
  gateway logs, tool args, LocalExecutionReceipts, and model-visible output
  never contain secret plaintext. There is deliberately no model-callable
  secrets capability: the only secret surface is the local CLI
  (`secret-set` / `secret-rotate` / `secret-delete` / `secret-list`), and
  listing exposes names only.
- The built-in task surface is the harmless echo task, the bounded Level 0
  `local.files.list`/`local.files.read` operations, consent-gated
  `local.files.write`, consent-gated Level 1
  `local.python` execution, and consent-gated projected `local.mcp.*` tools.
  There is no system/shell command capability, and unannounced `local.*`
  operations are rejected before dispatch.

## Threat register

| Threat | Control | Observable rejection/evidence |
| --- | --- | --- |
| Pairing code guessing | High-entropy code, expiry, attempts/rate limit, single use | `PAIRING_INVALID` / audit event |
| Non-owner confirmation | Authenticated owner comparison | `PAIRING_NOT_OWNER` |
| Pairing replay | Atomic consume and terminal session state | `PAIRING_ALREADY_USED` |
| Stolen/revoked device key | State check on handshake and session fencing | `DEVICE_REVOKED` |
| Session hijack | Device-key proof plus session binding and WSS transport | `SESSION_MISMATCH` |
| Task replay | Seen task IDs scoped to device/session and expiry | `TASK_REPLAYED` |
| Task tampering | Signature verification and payload hash | `TASK_SIGNATURE_INVALID` / `TASK_HASH_MISMATCH` |
| Cross-session delivery | Envelope session ID must equal active session | `SESSION_MISMATCH` |
| Server overreach | Local policy and consent gate before execution | `LOCAL_POLICY_DENIED` |
| Secret exfiltration | OS-store-only values, `local:` references on the wire, outbound redaction, literal-slot rejection | `SECRET_REF_NOT_FOUND` / `[REDACTED]` / `INVALID_TASK` |
| Capability drift | Versioned capability registration and intersection at assembly | Capability omission / receipt |
| Offline ambiguity | `expires_at` plus explicit `DEVICE_OFFLINE` state | Task terminal state |
