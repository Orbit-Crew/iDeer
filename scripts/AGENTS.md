## Test entry contracts

`test_preflight.py <lane>` is a read-only, fail-fast check for the selected
lane. It checks locked tooling, framework plugins, browser availability,
writable runtime directories, and (for browser/service lanes) local socket
binding. It never installs packages or contacts application services. Socket,
browser, lockfile, and package-manager failures are always fatal; rerun the
same lane in an environment that permits local sockets when necessary.
`pnpm_command.py` is the single resolver for both preflight and lane execution:
it uses `TEST_PNPM_BIN`, then PATH pnpm, then `corepack pnpm`. `test_inventory.py --json` is the
static ownership report; `collection_status: static-only` keeps tests with
unavailable credentials visible rather than silently dropping them.
`check_test_contracts.py` is the cheap CI gate for missing ownership, base-lane
overlap, and stale runner/package entry names; it must pass before an expensive
lane starts.

## Service Startup Contracts

Optional browser dependency detection reads the top-level `tools:` sequence
without requiring `name` to be its first mapping key. Both indented and
indentless lists are supported; nested option names and block-scalar text
must not enable the browser extra. Keep the detector standard-library-only
because it runs before dependency synchronization. Read UTF-8 config files
with or without a leading BOM so the first section remains detectable.
`setup-sandbox.sh` also strips the leading BOM and normalizes CRLF before selecting the image;
keep its shell filter compatible with GNU and BSD sed.

The root `PORT` value configures Docker's published nginx ingress only; local
orchestration pins Next.js to `3000`. Runtime commands launch from the already
synchronized environment with `uv run --no-sync`. Production Compose probes
Gateway `/health`, and `deploy.sh` waits for all services before reporting
success; failures print Compose status and recent Gateway logs.

## Shell Script Invocation Contract

Root Makefile recipes must invoke repository `.sh` files through
`RUN_SHELL_SCRIPT`. On POSIX this expands to `$(BASH)`; on Windows it uses the
Git Bash wrapper. Shell scripts that invoke sibling repository scripts must
likewise prefix the target with `bash`. This keeps documented `make` commands
working when a source archive, `core.fileMode=false`, or a non-POSIX filesystem
does not preserve executable bits.

Host-side pnpm calls must go through `scripts/pnpm.py`. With native Windows
Python (`os.name == "nt"`), it checks `pnpm.cmd` before the generic `pnpm`
lookup, which uses `PATH`/`PATHEXT` and may select an `.exe` or `.bat` in the
same or an earlier PATH directory. If neither is found, it falls back to
Corepack, checking `corepack.cmd` before `corepack`. POSIX Python (including
MSYS/Cygwin Python) keeps the generic name first for each tool; the gate is
based on Python's `os.name`, not the invoking shell.

## Public Skill Review Waivers

`review_changed_public_skills.py` keeps the analyzer strict and applies narrow
CI-only exceptions from `.github/skill-review-waivers.v1.json`. The manifest is
versioned by `contracts/skill_review/waiver_manifest.v1.schema.json`; each entry
must identify one current error by package, source, rule, path, line, and
evidence, and pin the complete source file with SHA-256 plus an expiry date.
An optional, bounded `preapproved_file_sha256s` list authorizes reviewed future
full-file digests without relaxing the exact finding match. Blockers are never
waivable, and waived errors are still printed with their original severity and
justification.

For pull requests, only the base revision's manifest is effective. The head
manifest is parsed and checked against the current analyzer output, but cannot
self-authorize a finding in the same pull request. Push comparisons use the
same before/after trust boundary. Preapproved digests must be code-reviewed in
that first change; after the corresponding file revision lands, promote the
consumed digest to `file_sha256` and remove it from the preapproval list.

## Backend Static Analysis Commands

Two read-only detectors inventory backend async-execution safety; both print
a concise summary and write complete versioned JSON under `.deer-flow/`.
Their full target semantics — the thread-boundary `boundary_kind` inventory
and AST/runtime coverage, the blocking-IO reachability and alias-tracking
algorithms (bare-name resolution, `ast.If`-only branch isolation,
enclosing-scope definition-time expressions, unconditional lambda/generator
scanning outside definition-time contexts), and the per-anchor runtime-gate
inventory — are maintained in
[backend/docs/BLOCKING_IO_DETECTION.md](../backend/docs/BLOCKING_IO_DETECTION.md);
read it before changing either detector, its support modules, or a runtime
anchor, and preserve its conservative over-report-rather-than-infer stance.

