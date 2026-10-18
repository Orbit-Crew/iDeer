---
id: acceptance-issue-98
kind: reference
status: current
owner: repository maintainers
scope: Candidate validation for issue 98 browser login and unified device entry
last-verified: 2026-10-18
verified-against: issue-98 working candidate
---

# Issue #98 acceptance

Execution date: 2026-10-18, Asia/Shanghai. Executor: Codex. Server review baseline
`ccb251e07e5f5934b851e4c3df00224718f28123`; Desktop baseline
`2fbfa8528a3f77b11cbf68b8e3f338ec08c1db94`. Final candidate commits, installer
SHA-256, lock/config/environment manifest and installed verification are pending.
Desktop's companion record is `docs/acceptance/issue-98/report.md` in the
iDeer-Desktop candidate. Required incomplete scenarios prevent issue closure.

| Scenario | Focused automatic result | Required real candidate result |
| --- | --- | --- |
| T98-01 | passed, explicit browser confirmation remains separate from Runtime exchange | incomplete, actual browser/public-entry/installed workflow evidence pending |
| T98-02 | passed, wrong initiator/key/owner, expiry, replay and concurrent completion | incomplete for final cross-repository candidate |
| T98-03 | passed in Desktop HTTP/stdio fault injection; bounded credential-free URL/status contract | incomplete for final OS-store/package/log inspection |
| T98-04 | passed for existing real signed WS and MCP regression | incomplete for final nginx cut/reconnect test |

From `backend/`:

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/api/test_desktop_login.py -q --basetemp=../dev-log/pytest-login-green-6 -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/integration/api/test_devices_router_auth_gate.py tests/integration/api/test_devices_router.py tests/integration/persistence/test_migration_0025_repair_run_change_seq.py -q --basetemp=../dev-log/pytest-login-regression -p no:cacheprovider
```

Observed exit code 0 for both commands: the original four login cases passed in
10.85 seconds; adding same-device reauthentication produced 5 passed in 30.72
seconds. The affected existing regression command passed 10 tests
in 17.19 seconds. New/touched Python files pass ruff; new browser route passes
Prettier and ESLint. Standard/pr-standard/protected-path lanes remain pending.
HTTP fixture keys/accounts/database are isolated. TTL is 300 seconds, test clock
advances 301 seconds, business/device TTL is one hour. Wrong-binding, ownership,
expiry and replay literals are respectively `LOGIN_BINDING_INVALID`,
`LOGIN_OWNER_MISMATCH`, `LOGIN_EXPIRED`, `LOGIN_ALREADY_USED`; exact comparisons
have no numeric tolerance. Proxy read/send bounds are 3600 seconds.

Initial collection was blocked by antivirus quarantine of unchanged scanner
sources. The user restored/trusted them. Existing Linux-only uvloop fixtures now
retain uvloop when available and use native asyncio otherwise. HTTP regressions
then exposed SQLite's naive/aware in-memory datetime comparison; SQL atomic
updates now disable ORM synchronization and all focused cases pass. Existing-device
renewal requires the same owner and proof of its private key, keeps its device ID
and invalidates old sessions. Desktop profiles without authenticated business
identity stay offline.

The final renewal-state refinement first brings the old session online, then
asserts the renewed response is offline until its new authenticated handshake.
All 5 login cases passed in 43.82 seconds. A post-hoc untouched-HEAD router replay
failed the first new HTTP assertion with `404 != 200`, 1 failed / 4 deselected
in 27.18 seconds; `dev-log/login-baseline-replay.log` retains that session evidence.

The full-Gateway negative run later found that the global HTTPException handler
converted new `LOGIN_*` detail dictionaries to strings. The integration fixture
now registers the production exception handlers. It first reproduced 3 failures
and 2 passes in 27.48 seconds. An explicit seven-code allowlist addition preserves
HTTP status and `detail.code`, while retaining the existing top-level
`error.code=INTERNAL_ERROR` convention and other branches. The 5 login tests plus
global-handler/payload regressions, including all seven codes, then passed
23 tests in 16.04 seconds; evidence is `dev-log/login-global-handler-green.log`.
This Server-only refinement requires a fresh real-Gateway acceptance run.

Real Win7 remains unexecuted, owner Neowyh, assigned to
[#131](https://github.com/Orbit-Crew/iDeer/issues/131). Pending Win7 scenarios are
T98-01 through T98-04 including browser handoff, Credential Manager, TLS/crypto,
signed reconnect, bundled process ownership and installed lifecycle. Modern
Windows evidence does not establish Win7 compatibility.
