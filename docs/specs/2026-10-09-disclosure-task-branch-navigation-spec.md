---
id: docs-specs-2026-10-09-disclosure-task-branch-navigation
kind: plan
status: archived
owner: repository maintainers
scope: evidence-led task-branch navigation within existing engineering documentation routes
last-verified: 2026-10-09
verified-against: docs/disclosure-dual-track @ dbd6c2df7099b11d9bd1406ff282bf01360b079d
triage: implementation-delivered; effect-gates-incomplete; optional-measurement-deferred-by-user
---

# 按具体改动分支引导文档阅读

## Problem Statement

维护者希望 coding agent 按实际改动找到相关约束和实现入口。九域短路由已经建立，但同一领域中仍有多个开发分支混在一起。例如 Chat 同时涉及提交门禁、SDK message chunk 组装、Gateway 事件和嵌入式跨模式去重。只知道任务属于 Chat，仍不足以判断该展开哪份材料。

最新阅读实验的常规任务 Markdown 去重读取量中位数为 99,857.5 → 88,068.5 字节，下降 11.8058%，未达到既有 30% 门槛。after 为 14/16 确认正确，另有未决和无效样本。这些结果支持继续定位过量阅读，但不能证明导航是全部剩余成本的原因。此前六场实作两侧均通过，也不能证明优化后开发更快。

## Solution

先用已保留的读取事件确定反复展开的资料、相关任务和可能原因，再将有证据支持的热点路由改成按具体改动分支选择资料的入口。每个分支说明触发条件、必须保留的不变量、当前契约章节、代码起点、条件决策和首验证。agent 能在任务边界明确后停止扩大文档阅读，转入源码核验。

本规格交付分支导航及其独立验收。根指引中 GitNexus 说明的精简由另一份规格处理。

## User Stories

1. As a coding agent, I want to choose a documentation branch from the behavior I will change, so that a broad domain label does not force unrelated reading.
2. As a Chat developer, I want submission-gate constraints separated from streaming constraints, so that I preserve duplicate rejection and subsequent-turn behavior without assuming every streaming rule applies.
3. As a Chat developer, I want SDK message chunk assembly and message identity ownership identified, so that I preserve incremental content and same-ID assembly.
4. As a Chat developer, I want Gateway event and recovery references triggered by Gateway work, so that I inspect the applicable event contract.
5. As a Chat developer, I want embedded cross-mode deduplication distinguished from SDK chunk assembly, so that I do not merge independent invariants.
6. As a Permissions developer, I want list visibility separated from role-operation authorization and approval flows, so that a list task does not require reading the entire permission design.
7. As a KnowledgeBase developer, I want list identity, visibility, and server-side provider-binding boundaries available together, so that I preserve the public resource contract.
8. As a test author, I want new-test placement separated from migration procedure, so that I read historical migration batches only when they inform my change.
9. As a developer changing several behaviors, I want all triggered branches combined, so that a short route does not hide a second applicable obligation.
10. As a developer with an ambiguous task, I want the unknown boundary made explicit, so that I verify source or clarify the task before assuming a branch is irrelevant.
11. As a coding agent, I want section-level contract links, so that locating one rule does not require reading its whole document.
12. As a coding agent, I want a clear transition to source verification, so that document navigation does not become an open-ended reading exercise.
13. As a reviewer, I want branch pointers to cite the current authority, so that an entry page does not become a competing contract.
14. As a maintainer, I want each navigation change tied to observed reading evidence, so that effort targets an actual problem.
15. As an evaluator, I want branch selection and applicable constraints checked independently, so that reduced reading cannot hide an incorrect answer.
16. As an evaluator, I want documentation and source costs reported separately, so that necessary source verification is not mistaken for navigation waste.
17. As an auditor, I want frozen inputs and reproducible reports, so that new measurements cannot silently change historical conclusions.
18. As a project owner, I want navigation delivery and measured reading improvement reported separately, so that a finished document edit is not presented as a passed effectiveness gate.

## Implementation Decisions