- `detect-thread-boundaries` (root Makefile) statically inventories execution
  boundaries under `backend/app/` and `backend/packages/harness/deerflow/`
  into `.deer-flow/thread-boundary-inventory.json`. Implementation and
  coverage: `tests/support/detectors/thread_boundaries.py` and
  `tests/test_detect_thread_boundaries.py` (under `backend/tests/`).
- `detect-blocking-io` (root or `backend` Makefile; both resolve to the same
  repo-root output `.deer-flow/blocking-io-findings.json`) AST-parses
  `backend/app/`, `backend/packages/harness/deerflow/`, and `backend/scripts/`,
  reporting only candidates on async-reachable paths. Findings are review
  candidates: `priority` is a deterministic review ordering from operation
  type, not proof of a bug. It is intentionally informational and not run
  from CI.
- `scripts/scan_changed_blocking_io.py` scopes the same findings to the
  added lines of `git diff <base>...HEAD` plus findings new versus the merge
  base (so a new async caller exposing an untouched sync helper in the same
  file is still reported) — the deterministic scope step used by the
  `blocking-io-guard` skill (`.agent/skills/blocking-io-guard/`) before
  routing each candidate to a fix and/or a `tests/blocking_io/` runtime
  anchor.
- Runtime gate (`tests/blocking_io/`): every item runs under a strict
  Blockbuster context scoped to `app.*` and `deerflow.*` (see
  `tests/support/detectors/blocking_io_runtime.py`). Any sync blocking IO
  call whose stack passes through DeerFlow business code while running on
  the asyncio event loop raises `BlockingError` and fails the test;
  `@pytest.mark.allow_blocking_io` is the only opt-out, and
  `test_gate_smoke.py` pins both. The gate only sees code that test
  execution actually touches; static AST coverage is a separate concern. CI
  hard-fails every PR via
  [.github/workflows/backend-blocking-io-tests.yml](../.github/workflows/backend-blocking-io-tests.yml).

Regression tests related to Docker/provisioner behavior:
- `tests/test_docker_sandbox_mode_detection.py` (mode detection from `config.yaml`)
- `tests/test_provisioner_kubeconfig.py` (kubeconfig file/directory handling)
- `tests/test_provisioner_request_threading.py` (keeps provisioner sandbox CRUD
  endpoints as sync FastAPI handlers so synchronous K8s client calls run in the
  Starlette worker pool instead of on the ASGI event loop)

Blocking-IO runtime gate:
- Regression anchors live under `tests/blocking_io/` (under `backend/tests/`);
  the per-anchor inventory — what each test locks, including the #1917 and
  #1912 fixes — is maintained in
  [backend/docs/BLOCKING_IO_DETECTION.md](../backend/docs/BLOCKING_IO_DETECTION.md)
  alongside the gate mechanics.

Boundary check (harness → app import firewall):
- `tests/test_harness_boundary.py` — ensures `packages/harness/deerflow/` never imports from `app.*`

Memory backend async boundary:
- `MemoryMiddleware.aafter_agent` calls `MemoryManager.aadd`; network-backed
  managers must override their `a*` methods to offload or use native async I/O.
- The mem0 backend requires an HTTPS `base_url` by default because requests
  carry an API token. Plain HTTP requires the explicit
  `backend_config.allow_insecure_http: true` local-development opt-in.
- Gateway memory routes offload the synchronous management contract with
  `asyncio.to_thread`, so backend file or HTTP I/O does not run on the ASGI
  event loop. Gateway startup and shutdown also resolve the manager off-loop,
  because a backend's `from_config` may perform a fail-fast connectivity check.
- A backend may set `requires_passive_writes_in_tool_mode = True` when tool-mode
  search is supported but durable writes still depend on conversation-level
  extraction. Such backends receive memory tools and retain `MemoryMiddleware`.
- Prompt recall rethrows `MemoryManagerError` only when backend config declares
  `failure_policy.read: fail_closed`; other recall errors preserve the existing
  log-and-empty-context behavior.

CI runs these regression tests for every pull request via [.github/workflows/backend-unit-tests.yml](../.github/workflows/backend-unit-tests.yml).

Agentic browser sessions are process-local. The Gateway startup safety gate rejects
`GATEWAY_WORKERS > 1` when `browser_navigate` is configured, because ordinary
uvicorn worker dispatch does not provide thread affinity for browser tools, REST
navigation, and the Live WebSocket.

Browser Live screenshots remain JPEG bytes inside the harness and the Gateway's
bounded, drop-oldest frame queue. WebSocket clients that request
`frame_format=binary` receive binary messages; control metadata remains JSON.
The legacy no-parameter protocol still base64-encodes frames into JSON at the
Gateway boundary for backward compatibility. Unknown `frame_format` values
receive a JSON error and close code 1008.
