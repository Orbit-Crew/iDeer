---
id: disclosure-scoring-rubric-2026-10-07
kind: policy
status: current
owner: repository maintainers
scope: human scoring of progressive-disclosure reading answers
last-verified: 2026-10-07
verified-against: worktree @ 59903d76e64d822cb807adb646758cb0184b141c
---

# Progressive disclosure scoring rubric

This is coordinator material. Calibration graders receive it; timed readers and formal reading evaluators must not. The ticket 02 collector must deny this file and scoring fixtures before a formal session begins. A candidate hash does not make scorer material safe to expose.

## Scoring procedure

Review each six-field answer independently against the exact candidate's current documents. Record a decision and both an answer excerpt and candidate source evidence for every numbered anchor. Use `met`, `missed`, or `not_applicable`; the latter is valid only for a conditional anchor whose stated trigger is false. A correct synonym earns `met` when it preserves the anchor's meaning. A generic pointer earns credit only if it identifies the applicable route and enough concrete detail to start safely. Do not require exact wording, exhaustive references, or irrelevant details.

The anchor IDs, accepted candidate sources, severity, and applicability are fixed below. `critical` denotes a materially unsafe or misleading omission or claim, including reversal of an authorization, identity, lifecycle, persistence, compatibility, or evidence invariant. `major` denotes a required central route or constraint. `minor` denotes useful validation or supporting context. A missed required anchor makes the answer incorrect. A conditional anchor is required only when its explicit trigger applies. Optional anchors never affect correctness. Any missed critical anchor counts as a critical error. Separately, reviewers flag historical-authority misuse only when the answer positively uses a superseded, archived, draft, accepted-decision, or historical-test claim as evidence of current behavior or validation. An omitted history anchor is incorrect where required, but is not automatically historical misuse. Historical misuse can occur in any task class.

Each answer gets two independent reviews, with distinct reviewers and separate access to the answer and candidate evidence. Each anchor decision must include an answer excerpt and candidate source evidence. Each reviewer separately records whether the answer commits historical-authority misuse and, if so, its evidence. Compare anchor decisions, conditional triggers, and the misuse judgment. Any difference requires a third reviewer. The adjudicator must be independent, include a rationale, cite the answer and candidate evidence, and decide disputed judgments under this rubric. Do not average grades. If the evidence or rule cannot resolve a disagreement, retain it as unresolved and the candidate cannot pass.

The CLI derives correctness from human-entered anchor decisions; it does not inspect answer keywords. It checks record shape, anchor coverage, explicit conditional triggers, reviewer separation, sample completeness, and arithmetic. Its report is derived from the records. A supplied summary must match exactly or the CLI rejects the report. Preserve source answers, both initial reviews, and any adjudication alongside the generated report.

## Anchors

Candidate sources below establish the relevant answer evidence; code paths are entry points, not substitutes for the current contract. When candidate content conflicts, cite that conflict and follow its declared current authority. Never use an old score as the answer key.

### UI

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| UI-01 | Names a concrete component or route entry for the requested display change. | `docs/agents/task-routing.md` §1; `frontend/AGENTS.md` | major | required |
| UI-02 | Places UI composition in `frontend/src/components/` and domain behavior in `frontend/src/core/`. | root `AGENTS.md`, Project Structure | major | required |
| UI-03 | Applies frontend conventions and uses `CONTEXT.md` only when engineering terms need clarification. | `frontend/AGENTS.md`; `CONTEXT.md` | major | required |
| UI-04 | Names a focused Vitest check and `pnpm check`, then the applicable standard lane and PR gate. | `docs/agents/task-routing.md` §1; test lane runbook | minor | required |
| UI-05 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |

### Chat

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| CHAT-01 | Distinguishes duplicate-submit handling in `turn-submit.ts`, stream state in `hooks.ts`, and shared page wiring in `use-thread-page.ts`. | `docs/agents/task-routing.md` §2 | major | required |
| CHAT-02 | Preserves message-ID event deduplication when changing stream delivery or merge behavior. | `backend/docs/STREAMING.md` | major | required |
| CHAT-03 | Names the relevant front/back-end boundary and the concrete first source entry. | `docs/agents/task-routing.md` §2 | critical | required |
| CHAT-04 | Preserves Run/Thread lifecycle, persistence, and stream contracts. | root `AGENTS.md`, Enterprise changes; `THREAD_LIFECYCLE.md`; `RUN_EVENT_STREAM.md` | critical | conditional: task touches Run/Thread lifecycle, persistence, or event streaming |
| CHAT-05 | Identifies a focused backend/frontend check, matching standard lane, and `pr-standard`. | `docs/agents/task-routing.md` §2; test lane runbook | minor | required |
| CHAT-06 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |

