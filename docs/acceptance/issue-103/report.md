---
id: issue-103-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 103 persistent directory consent and device lifecycle validation
last-verified: 2026-10-23
verified-against: feat/issue-103 based on 207b3926f6652438473d939edc91ce6176547742
---

# Issue 103 Server acceptance

Specification: [iDeer #103](https://github.com/Orbit-Crew/iDeer/issues/103).
Prerequisite #102 was closed/completed before implementation on 2026-10-23.
Branch `feat/issue-103` starts at `207b3926f`, verified against `github/develop`.
Desktop branch `feat/issue-103` starts at `0a26bdf`.

The candidate accepts local completed write evidence only with `approved` or
`directory:<canonical lowercase UUID>`. Live results and durable replay share
that predicate. Current session, owner, device/public keys, original signed
task, Run/tool-call identity and request/result hashes remain mandatory.
The archive retains the grant reference and never resumes an old task.
Desktop owns the grant store, UI, normalized directory enforcement and logout.
Existing Server renewals preserve the device ID/key and rotate session tokens;
revoked devices cannot renew, and new pairings have new device IDs.

## Confirmed test contract and scenarios

The user confirmed WorkspaceFileService, signed Runtime protocol, Desktop chat
UI, real Server-to-Runtime integration, settings and identity lifecycle seams.
Expected file constants are BEFORE, AFTER and NEW; byte/hash tolerance is zero.
The 65,536-byte UTF-8 limit and 300-second production approval timeout remain.
Tests use synthetic A/B accounts, D1/D2 bindings and temporary W1/W2 directories.

| Scenario | Actual entry and observations | Result |
| --- | --- | --- |
| T103-01 | Real Desktop chat directory approval; existing, subdirectory and new writes; canonical grant reference in original task/Run receipt; settings view | Development and installed passed |
| T103-02 | Real outside/protected/junction/local-DENY writes preserve files; signed Runtime rejects scripts and legacy approval import; Server rejects malformed basis in live and replay | Development and installed passed |
| T103-03 | Real logout/reopen, same-binding relogin, legal rotation, device revoke/rebind and B-account isolation; original grant restored only for same binding | Development and installed passed |
| T103-04 | Settings revoke returns writes to one-time approval; pending directory switch has zero executions and unchanged bytes; actual application quit/reopen | Development and installed passed |

Directory switching can leave the original Server Run RESULT_UNCERTAIN after
disconnect; the file and local execution ledger are checked independently.
There is no tray-hide entry. Window close truly exits; tray hiding is not applicable.
All UI actions are automated by Codex. Browser confirmation uses synthetic
owner-authenticated public HTTP APIs; no separate human sign-off is claimed.

## Candidate bindings and evidence

Executed on 2026-10-23, Asia/Shanghai. Server uses isolated WSL Ubuntu/Linux x64,
Python 3.12.3, Node 22.23.2 and locked pnpm 10.26.2. Desktop uses Windows 11 Pro
10.0.26300 x64, Node 22.23.3, test Python 3.12.8 and bundled Python 3.12.10.
Server source SHA-256: `cb2da64c47586adcf249ce0b56f6858b673f80189053e0261b1cdf6f3025a980`. See [per-file binding](evidence/source-binding.json.gz).
Desktop source SHA-256: `3a433a621b9082c134d7c32f5cf1ff6500c231f0be099aa293435c1e17621bb3`.
Installer SHA-256: `fda4a9266eac7853d06529243014b443e20b8d45de87332062d7ad84e388dca9`. Development and installed runs each passed 17 real operations with 15 grouped assertions.

The authoritative cross-repository scenario record and sanitized UI/file/Run
evidence are in iDeer-Desktop `docs/acceptance/issue-103/report.md` and its
`evidence/` directory. Those records bind each candidate source file and lock.
Server-only test, graph and lane evidence is in the adjacent `evidence/` directory.
Earlier failed attempts are retained separately and are not selected evidence.
Real Win7 remains unexecuted under [#131](https://github.com/Orbit-Crew/iDeer/issues/131),
owner Neowyh: installation, startup/exit, credentials, directory consent,
identity lifecycle, native dependencies and filesystem handle protections.

## Server gates

| Command | Result |
| --- | --- |
| Focused broker/archive/login/API pytest files | 74 passed |
| Ruff for changed production/test files | passed |
| `python scripts/test_inventory.py` | passed |
| `python scripts/check_documents.py` | passed after final report registration |
| `python scripts/check_upstream_patches.py --base github/develop --upstream-baseline 345f08be00c8a9495079b732a39b46aa9af1584e` | passed after final report registration |
| `bash scripts/run-test-lane.sh pr-standard` | passed, exit 0 |

| Lane | Result | Seconds |
| --- | --- | ---: |
| `local-runtime` | 230 passed, 4 skipped, 1 warning in 9.48s | 17 |
| `backend-standard` | 26920 passed, 237 skipped, 1079 warnings in 1491.13s (0:24:51) | 1674 |
| `frontend-standard` | Rstest 1270 passed; Vitest 10565 passed | 481 |
| `frontend-smoke` | 35 passed (1.5m) | 105 |
| `pr-standard` | passed, exit 0 | 2285 |

Earlier standard-lane attempts are recorded separately. One used pnpm 11, one exposed TEST_PNPM_BIN to resolver tests, and one lacked uv on PATH. The selected run uses a PATH wrapper for locked pnpm 10.26.2, no TEST_PNPM_BIN, and the installed uv. All 17 resolver regressions pass. An earlier smoke run had three menu-action timeouts; the unchanged three tests passed under the production build, and the selected full smoke lane passed. No assertion or timeout was relaxed. Pinned GitNexus 1.6.10 restored the graph and FTS after the default CLI version drifted.

[Selected lane records](evidence/selected-lanes.json) retain exact commands, UTC timestamps and durations; adjacent compressed logs retain full output.

The shared CI selector chooses governance, backend-standard and static-checks;
the explicit protected-path Real E2E selector is false for these device-control
paths. Real cross-repository acceptance still runs because this ticket changes
authorization and receipts. That functional evidence is separate from browser smoke.

GitNexus is bound to this worktree. Pre-edit exact impacts were LOW:
broker.receive -> device_websocket; archive.accept -> broker.receive -> device_websocket.
The final complete scope-all analysis includes every staged change; its mapping
and doctor result are retained in the adjacent evidence. Graph and FTS are available. Global process
ranking caps are recorded and are not evidence that missing flows are absent.

## Review and disposition

Independent Standards and Spec reviews reported zero Server findings.
No push, merge, release publication or issue closure is performed by this task.
Modern Windows development, installed and standard gates passed. Real Win7 remains deferred to #131.
