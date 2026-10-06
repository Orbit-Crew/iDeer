# Repository Guidelines

## Guidance maintenance

Edit `AGENTS.md` as the sole source in each rule directory. Run `python3 scripts/sync_agent_guidance.py --write` to produce its regular UTF-8 `CLAUDE.md` copy, then run `--check`. Both files have identical content, including this convention. Merge valid copy-only rules before writing. Handle both files when moving or deleting a directory; inspect orphan copies before deleting them. CI checks the candidate revision and never repairs or commits copies. Team guidance belongs on `develop` and product branches; pure upstream `main` receives only fast-forward mirror updates. After an upstream merge, check for divergent pairs and use GitNexus `--index-only` for daily indexing.

## Implementation discipline

Keep each change limited to the requested behavior and follow nearby conventions. Before editing, state the approach and its assumptions, identify any choice that changes the result, and present such choices with a recommendation; reserve blocking questions for what the evidence cannot resolve. When you notice an adjacent defect, a cheaper design, or an existing utility that already fits, surface it as a suggestion instead of silently expanding or shrinking scope. Prefer the smallest implementation that meets the acceptance criteria. Define completion in observable checks, then run those checks and report their actual status. Long-span work — a single task whose reading and implementation would not fit one context window, or a batch of tickets with blocking edges — goes through the `orchestrate-worktrees` skill (one self-contained subagent per ticket in a dedicated git worktree) instead of working inline.

## Skill routing

When a situation matches a routed skill, invoke it instead of improvising the process; small, well-specified changes go straight to the TDD slice discipline above. Skills change how work is prepared and reviewed, never what validation the test-lane contract requires; if a routed skill is not installed, follow the stated principle anyway.

| Situation | Route |
| --- | --- |
| New feature with open design questions | `grill-with-docs` |
| Hard bug resisting a first glance | `diagnosing-bugs` |
| Multi-session feature build | `to-spec` → `to-tickets` → `orchestrate-worktrees` |
| Incoming bugs and requests pile up | `triage` |
| Reviewing a diff, branch, or PR | `code-review` |
| Completed build, especially a bumpy one | propose `retro` |
| Fuzzy or overloaded domain term | `domain-modeling` |
| Huge, foggy effort | `wayfinder` |

The full map (including codebase-design, prototype, and research), phase boundaries, and precedence rules live in [docs/agents/skill-routing.md](docs/agents/skill-routing.md).

## Project Structure & Module Organization

iDeer is a full-stack agent application. `backend/` contains the Python FastAPI/LangGraph gateway, channel integrations, and tests in `backend/tests/`. `frontend/` contains the Next.js app: routes in `frontend/src/app/`, UI in `frontend/src/components/`, domain logic in `frontend/src/core/`, and tests in `frontend/tests/`. Shared scripts live in `scripts/`, deployment assets in `docker/`, public skills in `resources/skills/` — the authoritative skill tree that ships to the runtime; `skills/public/` is only the upstream landing zone and must not receive enterprise adaptations (see `skills/public/README.md`) — and planning material in `docs/`. Respect narrower guidance in `backend/AGENTS.md` and `frontend/AGENTS.md`.

## Build, Test, and Development Commands

- `make setup`: run the interactive setup wizard.
- `make install`: install backend, frontend, and pre-commit dependencies.
- `make dev`: start all local services with hot reload.
- `make start`: start the optimized production-mode local stack.
- `make docker-start` / `make docker-stop`: run or stop the Docker development environment.
- `cd backend && make test`: run backend pytest suite.
- `cd backend && make lint`: run ruff lint and format checks.
- `cd frontend && pnpm test`: run Vitest unit tests.
- `cd frontend && pnpm test:e2e`: run Playwright tests.
- `cd frontend && pnpm check`: run ESLint plus TypeScript checks.

## Coding Style & Naming Conventions

Backend code targets Python 3.12 and is formatted with ruff. Use snake_case for modules, functions, and test files; keep FastAPI gateway code under `backend/app/gateway/`. Frontend code uses TypeScript, React, Next.js App Router, ESLint, and Prettier with Tailwind sorting. Use PascalCase for components, camelCase for functions/hooks, and `use*` for hooks. Keep feature logic in `src/core/` and UI composition in `src/components/`.

## Testing Guidelines

Place backend tests in the relevant `backend/tests/unit/`, `backend/tests/integration/`, or `backend/tests/contracts/` package, using `test_*.py` filenames. Place frontend unit tests in `frontend/tests/unit/`, mirroring the relevant `src/` area, and E2E tests in `frontend/tests/e2e/`. Add focused tests for changed behavior and run the smallest relevant suite before broader checks.

### Test selection by risk and stage

Choose checks for the changed behavior and the stage of the work. For an ordinary local change, completion requires the focused regression test and the narrowest relevant type or lint check. Changes to public contracts, authorization, persistence, migrations, or core runtime behavior also need the matching contract and integration checks. Run one focused check per TDD slice. Run the applicable standard lane once when preparing the PR; retain `pr-standard` as the cross-stack PR gate. Use `core-full` only for an explicit release, delivery, or full-acceptance request.

A combined lane replaces its included base lanes for the same candidate. Reuse a successful result only when the candidate, dependencies, test configuration, and environment are unchanged. Rerun affected checks after relevant changes, failures, or incomplete evidence. Keep assertions and coverage intact; do not speed up a lane by weakening assertions, adding skips, or reducing its scope.

