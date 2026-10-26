# Repo Guide

## Guidance

`AGENTS.md` is sole rule source; `CLAUDE.md` its UTF-8 mirror. Merge copy-only rules first. After edits run `python3 scripts/sync_agent_guidance.py --write` then `--check`. Move/delete both and inspect orphan mirrors. CI checks, never repairs. Team rules belong on `develop`/product branches; pure upstream `main` gets fast-forward mirrors. After upstream merges inspect divergent pairs; daily GitNexus uses `--index-only`.

## Implementation discipline

Keep changes scoped and follow nearby conventions. Before editing, state approach, assumptions and result-changing choices with a recommendation; ask only when evidence cannot resolve a blocker. Surface adjacent defects, cheaper designs and fitting utilities. Prefer the smallest complete change, define observable checks and report results. Long-span tasks and blocked batches use `orchestrate-worktrees`, one worktree/agent per ticket.

## Skill routing

Route open designs to `grill-with-docs`, hard bugs to `diagnosing-bugs`, multi-session features to `to-spec` → `to-tickets` → `orchestrate-worktrees`, request piles to `triage`, reviews to `code-review`, fuzzy terms to `domain-modeling`, huge efforts to `wayfinder`; propose `retro` after completed builds. Full map: [skill routing](docs/agents/skill-routing.md). Validation contracts remain binding; small specified changes use focused TDD.

## Paths

iDeer uses `backend/` (FastAPI/LangGraph), `frontend/` (Next.js routes/UI/domain), `scripts/`, `docker/`, `docs/`, and runtime skills in `resources/skills/`; `skills/public/` is upstream landing zone only. Follow backend and frontend `AGENTS.md`.

Commands: `make setup|install|dev|start`, `make docker-start|docker-stop`; backend `make test|lint`; frontend `pnpm test|test:e2e|check`. Backend Python 3.12/ruff; frontend TypeScript/React/Next/ESLint/Prettier. Use snake_case, camelCase functions, PascalCase components, `use*` hooks; logic in `src/core/`, UI in `src/components/`.

## Testing and delivery

Backend `test_*.py` files go in `backend/tests/{unit,integration,contracts}`; frontend tests mirror `src/` under `tests/unit/` or use `tests/e2e/`. Each slice: identify the public seam, add one focused regression, prove failure, implement minimally, then pass it and the narrowest static check. At completion run the applicable standard lane once; no repository-wide lane per slice. Before a lane run `python3 scripts/test_preflight.py <lane>` (runner does this automatically); after adding/moving tests run `python3 scripts/test_inventory.py`. Select lanes by behavior and stage. Combined lanes replace included base lanes on the same candidate. See [runbook](docs/testing/test-lane-runbook.md), [coverage](docs/testing/coverage-matrix.md), [inventory](scripts/test_inventory.py), [migration ledger](docs/testing/test-migration-ledger.md). Reuse only on the same candidate, dependencies, config and environment; rerun after relevant changes or incomplete evidence. Preserve coverage. Smoke is a mock E2E subset; missing credentials are unexecuted.

Contracts, authorization, persistence, migrations and core runtime need matching contract/integration checks. Auth, RBAC, persistence, memory, admin, Agent, Skill and Workflow need matching standard lane plus `pr-standard`, the cross-stack gate. GitHub Actions selects Real E2E for protected high-risk paths; report its selection at handoff. `core-full` is for explicit release/delivery/full acceptance only. Restricted backend commands use `UV_CACHE_DIR=/tmp/deer-flow-uv-cache`. If sandbox denies a socket test, report and rerun where local sockets work; do not bypass by changing code/tests. For hangs/timeouts report command, elapsed time and last test. For `pr-standard`/`core-full`, report sub-lane summaries and parent `TEST_LANE_DURATION`. Before pushing a candidate, replay the CI document gates locally: `python3 scripts/check_documents.py` and `python3 scripts/check_upstream_patches.py --base <current develop tip> --upstream-baseline 345f08be00c8a9495079b732a39b46aa9af1584e` (new tracked `.md` needs a [document-policy](docs/governance/document-policy.json) registration; a develop governance sweep re-anchors the ledger `previous_*` allocation).

## Compatibility

Keep enterprise behavior at Extension → Adapter → registered minimal runtime patch. Preserve Run/Thread lifecycles, streaming, tools, restoration and persistence. Config states offline capabilities and permission limits and reports effective state. Validate with customization off and enterprise limits on. Log each harness patch's reason, alternatives, impact, validation, owner and removal condition. Resolve conflicts per behavior/contract; report sync, integration and compatibility separately. Registration does not prove compatibility.

KnowledgeBase list/create uses `/api/resources` with Resource Governance visibility; responses expose canonical identity/visibility and keep provider bindings server-side. Qodo Cover configs are local assets. Stagehand E2E (`frontend/tests/e2e/stagehand/`) uses its specialty lane. Archived validator designs are not callable skills.

## Task documentation

Follow the [task route](docs/agents/task-routing.md) for contract, decisions, code and validation. Its five stops start source verification, not proof. Root owns global rules; routes own domain references. Terms: [CONTEXT.md](CONTEXT.md); UI display terms: [term table](docs/plans/2026-08-26-term-glossary.md). Docs index: [docs/README.md](docs/README.md). ADRs are in `docs/adr/`, dated decisions in `docs/decisions/`, indexed in their README. Current docs govern; drafts propose, superseded docs point forward, archives preserve history. Historical tests never validate current candidates. Update docs for behavior, interface, config, architecture or workflow changes.

## Commit, security and operations

Use Conventional Commits (`fix(scope): imperative summary`). PRs list behavior, checks, issues and visual evidence. Never commit secrets; use untracked local config and run `make doctor` for environment issues ([local ops](docs/agents/local-ops-notes.md#security--configuration)). Nginx loopback is public entry; bind new ports explicitly ([deployment](docs/agents/local-ops-notes.md#deployment)). Keep session artifacts in ignored `dev-log/`, never repo root; never force-add them ([session files](docs/agents/local-ops-notes.md#session--working-files-dev-log)). Test-account passwords equal their email; see [account table](docs/agents/test-accounts.md).

## Agent skills

### Issue tracker

Issues live in GitHub (`Orbit-Crew/iDeer`) and are synced to Gitea (`TechCode/iDeer`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **AgentPlatform** (101537 symbols, 206551 relationships, 1089 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- **Doc-only commits are exempt from re-indexing.** This exception applies only when every changed path ends in `.md` and the output is partial but not truncated; record that partial result in the commit message.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
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
