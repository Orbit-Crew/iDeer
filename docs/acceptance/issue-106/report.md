---
id: issue-106-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 106 Server implementation and coordinated acceptance
last-verified: 2026-10-26
verified-against: codex/complete-issues-105-110 (f817aa9fa on 591f80cf3)
---

# Issue 106 Server acceptance

Server PR [#142](https://github.com/Orbit-Crew/iDeer/pull/142) (merged as
`6a819f3a73dfc2bda5c097e82b47737c9c1058bc`) retired the Server-side device
runtime copy: the whole `local-runtime/` tree (21 core modules, 26 test
files, packaging metadata) plus the duplicated device-router test lanes and
shrunk test-governance scripts were removed in one shrink commit
(+8/−14,509 over 60 files). `git trees` on both default branches show zero
residual `local-runtime` paths; the Desktop repository owns the single
device-side implementation, and the fixed compatible combination is the
Desktop-bundled Runtime.

Environment: WSL Ubuntu, Python 3.12.3, pytest 9.0.3, candidate-first
PYTHONPATH (backend, harness, extension, extension-api); no unrelated
main-tree product source imported.

| Scenario | Status | Evidence |
| --- | --- | --- |
| T106-01 | passed | The pre-migration Server test inventory continues green on the shrink tree: the combined focused suite (devices/auth-gate/artifacts/local-task-history/updates-address/compatibility gate) passes 29 tests; per-tie focused logs under ignored dev-log. |
| T106-02 | passed | Cross-repo tests and builds no longer reference Server device-side sources; the Desktop-bundled Runtime is the only implementation. The upload scenario re-verified for real on the installed candidate (below). |
| T106-03 | passed | Post-shrink clean-tree rebuild and rerun recorded by PR #142 CI (all required checks green, including blocking-IO, migration and Real E2E gates). |
| T106-04 | passed | Gate inventory and version-combination records kept with the PR; no shared-harness refactor mixed into the migration (the later `/updates` namespace reservation is registered separately as PATCH-030 for #107). |

## Final installed re-verification (0.2.0 candidate, passed)

The installed-candidate switch-over matrix was re-run cross-repo on the
final Desktop 0.2.0 package against the real Gateway fixture from this
branch — including the explicit upload against the live Server artifact
endpoint, an idempotent repeat, second-device download of exact bytes and
the cross-account refusal (13 cases, all passed). Binding, run map and
result JSON: Desktop repository
`docs/acceptance/final-candidate-binding.md` and
`docs/acceptance/issue-106/evidence/installed-matrix-result.json`.

Real Win7 remains `unexecuted` under
[#131](https://github.com/Orbit-Crew/iDeer/issues/131).