1. Retain the existing nine-domain entry structure and five stopping conditions. Add behavior-specific branches within the relevant short routes; do not introduce a tenth domain or a second global navigation system.
2. Start from the existing archived physical read events, candidate manifests, role maps, and final answers. Produce a hotspot table containing task identity, document/section, returned and unique bytes, repetition, applicability evidence, and the proposed change. Separate unrelated expansion, required contract reading, source verification, retries, and unknown causes; bytes alone do not establish irrelevance.
3. Prioritize the four previously observed hotspot domains: Chat, Permissions, KnowledgeBase, and Tests. Inspect the other domains for affected links and retained obligations. Expand their content only if the hotspot table supplies task-level evidence, and record why the scope changed.
4. Express branch triggers in terms of changed behavior. Each branch supplies applicable current-contract sections, relevant invariant ownership, a verified source start point, conditional decisions, and the first focused validation hop. Shared definitions remain in their current authority and are linked rather than copied.
5. Distinguish the four Chat branches of submission fencing, SDK chunk assembly, Gateway events/recovery, and embedded cross-mode deduplication. Identify the actual owner for each invariant. Reading a harness entry point does not itself mean the implementation edits the harness or triggers patch registration.
6. Distinguish resource list visibility, role-operation authorization, and visibility applications/approval. Retain visibility-before-pagination and filtered-count obligations where applicable. A visibility-list task does not automatically require approval-flow material.
7. Keep KnowledgeBase canonical identity, governance visibility, and server-side provider bindings discoverable on list/create branches. Trigger retrieval, publishing, and lifecycle material only when the described change touches those behaviors.
8. Separate adding tests, moving tests, and deleting tests. Preserve assertion strength, execution ownership, inventory, keeper/replacement evidence, and the migration ledger when triggered. Reading an old migration batch is conditional, not a prerequisite for every test task.
9. A task may trigger multiple branches; its applicable material is their union. When the description is insufficient, record the uncertainty and use narrow source verification or clarification. Do not infer that an uncertain branch is inapplicable, and do not require all domains to be read by default.
10. Preserve the five stopping conditions: source entry, current contract, triggered decisions, validation path, and unresolved state. Reaching them establishes a development starting point, not proof that an implementation is correct. Source findings may require reopening documentation.
11. Prefer clearer headings, trigger wording, and links inside the existing short page. Create a separate branch reference only when the current page cannot remain readable within its budget; retain a precise trigger pointer and section-level access. Keep the task index within 4 KiB and each domain short page within 6 KiB, measured as UTF-8 bytes.
12. Keep current, draft, superseded, and archived roles distinct. A route must not describe the same section as both a mandatory current contract and historical-only material. Resolve conflicts against the authoritative document's applicable sections, recorded decisions, and current source; preserve uncertainty if evidence cannot settle them. Preserve protected bodies, engineering terminology, global implementation obligations, and the test-lane contract. Update route registration and document indexes when an entry changes.
13. Reuse the existing section reader, frozen reading runner, scorer, and cost reporter. Do not repair or extend the experiment infrastructure as part of this feature. If a prerequisite cannot provide valid frozen evidence, report the effect run as blocked or incomplete and route the infrastructure problem separately.
14. Measure this feature against an immutable pre-edit navigation candidate. The reader-visible differences must be limited to this feature's navigation documents; keep root GitNexus guidance, product source, tests, prompts, and external evaluator tools identical. If the root-guidance feature is integrated first, freeze a new navigation baseline with that change already present. A combined candidate alone cannot establish the separate contribution of each feature.
15. Preserve old artifacts, scores, exclusions, and thresholds. Publish new implementation, governance, reading-correctness, and cost states separately, with task-level evidence and limits on generalization.

## Testing Decisions

