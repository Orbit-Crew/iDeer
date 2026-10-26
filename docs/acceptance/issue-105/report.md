---
id: issue-105-server-acceptance
kind: evidence
status: current
owner: Neowyh
scope: Issue 105 Server implementation and coordinated acceptance
last-verified: 2026-10-25
verified-against: codex/complete-issues-105-110 based on 591f80cf3579fcd3ec527d79fa9a867f6f4fc32d
---

# Issue 105 Server acceptance

The Server candidate is in the isolated worktree
/home/neowyh/.codex-worktrees/ideer-complete-105-110-20261025.
Desktop shares the branch name and starts at dc104eacc20fd9990769ba3a577b87300d7cea2b.
Source is not yet committed. Final source binding, installer SHA-256,
dependency/configuration binding and installed acceptance remain in progress.
No issue closure is claimed.

Environment is WSL Ubuntu, Python 3.12.3, pytest 9.0.3. The focused runner uses
the existing dependency environment with explicit candidate-first PYTHONPATH
for backend, harness, extension and extension API. No unrelated main-tree
product source is imported.

| Scenario | Overall status | Current evidence and remaining required work |
| --- | --- | --- |
| T105-01 | incomplete | Server creates no artifacts from generation/read; final installed two-device evidence pending. |
| T105-02 | incomplete | Real device registration, signed completed task, grant, upload and independent-device download pass HTTP checks. Final installed candidate pending. |
| T105-03 | incomplete | Wrong owner/thread, changed digest, invented grant, revocation and permission refusal pass. Installed cancellation/network cases pending. |
| T105-04 | incomplete | Same-token and fresh-token retries return the same one artifact. Installed history screenshots pending. |

## Commands and results

Focused command uses ignored dev-log/issue-105/test.sh followed by these files:
backend/tests/integration/api/test_device_compatibility_gate.py,
test_desktop_artifact_authorization.py, test_desktop_artifacts.py,
test_devices_router.py, test_local_task_history.py and test_updates_address.py
under the same integration/api directory, with -vv -o faulthandler_timeout=25.

The final combined run passed 29 tests in 26.92 seconds, exit 0, with six third-party
Alembic/uvicorn/websockets deprecation warnings. Its log is
dev-log/issue-110/final-focused-legacy.log. Product and test sources are frozen
after this run.

Per-slice red/green logs are in ignored dev-log/issue-105, issue-107 and issue-110.
The production update HTTP red run had 2 failures and 3 passes. Its first green
had 5 passes; actual isolated Nginx/public-origin validation then had 6 passes
in 4.92 seconds, exit 0, in dev-log/issue-107/nginx-public.log.
The signature/restart/receipt run had 2 passes in 4.27 seconds. A larger run
exposed cross-thread in-memory SQLite fixture cleanup blocking. That run was
interrupted and replaced by an isolated file SQLite fixture with independent
connections; the final 29-test combined run includes the legacy fix below.

Final pr-standard, protected Real E2E selection/execution and human release
confirmation are pending the integrated candidate freeze. Signing private keys
are not retained in this report. Win7 remains unexecuted under #131, with
Neowyh responsible for that platform validation; Linux results do not establish
modern Windows or Win7 installed acceptance.

## Original-client compatibility correction and impact evidence

The original Desktop 0.1.0 Runtime HELLO does not contain desktop_version or
runtime_python. A focused red run demonstrated two failures with the original
HELLO and its explicit signed legacyHello mapping. The Server now verifies the
mapping against both signed HELLO runtime_version and registered device metadata,
the exact protocol, the deployed Server identity and a unique reviewed row.
It does not infer missing versions. The narrow green run passed 4 tests in
7.58 seconds; red/green logs are dev-log/issue-110/{red,green}-legacy.log.
Both old-style and new-style signed WS tests cover capability/core blocks,
protocol/version rejection, preserved unknown evidence and receipt replay.

GitNexus structured detect_changes(scope=all) covered 21 changed files,
82 symbols and 18 processes, with critical aggregate risk. Its complete arrays
are in dev-log/issue-110/detect-complete.json; partial=false, truncated=false,
and no tool error. Display-only CLI abbreviation is not used as proof.
The index is candidate-local, 451801 nodes and 964856 edges. Indexing retained
the tool's process-discovery budget limits (7140 entry points and 1824 callees
not explored, 48 walks capped); absent flows are not evidence of no dependency.
Full-text Function search degraded on Invalid UTF-8, while graph indexing and
structured change detection completed. The final legacy helper was added
after that index snapshot and requires the scheduled post-E2E index refresh.

The first pr-standard invocation failed in preflight, before child lanes, on
pnpm 11.25.0 versus locked 10.26.2. A task-local wrapper now selects cached
pnpm 10.26.2 without changing the system installation. The coordinated final
standard lane will record its own child summaries and parent duration.

## Final installed acceptance (0.2.0 candidate, passed)

The installed-candidate cross-repo acceptance ran on the final Desktop
0.2.0 package against this branch's real Gateway: the explicit upload
against the live artifact endpoint, the idempotent repeat, the second-device
download of exact bytes and the cross-account refusal all passed (13-case
matrix; the #106 matrix carries the same artifact flow). Binding and
evidence: Desktop repository `docs/acceptance/final-candidate-binding.md`
and `docs/acceptance/issue-105/evidence/`. Source binding for this report:
branch `codex/complete-issues-105-110` (f817aa9fa on 591f80cf3).
