# Test lane result consistency

This record covers ticket T1 from [the first test system batch](../specs/2026-10-02-test-system-first-batch-spec.md). The candidate started at `a1bb73afee6a0e3b1683deb1b326276fe3dda37f`.

## Change

The Stagehand lane now records `unexecuted` in its evidence and CI summary when credentials are missing, while preserving exit code 0. The runner completes evidence before it prints the final duration, metadata, and summary. An evidence completion error changes a successful test run to exit code 1; when tests already failed, their exit code remains and the runner reports the evidence error. Completion writes use a same-directory temporary file and atomic replacement, so a failed publish leaves the start record incomplete.

## Red and green evidence

The runner subprocess regression was first run against the original implementation. It produced 4 failures in 23.84 seconds: the Stagehand evidence said `passed`, evidence failure left duration status at 0, evidence failure was not reported after a test failure, and summaries had no outcome.

The completion writer regression was also run before its change. Its injected `os.replace` failure did not raise because the original writer wrote directly to the evidence file. After the atomic-write change, the same test passed in 3.47 seconds and confirmed that the original start record remained incomplete.

On the changed candidate, the focused runner command passed all 4 cases in 20.74 seconds:

```bash
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests \
uv run --no-sync pytest tests/unit/scripts/test_run_test_lane.py -q
```

The evidence writer file passed all 4 tests in 6.26 seconds on the final candidate:

```bash
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests \
uv run --no-sync pytest tests/unit/scripts/test_test_lane_evidence.py -q
```

The targeted atomic-publish test passed separately in 3.47 seconds. Ruff passed for the changed Python files, and `bash -n scripts/run-test-lane.sh` exited 0. `python3 scripts/test_inventory.py` exited 0; `--collect --json` also listed all four runner cases and all four evidence writer cases.

The runner cases cover missing credentials, successful tests with evidence failure, failed tests with evidence failure, and ordinary success. Fault injection stays in the runner's Python child process. The PR lane and Mock E2E full lane remain part of T7's final validation.

## Environment

The worktree used independent backend and frontend dependencies. `uv sync --locked` and pnpm 10.26.2 frozen-lockfile installation completed. The model configuration used an offline loopback placeholder, with no real credentials. The configuration SHA-256 was `89516072f7ee914e7caafcf50fe96e41c128d1f1d7f6d1664288248721dc2098`; `frontend/.env` SHA-256 was `b0dae7d39a2134a6459986bbadb9801b3d307fe354547a58577457e67fb36184`. The allowed-environment Mock preflight and offline-config Doctor both exited 0; Doctor reported 3 warnings. The restricted-environment Chromium/socket preflight failed, so browser validation remains outside T1.