The lane contract and handoff rules live in [docs/testing/test-lane-runbook.md](docs/testing/test-lane-runbook.md). The [coverage matrix](docs/testing/coverage-matrix.md) maps behavior to test layers; the [test inventory](scripts/test_inventory.py) records discovered files, collected nodes, execution ownership, and status; the [migration ledger](docs/testing/test-migration-ledger.md) records test moves and deletions. After adding or moving tests, run `python3 scripts/test_inventory.py`; before a lane, run `python3 scripts/test_preflight.py <lane>` (the lane runner does this automatically). Smoke is an aggregate subset of mock E2E, not a second execution owner. Missing optional credentials are reported as unexecuted.

### Enterprise changes and upstream compatibility

Keep enterprise behavior at the extension boundary. Prefer, in order, Extension, Adapter, then a registered minimal runtime patch. Preserve Run and Thread lifecycles, streaming events, tool execution, state restoration, and persistence contracts. Offline capability switches and enterprise permission limits must be explicit in configuration and report their effective state. Verify compatibility behavior with customization disabled and enterprise constraints with it enabled.

For each harness patch, record its reason, alternatives, impact, validation, owner, and removal condition in the applicable patch ledger. Resolve upstream conflicts by behavior and contract; review each conflicted change instead of accepting one side globally. Track upstream synchronization, product integration, and compatibility validation as separate states. Contract and patch registration checks prove that changes are recorded, not that behavior is compatible; compatibility evidence comes from the relevant tests and review.

### Task documentation routing

Once the task domain is known, read the matching route in [docs/agents/task-routing.md](docs/agents/task-routing.md): for each of the nine common task domains it names the current contract, code entry point, conditional decisions, and the first validation hop, and states the stopping point where document reading ends and source verification begins. Engineering terminology is defined in [CONTEXT.md](CONTEXT.md); the [UI term table](docs/plans/2026-08-26-term-glossary.md) covers display-language copy only.

`docs/README.md` is the engineering documentation index. `docs/adr/` holds ADR records; `docs/decisions/` holds dated decisions, and both are indexed from the decisions README. Current documents govern active work. Drafts are proposals, superseded documents point to their replacement, and archived records provide history only. A historical test result never satisfies validation for the current candidate. Update documentation when behavior, interfaces, configuration, architecture, or workflow changes.

### Agent implementation checks

For each implementation slice, identify the public seam, add one focused regression test, verify it fails, implement the smallest change, and verify it passes. After each slice, run only that test and the narrowest relevant static check. At implementation completion, run the applicable standard lane once. Use `UV_CACHE_DIR=/tmp/deer-flow-uv-cache` for backend commands in restricted environments. If a socket test is denied by the sandbox, record the environment result and rerun the same lane where local sockets are permitted; do not alter product code or tests to bypass the restriction.

For auth, RBAC, persistence, memory, admin, Agent, Skill, or Workflow changes, run the matching standard lane and `pr-standard`. GitHub Actions selects Real E2E for protected high-risk paths; report that selection when handing off a pull request. Do not run a repository-wide lane for each TDD slice.

For a focused test or lane that hangs or times out, report it as incomplete with the exact command, elapsed time, and last observed test. Distinguish focused, standard-lane, PR-lane, and delivery-lane results. For `pr-standard` and `core-full`, report each sub-lane's final summary and the parent lane's `TEST_LANE_DURATION` status.

## Enterprise interfaces and validation assets

KnowledgeBase list and create operations use `/api/resources` with Resource Governance visibility filtering. Responses expose canonical identity and visibility; provider infrastructure bindings stay server-side. Preserve these boundaries when editing Knowledge Center behavior.

Qodo Cover configurations are local validation assets. Stagehand tests live in `frontend/tests/e2e/stagehand/` and require their explicit specialty lane. The archived `frontend-validator`, `backend-validator`, `qa-tester`, and `validation-orchestrator` designs are historical proposals, not callable skills in this worktree.

## Commit & Pull Request Guidelines

Git history primarily uses Conventional Commit prefixes such as `fix(runs): ...`, `fix(frontend): ...`, and `fix(sandbox): ...`. Prefer `type(scope): summary` with a concise imperative summary. Pull requests should describe the user-visible change, list validation commands, link related issues, and include screenshots or before/after artifacts for visual changes.

## Security & Configuration Tips

Do not commit local secrets; keep local values in untracked config files and run `make doctor` before reporting environment issues. Details: [local ops notes](docs/agents/local-ops-notes.md#security--configuration).

## Deployment Notes

Nginx on loopback is the single public entry; any new published port needs an explicit bind address. Details: [local ops notes](docs/agents/local-ops-notes.md#deployment).

## Session / Working Files (dev-log)

Session artifacts belong in git-ignored `dev-log/`, never the repo root; never `git add -f` them. Details: [local ops notes](docs/agents/local-ops-notes.md#session--working-files-dev-log).

## Test Accounts (密码 = 邮箱名)

Role verification needs a seeded local DB; passwords equal emails. Table: [test accounts](docs/agents/test-accounts.md).

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **AgentPlatform** (47479 symbols, 96181 relationships, 886 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact analysis before editing.** Use `impact({target: "symbolName", direction: "upstream"})` (MCP) or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .` (CLI fallback); report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "product/offline-1.x"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "product/offline-1.x" --repo .`.
- **Doc-only commits are exempt from re-indexing.** A commit that touches only Markdown documentation files (every changed path ends in `.md` — e.g. `docs/`, `README.md`, `AGENTS.md` — with no code, config, workflow, script, or test changes) satisfies detect-changes by recording its `partial` result in the commit message — no re-index (`--index-only`) is required, and this is the only case where a `partial` result is acceptable. Every other commit must still follow the full MUST above.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/AgentPlatform/context` | Codebase overview, check index freshness |
| `gitnexus://repo/AgentPlatform/clusters` | All functional areas |
| `gitnexus://repo/AgentPlatform/processes` | All execution flows |
| `gitnexus://repo/AgentPlatform/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
