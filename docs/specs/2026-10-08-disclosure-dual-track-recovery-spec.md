---
id: docs-specs-2026-10-08-disclosure-dual-track-recovery
kind: plan
status: draft
owner: repository maintainers
scope: reliable progressive-disclosure reading tools, focused guidance, and dual-track acceptance
last-verified: 2026-10-08
verified-against: disclosure-readability-recovery @ 5687f8b90b96de73887e91e3984ad74d0772a01b
triage: ready-for-agent
---

# 渐进式文档披露双轨修复规格

## Problem Statement

上一轮 32 槽阅读实验已完成，但 after 只有 14/16 正确，常规任务总读取字节中位数从 151647 增至 176095.5。一个 Chat 答案漏掉已读到的消息去重约束；另一个 Chat 槽首次遭遇工作区加载及记录读取故障，最终重试报模型服务额度耗尽，未提交答案。记录器与运行器并发读写 JSON 还使其他槽失败。实验不能将所有失败归为文档，也不能把工程交付当作阅读效果达标。

16 个 after 会话全部读完 17370 字节的九域路由页，根指引只缩短 202 字节；Permissions、Tests、Knowledge 仍读了整篇大文档或源码。旧口径将文档与源码混算，且抽象 UI 题在没有指定组件时要求具体组件。维护者需要可靠的实验、可按需读取的文档，以及能检验真实开发工作的新版评价，同时保留旧门槛供独立对照。

## Solution

修复现有收集器和运行器；增加按标题读取与分层成本报告；精简根指引和九域路由，修正已证实的长文档入口与 Chat 不变量；以具体场景运行新版阅读与小型实作验收。新版通过后再运行旧口径。历史原始记录和评分不变，补充故障归因勘误。

## User Stories

1. As a coding agent, I want the root guidance and task index to point to my task's short page, so that I can stop expanding documents once the relevant contract, source entry, condition, and validation are known.
2. As a coding agent, I want to read a named Markdown section, so that a link to a section does not force a full-file read.
3. As a Chat developer, I want submission fencing, SDK message assembly, Gateway streaming, and embedded cross-mode deduplication distinguished, so that I preserve the invariant my change touches.
4. As a Permissions developer, I want current authorization rules and matrix sections separated from design history, so that I can verify visibility before pagination without reading unrelated proposals.
5. As a Tests developer, I want the migration procedure before the historical ledger, so that I can move a test without reading every old migration.
6. As a Knowledge developer, I want the list operation and visibility seam, so that I inspect the relevant source range rather than a whole large router.
7. As an evaluator, I want atomic, durable records and child cleanup, so that infrastructure errors cannot masquerade as wrong answers or erase submissions.
8. As an evaluator, I want failure classes, retries and service interruptions retained, so that I can resume a frozen queue without redrawing wrong answers.
9. As a scorer, I want required, conditional, and auxiliary anchors separated, so that an irrelevant omission does not make a correct task answer fail.
10. As a reviewer, I want two independent grades and adjudication, so that semantic disagreement is visible and resolved against frozen evidence.
11. As a maintainer, I want Markdown, source, duplicate returns, and actual attempt costs reported separately, so that the cost of source verification is not presented as document cost.
12. As a maintainer, I want real UI, Chat and Permissions work checked in isolated worktrees, so that reading answers can be compared with safe implementation outcomes.
13. As a project owner, I want separate new and legacy gates, so that a revised measure cannot retroactively turn the old failed experiment into a pass.
14. As an auditor, I want portable raw evidence and a clean-directory recomputation, so that a deleted experiment worktree does not erase the basis of the verdict.

## Implementation Decisions