### Knowledge

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| KB-01 | Uses `/api/resources` as the canonical list/create operation and preserves Resource Governance visibility filtering. | root `AGENTS.md`, Enterprise interfaces | critical | required |
| KB-02 | Keeps the canonical KnowledgeBase identity and visibility governance in AgentPlatform; provider index identifiers do not replace that identity. | root `AGENTS.md`, Enterprise interfaces; `docs/decisions/2026-09-08-knowledge-dual-source-of-truth.md` | critical | required |
| KB-03 | Leaves indexing state with the provider and keeps provider IDs as opaque server-side bindings, outside model-visible data. | same knowledge dual-source decision; root `AGENTS.md` | critical | required |
| KB-04 | Identifies the applicable resource or knowledge code entry and accurately labels conditional lifecycle decisions. | `docs/agents/task-routing.md` §4 | major | required |
| KB-05 | Names resource contract checks, matching standard lane, and `pr-standard`. | `docs/agents/task-routing.md` §4; test lane runbook | minor | required |
| KB-06 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |

### Permissions

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| PERM-01 | Uses the permission model and role/action matrix for authorization meaning. | `docs/permission-model-redesign.md`; `docs/permission-matrix.md` | critical | required |
| PERM-02 | Identifies relevant authorization, RBAC, visibility, or resource-service seams. | `docs/agents/task-routing.md` §3 | critical | required |
| PERM-03 | For device/local execution, separates server delegation from the local veto and says local DENY prevails. | `docs/decisions/2026-09-08-local-authorization-veto.md` | critical | conditional: task changes device or local execution authorization |
| PERM-04 | Preserves resource visibility and governance boundaries. | `docs/decisions/2026-08-14-resource-governance-v2.md`; root `AGENTS.md` | critical | conditional: task changes resource authorization or visibility |
| PERM-05 | Requires applicable contract/integration checks, the matching standard lane, and `pr-standard`. | `docs/agents/task-routing.md` §3; test lane runbook | minor | required |
| PERM-06 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |

### Tests

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| TEST-01 | Places tests in the documented layer and package. | `docs/testing/README.md`; root `AGENTS.md` Testing Guidelines | major | required |
| TEST-02 | Updates and runs inventory after adding or moving tests; updates the migration ledger when tests move or are deleted. | root `AGENTS.md`; `docs/agents/task-routing.md` §8 | major | conditional: task adds/moves tests; ledger clause applies to moves/deletions |
| TEST-03 | Selects a focused check and applicable standard lane through the runbook/coverage route; does not prescribe an indiscriminate full-suite run. | `docs/testing/test-lane-runbook.md`; `docs/testing/coverage-matrix.md` | major | required |
| TEST-04 | Uses evidence from the current candidate; a prior run does not validate it. | root `AGENTS.md`, Testing Guidelines | major | required |
| TEST-05 | Names the focused check and applicable standard/PR lane. | `docs/agents/task-routing.md` §8 | minor | required |
| TEST-06 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |
| TEST-07 | Recognizes that a combined lane replaces its included base lanes for the same candidate. | `docs/testing/test-lane-runbook.md` | minor | conditional: task selects a combined lane |
| TEST-08 | Recognizes that smoke is an aggregate subset of mock E2E. | `docs/testing/test-lane-runbook.md` | minor | conditional: task selects the smoke lane |
| TEST-09 | Reports missing optional credentials as unexecuted. | root `AGENTS.md`, Testing Guidelines | minor | conditional: selected lane needs unavailable optional credentials |

