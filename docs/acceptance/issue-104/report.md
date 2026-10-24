---
id: issue-104-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 104 Server stop intent, durable local-task history and receipt recovery
last-verified: 2026-10-24
verified-against: feat/issue-104 based on 14fcfef9894b72f19fb819d186c2d800e3862062
---

# Issue 104 Server acceptance

Specification: [iDeer #104](https://github.com/Orbit-Crew/iDeer/issues/104).
The implementation uses branch `feat/issue-104`, based on develop
`14fcfef9894b72f19fb819d186c2d800e3862062`.
The Server product, test and build source fingerprint is
`715af6c8605e08354f203bca9f31031e8333704b9e4519de01bac8483305d307`,
recorded at 2026-10-24T01:56:06.894570Z. The report is committed with the
Server implementation. Cross-repository evidence is bound to Desktop
product commit `b84abf1d40f0b90bcc68d546f9cc58e40dbf897d` and evidence
commit `ced7692e40d0650c87a8689ed4ec270c50521138`.
Desktop source SHA-256 is
`3d55ead215f80025dbc4ac6059b6bcca3f3e33ac6ce01c18a0edcdbd6a6df46b`.
The tested installer SHA-256 is
`89128b82a2857e637d686cf09ce4a2d79c5b6e0506a5f5525042c5125d8ca2f9`.

This candidate records stop intent independently of task outcome. An
independent stop during either durable admission or pre-send observation
prevents dispatch. After dispatch begins, the Server attempts signed Runtime
cancellation without waiting for observation storage. A completed signed
receipt remains completion evidence even when stop was requested.
Committed writes are never rolled back. Duplicate task rejection is
uncertainty about the original operation, rather than evidence of failure.

The owned, bounded Thread history API covers tasks from every Run and
survives broker/Server restart. It excludes task arguments, file content,
session credentials and signatures. Recovery does not reconstruct executable
tasks. Receipt replay only confirms original historical evidence and emits
an idempotent acknowledgment; it has no RunManager dependency or Run mutation.
The current contract is documented in the Server repository's
`docs/local-runtime/SECURITY_MODEL.md#thread-task-recovery` and the
[portable API summary](evidence/server/task-history-contract.json).
All production changes are application-owned; no shared harness patch is added.

## Environment and reproducibility

Server validation uses Ubuntu on WSL2, x86-64, kernel
`5.15.167.4-microsoft-standard-WSL2`, glibc 2.39, Python 3.12.3 and
Node 22.23.2. Standard lanes select the isolated Server virtual environment
through `PYTHON`. A run-local PATH wrapper selects installed pnpm 10.26.2.
`TEST_PNPM_BIN` is unset so test-owned fake PATH executables still work.
Backend parallel workers are bounded with
`PYTEST_XDIST_AUTO_NUM_WORKERS=8`; test selection is unchanged.

| Dependency lock | SHA-256 |
| --- | --- |
| `backend/uv.lock` | `5484082ec314c5933225ef852a5c7708bd60c02870472e81a11a8dea0d4d54af` |
| `frontend/pnpm-lock.yaml` | `3ff4163ee66e540357d2f0fed3c03c034ed8bc68c4549ead0d9cf8271a866131` |

Tests use isolated A/B identities, temporary SQLite stores, signed synthetic
device sessions and controlled synchronization events. Expected values are
literal `BEFORE` and `AFTER`, explicit status/error constants and exact
task/Run/tool-call identities. Identity, byte and execution-count tolerance
is zero. Server unit tests assert protocol and persisted history; actual file
bytes and execution counts belong to the separate real Desktop/Runtime checks.
Five-second synchronization timeouts are test liveness bounds, not task
execution deadlines.

## Scenario evidence

The user confirmed the Desktop stop/recovery UI, signed Runtime protocol,
real file bytes/counts and real Server-to-Runtime recovery boundaries before
implementation. The following Server checks support the required scenarios.
Both development and installed Desktop runs also passed every scenario.

| Scenario | Server automatic checks | Real cross-repository status |
| --- | --- | --- |
| T104-01 | passed: requested stop differs from terminal receipt; committed completion wins; awaiter and independent broker stops before dispatch send zero tasks; signed cancel is attempted before blocked observation storage | passed in development and installed runs: pending stop executes zero writes; stop after first write retains AFTER and leaves second target BEFORE |
| T104-02 | passed: disconnected writes retain uncertainty, replay markers do not invent failure, duplicate receipt uploads retain one acknowledgment and original identity | passed in both runs: disconnect before write retains BEFORE and zero executions; disconnect after write retains AFTER and one execution; duplicate delivery never repeats the write |
| T104-03 | passed: late signed completion verifies original task history; replay does not create broker tasks; unfamiliar receipt states never become tool success | passed in both runs: late completion verifies the original Task, terminal Run remains unchanged, pending receipt upload survives reopening |
| T104-04 | passed: new broker restores durable Thread history, owner isolation, pending phase and acknowledgment state; populated legacy schema upgrades preserve original signed task and evidence | passed in both runs: actual Runtime, Desktop and Server restarts restore history; unknown original Task and file hashes remain unchanged during read-only recovery checks |

The primary Server regression entry points are
`backend/tests/unit/device_control/test_task_recovery.py`,
`backend/tests/integration/api/test_local_task_history.py`, and
`backend/tests/integration/persistence/test_task_history_migration.py`.
The original broker, receipt and migration regressions remain in the focused run.
Cross-repository entry points are the Desktop repository's
`scripts/acceptance/issue-104/{server_fixture.py,fixture_hooks.py,desktop.cjs,flow.cjs}`.
The final runs used Microsoft Windows NT 10.0.26300.0, X64.

| Final execution | Desktop command | Server fixture | Result |
| --- | --- | --- | --- |
| Development dev-10 | 93.515 seconds | 124.762 seconds | both exit 0; 9 fault operations and 2 read-only storage recovery checks passed |
| Installed installed-11 | 90.765 seconds | 147.444 seconds | both exit 0; the same 9 operations and 2 checks passed |

Each run captured eight screenshots. Each removed six synthetic credential
references with zero failures, closed its application, removed temporary
state and stopped its Server. The installed run verified identical before
and after hashes for all three pre-existing current-user Runtime profile files.

Expected UTF-8 bytes have zero tolerance. `BEFORE` is six bytes with SHA-256
`c341c7fe1027f9487e8019198223ad7af0b9cfe1564d41c7e7c4d139cd0226f3`;
`AFTER` is five bytes with SHA-256
`94c3f1415d2061d05e4cce4d33e43e26a5ad7ebcf6e89acace6e8b84240a629c`.

Full result JSON, wire events, per-Task UI assertions, cleanup records,
source bindings and screenshots are in the Desktop evidence commit under
`docs/acceptance/issue-104/evidence/development` and
`docs/acceptance/issue-104/evidence/installed`.
The corresponding command records are
`evidence/checks/{functional-dev-10,server-dev-10,functional-installed-11,server-installed-11}.{json,log.gz}`.
A successful Run can contain a Task whose result remains unverified. The
acceptance checks assert Run status, signed Task facts, actual bytes and
execution counts independently.

## Checks and review

Committed evidence is under [evidence/server](evidence/server). It includes
full compressed command logs, the source binding, formatter AST proof and
the [two-axis review](evidence/server/two-axis-review.json). The
[cross-repository summary](evidence/server/cross-repository-summary.json)
records the exact Desktop evidence file hashes.

| Check | Result |
| --- | --- |
| New-slice red-before-green | passed: initial cancellation, persistence recovery, missing HTTP history, legacy migration, replay marker, admission/observation cancellation, blocked-storage stop signaling, unfamiliar receipt statuses and connection cleanup all failed before their respective fixes |
| Full backend `make lint` | passed; Ruff checks passed and all 2150 files already formatted |
| Frontend `pnpm check` | passed; zero errors, 1273 existing warnings |
| Focused device-control, HTTP history, receipt/migration regressions | passed: 824 passed, 12 skipped, 312 warnings, 115.41 seconds; complete related persistence directories include serial and nonserial cases |
| `python3 scripts/test_inventory.py` | passed; all new files belong to backend-standard |
| `bash scripts/run-test-lane.sh local-runtime` with isolated Python | passed: 230 passed, 4 skipped, final parent sub-lane 28 seconds |
| `pr-standard` backend-standard child | passed: 26935 passed, 237 skipped, 1100 warnings; pytest 831.01 seconds, lane 881 seconds |
| `pr-standard` frontend-standard child | passed: Rstest 167 files / 1270 tests; Vitest 355 files / 10565 tests; lane 463 seconds |
| `pr-standard` frontend-smoke child | passed: 35 tests, lane 93 seconds |
| Complete `bash scripts/run-test-lane.sh pr-standard` parent | passed, exit 0; `TEST_LANE_DURATION lane=pr-standard seconds=1485 status=0` |
| Selected `QA_ISOLATED=1 TMPDIR=/tmp bash backend/scripts/run-real-e2e.sh` | passed: 7 passed, 5 environment skips, exit 0, 90.355 seconds; verified manual removal of generated read-only state |
| Signed WebSocket echo regression repeated independently | passed 10/10, 48.554 seconds total |
| Two-axis code-review | passed after fixes; Standards and Spec independently rechecked their findings, with no remaining findings |
| Final document checker, upstream patch checker and guidance mirror | passed: no findings; upstream registration verified against develop base 14fcfef9 |
| Final GitNexus all-scope detect-changes | passed: 43 changed files, 88 changed symbols, 17 affected processes, critical risk; structured output has no partial, truncated or error flag |

The final Real E2E run recorded its unique manifest hash, backend PID,
working directory and IDEER_HOME before execution. The official cleanup
stopped the services, but `rm -rf` could not remove generated version
directories with mode 0555. After verifying both ports were closed and
no matching backend process remained, cleanup restored owner permissions
only on the 319 generated directories inside that exact isolated state
directory and removed it. The temporary Next build was removed, and tracked
TypeScript configuration hashes were identical before and after the run.
[Full command and cleanup metadata](evidence/server/real-e2e-final.json)
distinguish automatic cleanup failure from completed manual cleanup.
The earlier non-/tmp attempt and interrupted diagnostic are recorded in
[prior attempts](evidence/server/prior-attempts.json); their state was also removed.

The protected Real E2E command uses its existing environment gates. The five
unexecuted cases and required configuration are recorded in
[real-e2e-skips.json](evidence/server/real-e2e-skips.json).

| Unexecuted Real E2E case | Missing opt-in configuration |
| --- | --- |
| Gate 4 owner document upload/index/delete | Real RAGFlow dataset ID |
| Gate 7 loading/unavailable/restricted chat evidence | Isolated Gate 7 Thread, Run and snippet |
| Gate 8 retrieval evidence, comparison and publish feedback | Isolated Gate 8 data and markers |
| Gate 7 archived item from a real Run | Isolated Gate 7 Thread, Run and snippet |
| Real model workflow and frozen knowledge snapshot | Real model/RAGFlow credentials and markers; default model mode is 0 |

These skips follow the runner's existing selection. All required Issue 104
T104-01 through T104-04 cases were executed in both Desktop development and
installed runs. External real-model, RAGFlow and the unconfigured knowledge
scenario coverage remain unexecuted.

The related persistence run's 12 skips require optional live PostgreSQL
configuration. They are unexecuted PostgreSQL coverage; the executed
recovery and migration evidence uses SQLite.

The first local-runtime invocation stopped at preflight because the system
Python lacked pytest. The first pr-standard invocation stopped at preflight
because root-directory Corepack selected pnpm 11.25.0. Both were corrected
using per-command interpreter and package-manager selection, without
lockfile or global configuration changes. These attempts did not execute
test cases. The first complete standard attempt found nine backend failures:
the Thread route sweep needed the new router registration, and eight
environment tests inherited `TEST_PNPM_BIN` instead of their fake executables.
Both causes were corrected; their focused regressions passed 80 tests.

A later full formatter check found formatting defects in the two modified
device-control modules. The earlier baseline comparison had used the wrong
Ruff configuration and was corrected. Only those two modules were formatted.
AST comparisons proved both files semantically identical before and after
formatting. The in-flight pre-format standard attempt was interrupted and is
diagnostic evidence only. The next full standard attempt exposed a WebSocket test synchronization
race: the test enqueued ACK, progress and result envelopes, then queried
before result processing completed. It observed progress and failed the
unchanged completed assertion. A bounded Event now observes completion of
the real original broker receive implementation, including persistence.
It does not alter production behavior or weaken signed receipt assertions.
The failed test's premature TestClient teardown also waited on cancellation;
a bounded diagnostic retained its thread dump. A full related serial run
found and corrected an omitted migration ancestry assertion.
The final manifest differs from the previous candidate only in those two
test files; every production file hash is identical. The interrupted parent
attempt remains failed diagnostic evidence. Final checks bind the new
full-source fingerprint above.

Standards review found mutable dictionary iteration across storage waits and
database waits under the broker lock; synchronous task snapshots now precede
storage, attachment remains available and invalidated sockets close first.
Spec review found independent cancellation during admission could be followed
by task dispatch; the dispatch fence now checks both persistence boundaries.
Deterministic regressions proved both fixes. Duplicate successful-send
observation writes were removed, and the public recovery contract was added
to current documentation.

## Platform scope

Real Windows 7 validation remains unexecuted under
[iDeer #131](https://github.com/Orbit-Crew/iDeer/issues/131), owned by Neowyh. Pending checks include installation, startup/exit,
stop races, disconnect/restart recovery, SQLite receipt persistence, signing,
TLS/WebSocket dependencies and existing compatibility patches on real Windows 7.
Modern Windows results must not be presented as Windows 7 validation.

Final change-analysis, document, upstream and guidance checks passed after
the standard gate and real fixture runs; their command records and the
structured detect-changes output are under [evidence/server](evidence/server).
Windows 7 remains outside the executed platform evidence.
