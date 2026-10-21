---
id: docs-local-runtime-architecture
kind: reference
status: current
owner: repository maintainers
scope: Local Runtime line architecture — the M7 control-plane boundary (server control plane → extension contract → device runtime), layers and dependency direction, main objects, integration seams, and invariants
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 4d2496136
---

# Local Runtime architecture

This document fixes the M7 boundary for the Local Runtime line. It describes the
current AgentPlatform host and the seams where device control-plane code belongs.

## Durable receipt recovery, issue 101

Desktop uses a SQLite receipt ledger in its Runtime profile. It commits task
admission before an operation, then commits the receipt before sending progress
or a result. Admission failures prevent new operations. If an effect happened
but completion could not be saved, the admitted row remains uncertain and the
UI shows `RESULT_UNCERTAIN`. Repair storage and inspect the actual result;
reconnection never reruns that task. Upload failures alone do not prevent new
operations while reliable local admission still works.

The immutable task basis contains original Server origin, user, device, device
public key, broker public key, Run, Tool Call, Local Task, request hash, original
session and verified task signature. Generated `/workspace/<UUID>` logical
targets are retained; other targets are represented by a SHA-256 digest. Receipts
retain policy/consent decisions, stable error categories and result hashes, with
no credentials, arbitrary task payload, exception text or full file body.

The Server advertises `receipt_replay: 1` in its verified HELLO. Only then can a
Runtime with the same original binding send `receipt_upload` in the current
signed session. It sends evidence only, never a saved result or execution request.
The Server rechecks current device/session and owner state, matches the original
durable dispatch, and atomically stores one receipt and one canonical tool-evidence
projection in `device_control_task_receipts`. Repeated matching uploads return the
same signed `receipt_ack`; conflicting evidence is rejected. The ACK identifies
the receipt ID, receipt hash and durable acknowledgment ID. Ownership is checked
again locally before confirming it.

`GET /api/devices/receipts/{task_id}` returns the authenticated owner's durable
dispatch, receipt, acknowledgment and evidence projection, including after a
Server restart. Other users receive 404. This route and receipt upload do not
invoke Run execution or mutate terminal Run status. The live task result path
remains separate from receipt confirmation.

Desktop history, task summaries and cleanup are filtered by the current profile's
original binding. A different account sees only its own records; old records
remain stored for their original account. Expired credentials do not erase local
facts. Missing identity binding exposes no records. Native cleanup confirmations
capture the ownership scope and the Runtime rechecks it before clearing. Manual
cleanup changes only confirmed records into permanent identity tombstones, which
cannot become pending again. Pending and uncertain rows are protected. History
pages show 20 rows; there is no storage cap or automatic expiry.

The broker's signing key is stored at
`{base_dir}/device-control/broker-signing.key`, with mode 0600 on POSIX. A key is
atomically published on first provisioning and is never included in a receipt,
API response, report or log. Keep it with the deployment's protected persistent
data. Restoring a database on another host requires restoring this same key.
An unreadable or corrupt existing key fails closed; do not delete it to repair a
connection, since a replacement key cannot confirm receipts bound to the original
broker. Older versions used an ephemeral process key. That lost private key
cannot be reconstructed from a database or public pin. Such old bindings require
operator recovery of the original identity; re-pairing with a new key does not
transfer pending receipts to a new identity.

The application-owned migration `20261021_receipt_outbox` follows
`20261018_desktop_login`. Its metadata/evidence table deliberately has no cascading
owner foreign key, so deleting an identity does not silently delete historical
execution facts. Access still requires the original currently authorized owner.

## Layers and dependency direction

```text
Browser / administrator
        |
        v
Gateway API (app.gateway) ---- server database / audit log
        |
        +-- Device control plane: identity, pairing, lifecycle, sessions
        |
        +-- Broker: outbound device sessions and signed task envelopes
        |
        v
Extension API / runtime assembly (deerflow_extension_api)
        |
        v
Local Runtime on the user's device
        +-- transport: outbound WSS only
        +-- policy: local DENY can veto server ALLOW
        +-- core: safe, explicitly registered local capabilities
        +-- receipts: immutable execution evidence
```

The dependency direction is server control plane → extension contract → Local
Runtime. The runtime never becomes a second Agent runtime and the server never
opens a connection to a user's device. A Device is a control-plane identity;
it is not a `Resource`, is not included in the resource type enum, and is not
selected or addressed by the model.

The existing application split remains a hard boundary: `app.*` may import
`deerflow.*`, while the harness must not import `app.*`. Device routes and
persistence therefore live under `backend/app/`; reusable extension contracts
live under `backend/packages/extension-api/`.

## Main objects

| Object | Owner | Responsibility | Lifetime |
| --- | --- | --- | --- |
| Device | Control plane | Stable user-bound public-key identity and lifecycle state | Until revoked/deleted |
| Pairing session | Gateway | Short-lived browser confirmation and device credential exchange | Minutes |
| Device session | Broker | Authenticated connection registered by an outbound device connection | Connection |
| Local capability | Device + policy | What this runtime can do, subject to effective authorization | Heartbeat/registration revision |
| Local task | Run/tool call + device | One delegated, bounded operation | Until result, cancel, expiry, or offline |
| Local execution receipt | Runtime/evidence | What ran, policy/consent, status, and hashes | Bound to the parent run |

## Integration seams

- Gateway startup and route mounting are owned by `backend/app/gateway/app.py`.
- Route authentication and authorization are centralized in
  `backend/app/gateway/authz.py`; device routes must use the existing auth
  context and must not invent a parallel user model.
- SQLAlchemy models share `deerflow.persistence.base.Base`, as shown by
  `backend/app/agentplatform/rbac_models.py` and
  `backend/app/agentplatform/resource_models.py`.
- The extension contract already provides `RunEvidenceEnvelope`, task
  lifecycle hooks, runtime dependencies, and an extension registry in
  `backend/packages/extension-api/deerflow_extension_api/contracts.py`.
- Model-visible tools are assembled through the pure
  `backend/app/agentplatform/tools/assembly.py:assemble_tools` seam. Device
  capabilities must be intersected before this seam; the model must only see
  authorized tools.

## Invariants

1. Device identity is public-key based; bearer credentials are short-lived and
   scoped to a pairing or session.
2. Device connections are outbound-only and are rejected unless the device is
   active and the session matches the current identity.
3. Local policy is authoritative at execution time. Local DENY overrides a
   server ALLOW, and consent binds to the exact task content.
4. Every local task belongs to a legitimate Run and Tool Call and produces a
   structured receipt or a structured rejection.
5. Protocol and runtime versions are negotiated before task delivery.