### Runtime

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| RUN-01 | Prefers Extension, then Adapter, then a registered minimal runtime patch. | root `AGENTS.md`, Enterprise changes and upstream compatibility | critical | required |
| RUN-02 | Preserves Run/Thread lifecycles, streaming events, tool execution, restoration, and persistence contracts. | same root section; runtime module guidance | critical | required |
| RUN-03 | Makes offline capability switches and enterprise permission limits explicit and reports their effective state. | root `AGENTS.md`, Enterprise changes and upstream compatibility | critical | conditional: task changes these switches or limits |
| RUN-04 | Verifies compatibility with customization disabled and enterprise constraints with it enabled. | root `AGENTS.md`; `UPSTREAM_PATCH_LEDGER.md` | major | required |
| RUN-05 | Names a concrete runtime code entry for the requested lifecycle change. | `docs/agents/task-routing.md`; `backend/packages/harness/deerflow/runtime/AGENTS.md` | major | required |
| RUN-06 | Names the relevant focused check and matching standard/PR lane. | root `AGENTS.md`; `docs/testing/test-lane-runbook.md` | minor | required |
| RUN-07 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |

### Upstream

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| UP-01 | Keeps `main` as a fast-forward mirror and places team/product guidance on `develop` or product branches. | root `AGENTS.md`, Guidance maintenance | major | required |
| UP-02 | Resolves each conflict by behavior and contract; does not select one side globally. | root `AGENTS.md`, Enterprise changes; `docs/agents/task-routing.md` §9 | critical | required |
| UP-03 | Records each harness patch's reason, alternatives, impact, validation, owner, and removal condition. | root `AGENTS.md`; `UPSTREAM_PATCH_LEDGER.md` | major | required |
| UP-04 | Prefers Extension, then Adapter, then a registered minimal patch. | root `AGENTS.md`, Enterprise changes | major | required |
| UP-05 | Preserves Run/Thread lifecycle, streaming events, tool execution, state restoration, and persistence when touching the harness runtime. | root `AGENTS.md`, Enterprise changes | critical | required |
| UP-06 | Tracks upstream sync, product integration, and compatibility validation separately; validates both customization modes. | root `AGENTS.md`; `docs/offline-product-line-governance-plan.md` | major | required |
| UP-07 | States a genuine unresolved detail or what source inspection must resolve; does not call already-routable facts unknown. | `docs/agents/task-routing.md`, stop conditions | major | required |

### History

| ID | Anchor | Candidate source | Severity | Category |
| --- | --- | --- | --- | --- |
| HIST-01 | Treats ADR 0007 as an accepted terminology constraint while distinguishing accepted decision from proof of current implementation or validation. | `docs/adr/0007-agent-terminology-unification.md`; `docs/decisions/README.md` | critical | required; a contrary current-status claim is historical-authority misuse |
| HIST-02 | Distinguishes the knowledge governance source from provider indexing state and does not treat provider dataset IDs as KB identity. | `docs/decisions/2026-09-08-knowledge-dual-source-of-truth.md` | critical | required; reversing the split is historical-authority misuse |
| HIST-03 | Uses current project-state evidence to state implementation status. | `docs/project-state.md` | major | required |
| HIST-04 | Uses the decision index and task route to identify current authority and labels historical reports as history. | `docs/decisions/README.md`; `docs/agents/task-routing.md` | major | required |
| HIST-05 | Supplies additional dated provenance when useful without treating it as a current contract. | applicable dated decision or report | minor | optional |
| HIST-06 | Distinguishes a genuinely unavailable historical fact from a fact already recorded in the decision index or status source. | `docs/decisions/README.md`; `docs/project-state.md` | major | required |

## Thresholds and report interpretation

The after denominator is always 16: two records for each of the eight task classes. An absent, interrupted, or timed-out after sample remains a failed sample and cannot be dropped. Pass requires all 16 after answers correct, zero after critical errors, zero after historical-authority misuse, no unresolved disagreement, and a routine five-class elapsed-time median no greater than 300 seconds. The reading-byte reduction for the same ten UI/Chat/Knowledge/Permissions/Tests records must be at least 30% against the corresponding baseline records. Use the ordinary median of the merged ten values, including the arithmetic midpoint for even sample counts; do not average per-task medians or filter failures.

The CLI accepts answer records, two independent anchor reviews, and a third adjudication when reviewers disagree. It derives the report from those individual records and rejects a supplied summary that differs. It does not infer semantic correctness from matching words. Keep each review, evidence note, adjudication, input, and generated report together for audit. The rubric is not part of timed evaluator input; ticket 02 owns the collector boundary that enforces this restriction.