1. The primary seam is a coding agent entering from the root/task index, using the existing public file/heading reader, and returning the applicable contract, source owner, conditional decisions, validation hop, and unknowns. Existing public document-check CLI tests provide the deterministic seam for registration and links. Do not introduce product API tests for a navigation-only change.
2. First construct and freeze a reviewer-only branch matrix against current contracts and source. Cover the four Chat branches, visibility versus role-operation/approval, KnowledgeBase list versus retrieval/lifecycle, test addition versus migration/deletion, a multi-branch task, and an ambiguous task. Each case specifies required and conditional anchors and material that is optional. Optional reading remains allowed and counted.
3. Non-scored branch pilots must show that each matrix branch is reachable, that the mixed task preserves the union of applicable constraints, and that uncertainty is reported for the ambiguous task. Prompts describe intended behavior and omit answer locations, route names, and rubric hints. Keep pilot evidence separate from formal samples.
4. Reuse the latest v2 eight-task prompts and two replicates per candidate for the formal comparison: 32 fixed slots, 16 per candidate, and the same ten routine slots per candidate for the pooled Markdown unique-byte median. Freeze exact prompt hashes, model alias/reasoning/CLI, role map, tool hashes, queue order, rubric version, and candidate manifests before dispatch; exclude this specification, hotspots, answers, and evaluator materials from reader inputs.
5. Correctness passes only when all 16 after answers meet applicable required anchors, with zero critical errors, zero historical-authority misuse, and no unresolved adjudication. Preserve the fixed denominator. The formal eight-task result and the more specific branch-matrix result are separate evidence; one does not substitute for the other.
6. The cost goal retains the existing 30% reduction in the pooled ten-slot routine Markdown unique-byte median against this feature's frozen baseline. Report per-task, source/test/config, repeated-return, and all-physical costs as well. A lower root/page size or fewer opened files alone cannot satisfy this gate.
7. Both correctness and cost must pass to claim measured navigation improvement. Missing submission/cost evidence or tool drift makes the affected gate incomplete; a measured reduction below 30% fails the cost gate. Use existing frozen timeout, quota-stop, and retry rules. Wrong answers and timeouts cannot be redrawn.
8. Use the current two independent semantic reviews and adjudication process. Establish conditional applicability before scoring; unresolved applicability remains visible rather than becoming an assumed pass or fail. Recompute medians and summaries from raw records in an independent directory.
9. Run document hygiene, current-candidate links and anchors, route completeness, guidance mirror checks, protected fingerprints, and explicit route/index size checks. Include negative CLI fixtures for missing branch targets or broken section links only when checker behavior changes; avoid tests that pin exact prose or heading counts.
10. Existing collector tests for heading reads and authorization, document-check CLI fixtures, the v2 scoring tests, and cost/archive recomputation tests are prior art. If an existing public checker must change, use a focused red/green regression at that CLI boundary and the narrowest static check; retain existing assertions.
11. Run the applicable standard lane for actual checker/tool code changes and the final integration `pr-standard` once on a frozen candidate. Pure document slices use document checks, not a repository-wide lane per slice. Report Real E2E selection from actual integrated paths. Do not rerun a successful unchanged candidate without a new reason.
12. Retain raw attempts, manifests, answers, reviews, and recomputation tools in a verified portable archive. Verify a worktree-external copy and report backup durability. Do not launch model sessions until the configured destination and payload are covered by existing authorization.

## Out of Scope

- Changing production UI, resource authorization, Run/Thread lifecycle, message streaming, or test-lane ownership.
- Compacting root GitNexus guidance, changing GitNexus commands, or weakening impact/change-analysis requirements.
- Repairing evaluator freezing, process supervision, timing, report generation, or backup infrastructure identified in retrospective items 1–4 and 7.
- Rewriting protected bodies, duplicating authoritative contracts, or routing every task through all historical decisions.
- Claiming general development speed gains, cross-model stability, or a passed historical legacy gate from this experiment.
- Adding a new practical coding acceptance exercise; the maintainer confirmed existing CLI checks plus reading acceptance as the validation boundary.
- Splitting tickets, running the feature, or starting model-backed acceptance as part of specification publication.

## Implementation status record (2026-10-09)