1. Reuse the current collector, session runner, scorer, audit and independent-review seams. Keep the old protocol and reports readable. Add a versioned new protocol and a separate dual-track verdict; do not reinterpret past frozen inputs.
2. Publish a session update through a same-directory temporary file, flush and atomic replace. Serialize read-modify-write updates for a record and verify valid status transitions. Once a submission is persisted, runner timeout or failure handling cannot replace it. The runner owns only its spawned process group and waits for cleanup before classifying a failure.
3. Classify service quota, workspace load, collector protocol, task timeout and wrong answer separately. Preserve raw trace and linked attempts. A preflight checks service availability but never claims remaining quota is known. Quota exhaustion stops new dispatch; unstarted queue slots retain their order. Started infrastructure failures use at most the one frozen retry. Wrong answers and task timeouts cannot be redrawn.
4. The existing file/line read stays. Add a Markdown heading listing operation and a heading read operation. A full heading path selects exactly one section through the next heading of the same or higher level. Duplicate or absent headings fail explicitly. Code-fence text cannot become a heading. Both new operations use the same candidate manifest, path authorization and byte-accounting rules; search returns remain counted. Full reads remain available.
5. New reports distinguish submitted elapsed time from failure-close time; a missing submission duration remains null. Separate root guidance, descendant guidance, route, current documentation, historical material, source/test/config, other and repeated returns. Freeze a document/section role map before formal sessions; unknown roles remain counted as other and visible. Cost summaries include final logical attempts and all physical attempts. Original total-unique-byte calculation remains available for the legacy gate.
6. New prompts contain concrete intended behavior for UI, Chat, Knowledge, Permissions, Tests, Runtime, Upstream and History, but not answer locations or rubric hints. Retain six answer fields. Required anchors test applicable task constraints; auxiliary anchors are reported without failing an answer. Conditional Chat anchors distinguish submit gate, SDK merge, Gateway stream and embedded cross-mode behavior. UI requires identifying the actual task target, not an arbitrary example.
7. The new reading baseline is the pre-edit integration candidate. The after candidate differs in engineering documentation only; products and test tools are identical. Both sides use the same tool and model alias, reasoning setting and CLI, with interleaved scheduling. The model service provider is assumed stable as the user directed; unknown backend revision is reported, never claimed known.
8. Root guidance remains the source for global obligations and is capped at 10 KiB. The shared nine-domain index is capped at 4 KiB; each domain page at 6 KiB. The limits do not permit omission of obligations. A necessary overflow fails the size check and must be resolved by removing duplication or moving conditional details to the authoritative target.
9. Domain pages carry applicability, exact current-contract sections, conditional decisions, source start points and first focused verification. Preserve the current stop conditions. Do not rewrite protected bodies or create a second normative contract. Sync every modified AGENTS.md to its CLAUDE.md mirror.
10. Permissions points to current authorization and matrix sections and marks historic implementation chapters as history. Tests points to procedure before ledger entries. Knowledge links list and visibility entry points. Chat foregrounds SDK message chunk assembly and ID deduplication on relevant paths. Other six domains retain their current obligations while moving into the short-page format.
11. New formal reading uses eight tasks × two candidates × two replicates, fixed 16 after denominator. It passes only with 16/16 applicable-required answers correct, zero critical/historical misuse, no unresolved grading dispute and a pooled ten-slot routine Markdown unique-byte median at least 30% below baseline. Missing submission or cost evidence makes the corresponding gate incomplete. Report elapsed times, source cost and per-task results without calling the 300-second timeout a speed improvement.
12. Three isolated implementation tasks use the same frozen product tree and same prepared exercise for both candidates: optional header action in SettingsSection; duplicate pending submission in the shared turn gate; list visibility filtering before pagination. Each side runs in its own disposable worktree, within 30 minutes. Frozen tests and independent review assess behavior, static checks and preservation of adjacent contracts; the exercise code is not merged into product.
13. New formal work starts only after tool tests, eight non-scored reading pilots, scoring calibration, exercise-fixture self-check, document governance and evidence-archive restore pass. Read sessions may have three parallel readers, implementation sessions are serial. Reader errors, final answers and grader disagreements retain raw evidence.
14. Only after the new reading and three after implementation tasks pass do 32 fresh legacy-protocol sessions run. They use the historical baseline candidate and the new after candidate, with the original thresholds and task prompts, and receive a separate verdict. Do not reuse historical pass/fail counts or alter old artifacts.
15. Package candidate-readable snapshots, manifests, prompts, tool configuration, all raw attempts, answers, reviews and recomputation tools in a portable archive. Verify SHA-256 and repeat calculation from an independent directory. Keep a copy outside the experimental worktree; report the absence of external backup if one is not available.
16. Publish status for tool repair, engineering documentation, new gate and legacy gate independently. Append the slot18 quota correction to the existing evidence report without overwriting its frozen numeric result. A failed new gate leaves the legacy run unexecuted, not failed or passed.

## Testing Decisions

1. Tool changes follow TDD at the public CLI/MCP and runner boundary. Prove the original race, valid state transitions, quota stop, cancellation cleanup, heading selection, multi-byte ranges, forbidden reads and hash drift with behavior-level tests. Avoid tests that merely mirror private helpers.
2. Freeze small synthetic scoring examples for applicable/missing/auxiliary anchors, failure duration null, fixed denominator, even medians and the 30% boundary. A generated summary must match source reviews. Independent reviewers handle semantic judgment.
3. Verify a clean archive restore computes the same read intervals, cost categories, scores and candidate identities. Tampering or missing raw input must fail closed.
4. For documentation changes run the document check, guidance sync check, protected fingerprint check, link check and size check. A reader must find the task page and relevant section in all eight pilots, and Chat must name the actual message-ID owner when stream merge is in scope.
5. For implementation exercises use a focused regression and the narrowest static check per slice. After all changes, run the applicable `pr-standard` once on the final candidate, record every sub-lane summary and the parent duration/status. Real E2E selection is reported by its actual changed-path decision.

## Out of Scope

- Changing production UI, Run, auth, KB or permission behavior as part of the experiments.
- Weakening the previous experiment's 16/16, 300-second or 30% thresholds, altering its original samples or overwriting its verdict.
- Claiming strict internal model-revision identity without provider evidence, or claiming cross-model statistical stability from two replicates per task.
- Publishing raw evidence to an external service without a separately established destination.

## Further Notes

The pre-edit engineering candidate is `5687f8b90b96de73887e91e3984ad74d0772a01b`. The old frozen baseline is `867f6709642854721f209a15e362d79a96b3b489`. Detailed diagnosis and original raw artifacts remain in the prior ignored local `dev-log/`; transfer them outside the old worktree before cleanup. Prior source report: `docs/governance/disclosure-readability-experiment-pdr-2026-10-07-ticket11.md`.