The four NAV route edits were delivered in after candidate `f10b0c525eb1438d043951a30d19a99986761286`. The immutable comparison baseline is `73a2a168fa08cf1854d60d1ceff41c4b572f63a6`; the reader-visible candidate difference is limited to the Chat, KnowledgeBase, Permissions, and Tests route pages. The existing task-routing index remains within its 4 KiB budget, and all four route pages remain within their 6 KiB budgets.

The non-scored branch matrix reached all 13 named branches, one mixed task, and one ambiguous task. The formal 32-slot comparison remains incomplete: slots 11–13 ended as quota failures under the fixed protocol, after has 11 correct and 3 incorrect answers among 14 submitted, and baseline has 13 correct and 2 incorrect among 15 submitted. C adjudicated all 18 disagreements. The after routine Markdown sample has 9 of 10 valid answers, so the 30% cost threshold cannot be evaluated. The report records the independent cost recomputation, archive hashes, restoration, and evidence limits in [ticket 05's acceptance report](../experiments/disclosure-branch-navigation-acceptance-2026-10-09.md).

The document edits are delivered. The measured-effectiveness gates remain incomplete; they do not determine whether the implementation was delivered. This record does not claim that NAV caused a difference between the incomplete candidate samples, or that the separate root GitNexus-guidance specification is complete.

## Implementation closeout (2026-10-10)

The user ended further ROOT model reading and directed engineering closeout. NAV remains delivered with its formal-effect results incomplete: final scoring is 13/16 baseline and 11/16 after, with three permanent quota failures in the fixed denominator; reading cost is incomplete because only 9/10 after routine answers are valid. The 15 non-scored branch pilots and eight second-action probes are reachability evidence only. Because wording changed in item 05, they do not establish a causal effect. No NAV slot was retried, replaced, or removed. Details remain in the [NAV acceptance report](../experiments/disclosure-branch-navigation-acceptance-2026-10-09.md).

Status `archived` means implementation work is recorded and no further experiment is scheduled by this decision. It does not mean the measured-effectiveness gates passed. Optional future measurement would require a separately authorized plan and must preserve the frozen queue and its permanent failures.

## Further Notes

- This is retrospective item 5. The baseline reference is `docs/disclosure-dual-track @ dbd6c2df7099b11d9bd1406ff282bf01360b079d`; it identifies the completed prior candidate, not a passed reading-effectiveness result.
- Current navigation: [task index](../agents/task-routing.md), [Chat](../agents/routes/chat.md), [Permissions](../agents/routes/permissions.md), [KnowledgeBase](../agents/routes/knowledge.md), and [Tests](../agents/routes/tests.md). The [domain glossary](../../CONTEXT.md) and [decision index](../decisions/README.md) remain authoritative for terminology and decisions.
- Sources: [latest four-state verdict](../experiments/disclosure-dual-track-ticket10-final-verdict-2026-10-09.md), [formal reading result](../experiments/disclosure-dual-track-ticket07-results-2026-10-08.md), and [practical/legacy conditional result](../experiments/disclosure-dual-track-ticket08-results-2026-10-09.md). Raw evidence locations and known limits are recorded there.
- A concrete navigation conflict to resolve is the current Permissions route: it links permission-model sections 2–4 as current contracts while its historical qualifier also includes sections 2–5. Resolve section applicability explicitly; do not simply reclassify the whole source document or rewrite its protected content.
- The current public seams are `scripts/check_documents.py`, `scripts/disclosure_reading_collector.py`, `scripts/run_disclosure_reading_session.py`, `scripts/score_disclosure_reading_v2.py`, and `scripts/report_disclosure_costs.py`. Their public behavior is reused rather than replaced.
- Publication follows [local specifications and work tickets](../agents/issue-tracker.md): this draft has `triage: ready-for-agent`; it is not a new current behavioral contract.
- Related independent specification: [root GitNexus guidance compaction](2026-10-09-root-gitnexus-guidance-compaction-spec.md). The two implementations may be sequenced, but independently attributed effects require separate frozen comparisons.
