---
id: docs-specs-2026-10-09-root-gitnexus-guidance-compaction
kind: plan
status: draft
owner: repository maintainers
scope: compact always-loaded root GitNexus guidance without weakening obligations or regeneration safety
last-verified: 2026-10-09
verified-against: docs/disclosure-dual-track @ dbd6c2df7099b11d9bd1406ff282bf01360b079d
triage: ready-for-agent
---

# 精简根指引中的 GitNexus 说明

## Problem Statement

coding agent 每次进入项目都会加载根指引，包括并非每个任务都需要的 GitNexus 命令示例、资源列表和操作说明。当前根指引为 10,226 UTF-8 字节，其中带标记的 GitNexus 区块为 4,134 字节，约占 40%。这些内容挤占常驻上下文，但其中的影响分析、提交前变更分析、风险处理和纯 Markdown 提交豁免仍是必须遵守的规则。

直接删掉区块或手工缩短一次不能解决问题。GitNexus 重生成会覆盖区块，现有文档检查还要求豁免声明留在区块内。维护者需要稳定保留关键义务，将操作参考按需披露，并验证 agent 不会因文档变短而漏掉检查。

## Solution

根指引保留 GitNexus 的触发条件、不可省略的检查、风险处理和一个专项指南入口。CLI 示例、资源目录、排障及详细操作放入项目维护的专项参考。为区块再生成建立受检的维护流程，使精简结果和指引镜像可重复得到。

同时验证根指引的实际字节下降与阅读者的规则理解。文件变小和行为不退化是独立完成条件，不将字节下降直接解释为开发提速。

## User Stories

1. As a coding agent, I want the root guidance to state when GitNexus is required, so that I do not load every command example for every task.
2. As an implementer, I want the pre-edit impact-analysis obligation visible at entry, so that I inspect callers and processes before changing a symbol.
3. As an implementer, I want HIGH and CRITICAL risks to require a warning before edits, so that risk is communicated at the correct time.
4. As an implementer, I want UNKNOWN risk explained, so that an empty graph result is not treated as proof of safety.
5. As a reviewer, I want pre-commit change analysis and its completeness requirement retained, so that partial evidence is not reported as a clean check.
6. As a documentation author, I want the exact Markdown-only exemption available, so that I avoid unnecessary indexing without exempting configuration or code changes.
7. As a coding agent with MCP access, I want the primary graph operations discoverable, so that the compact root still leads to the applicable tool.
8. As a coding agent without MCP access, I want a verified CLI fallback, so that I can meet the same obligations in the current worktree.
9. As a coding agent exploring unfamiliar code, I want query and context usage discoverable, so that I can locate flows and symbol relationships.
10. As a coding agent renaming a symbol, I want the graph-aware rename requirement preserved, so that text replacement does not silently miss references.
11. As a security reviewer, I want the taint-analysis prerequisite stated, so that I do not treat an unbuilt analysis layer as complete evidence.
12. As a maintainer, I want one project-owned operational reference, so that command examples and resource lists do not diverge across documents.
13. As a maintainer, I want regenerated guidance normalized through a checked process, so that indexing does not restore verbose or incomplete instructions.
14. As a maintainer, I want source and mirror guidance to remain identical, so that different coding agents receive the same rules.
15. As a reviewer, I want an obligation-preservation map, so that removed wording can be traced to retained meaning rather than assumed redundant.
16. As an evaluator, I want required and optional GitNexus reading measured separately, so that moving text into a second file cannot masquerade as a cost reduction.
17. As a project owner, I want byte-budget and behavior results reported independently, so that a compact file is not presented as proven safe without validation.
18. As an auditor, I want a frozen comparison and original records preserved, so that this change does not reinterpret prior reading experiments.

## Implementation Decisions

1. Limit changes to root GitNexus guidance, its project-owned operational reference, its mirror, and the narrow checks/maintenance integration needed to keep them consistent. Preserve unrelated global rules, the nine-domain routes, narrower module guidance, protected bodies, product code, and test-lane contracts.
2. Keep the mandatory pre-edit impact-analysis and pre-commit change-analysis obligations immediately visible in the root. Keep the prohibition on editing symbols before impact analysis and on committing before change analysis. Merge repeated affirmative/prohibitive wording only when the full condition and action remain explicit.
3. Retain the requirement to warn before proceeding on HIGH or CRITICAL risk. UNKNOWN requires independent caller/source confirmation and cannot be read as low risk or proof of non-use. A text search may supplement an unresolved graph result; it does not replace the mandatory graph call.
4. Retain completeness rules for change analysis. Partial or truncated output is unresolved for code, configuration, workflow, script, or test changes. The sole exception is a commit whose every changed path ends in Markdown: it may record its partial result in the commit message without re-indexing. Preserve the complete exception boundary and its required record.
5. Preserve graph-first discovery for unfamiliar code, full symbol-context lookup, graph-aware rename, and the prerequisite analysis layer for security/taint review. The root gives concise triggers; the operational reference supplies invocation details and examples. Do not erase a requirement merely because its current wording appears twice.
6. Keep one direct root pointer to the project-owned GitNexus operational reference. That reference covers MCP operations, equivalent CLI fallback, worktree/index identity, freshness checks, daily index-only analysis, complete change-analysis output, UNKNOWN handling, rename, resource lookup, and recovery. It links applicable installed skills instead of copying their bodies.
7. Root checks must be executable without reading the full reference on every task. A user who needs command syntax or recovery follows the appropriate reference section. Existing tool metadata and runner help remain the authority for supported options; avoid maintaining an unnecessary duplicate catalog.
8. Preserve the managed-block markers and the existing Markdown-only exemption lead phrase inside the compact managed block. Do not remove the block to evade the current exemption checker. Keep the full exemption semantics visible even if the checker currently matches only the lead phrase.
9. Establish one repeatable generation/normalization flow for the root block and its mirror. Prefer a supported generator configuration if the installed tool can meet the contract; otherwise use a narrow project-owned post-generation normalizer at the existing maintenance boundary. Verify supported behavior locally before choosing the mechanism. Do not fork the graph engine or rely on an agent remembering a manual repair.
10. Normalization is limited to the recognized root managed block and the declared operational reference. Preserve content outside the block byte-for-byte except separately reviewed pointer placement. Fail explicitly on missing, duplicate, or unrecognized markers/templates rather than rewriting an uncertain region. The process must be idempotent and must not read or alter unrelated worktrees.
11. Treat the root source as authoritative and produce its regular UTF-8 mirror through the existing sync flow. A read-only check must report verbose regenerated content, missing obligations, incorrect mirrors, or stale reference links. CI detects drift and does not repair or commit it.
12. Require the root file to be at most 8 KiB and at least 20% smaller than its frozen pre-edit root; require the GitNexus block to be at most 2 KiB. Count normalized UTF-8 bytes per file, not tokens or the sum of the mirror pair. All three conditions apply, and no obligation may be omitted to meet them.
13. Reuse the existing public guidance/document check boundaries for feature-specific budgets and managed-block validation. The existing general root budgets are looser and do not by themselves prove this feature's acceptance limits. Add the smallest scoped check needed without tightening unrelated module budgets.
14. Preserve an obligation map from every original normative statement to retained root wording and, where needed, its operational reference. Mechanical checks cover markers, links, budgets, mirror equality, and known exemption loss; independent review judges semantic equivalence. Do not rely on keyword presence alone to prove equivalence.
15. Freeze a comparison in which only this feature's reader-visible guidance changes. Keep domain routes, product source, tests, prompts, and external evaluator tools identical. If task-branch navigation lands first, include it in both sides of a newly frozen root-guidance comparison. Report a combined result as combined, without attributing it solely to root compaction.
16. Keep engineering delivery, byte-budget compliance, rule-preservation validation, and measured reading-cost results separate. Existing historical acceptance remains unchanged, and unknown model-provider revisions remain unknown.

## Testing Decisions

1. The deterministic seams are the existing public document/guidance check CLIs and the guidance maintenance command boundary. The behavioral seam is a coding agent entering through root guidance and locating the required GitNexus action through its pointer. Use both; neither file size nor wording snapshots establish behavioral equivalence.
2. Before editing, freeze the root bytes, managed-block bytes, rule-preservation map, baseline candidate, and expected semantics. The recorded 10,226/4,134-byte values describe the prior candidate; recompute against the actual frozen baseline instead of assuming they remain current.
3. At the public checker boundary, use focused red/green fixtures for an oversized compact root/block, a broken reference anchor, a missing exemption, mirror mismatch, and a changed non-Markdown file incorrectly treated as exempt. Include a valid compact candidate. Assert findings and exit status, not exact prose or private helper calls.
4. At the maintenance boundary, exercise representative full generated output followed by normalization/sync/check. Verify compact output, complete obligation preservation, identical mirrors, unchanged surrounding content, and idempotence. Missing/duplicate markers or an unsupported generated format must fail without partial writes. Retain existing protected-fingerprint and candidate-revision checks.
5. Verify an actual supported local regeneration path in an isolated worktree with a private matching index. Record the command, tool version, and before/after file hashes. If regeneration itself writes guidance, the complete declared maintenance flow must restore the compact, synchronized candidate and then pass the read-only checks. A hand-crafted fixture alone cannot prove real regeneration compatibility.
6. Run non-scored behavior probes for pre-edit impact, HIGH/CRITICAL warning timing, UNKNOWN confirmation, complete pre-commit analysis, valid Markdown-only partial exemption, non-Markdown rejection of that exemption, graph-aware rename, and MCP-unavailable CLI fallback. Prompts state tasks, not the required answers. Separate correct action selection from proof that a graph command actually ran.
7. Use reviewer-only required/conditional anchors from the obligation map. Obtain two independent semantic reviews and adjudicate disagreements before claiming equivalence. Any missing mandatory rule or unresolved applicability prevents rule-preservation acceptance; existing graph UNKNOWN/truncation results cannot become successful execution evidence.
8. For the formal reading comparison, reuse the v2 eight-task prompts and two replicates per candidate, with 32 fixed slots and 16 after answers. Hold the prompt/queue/rubric/reader configuration fixed across candidates; exclude this specification, the obligation map, answers, and evaluator materials. Preserve existing timeout, quota-stop, and retry rules and all physical attempts.
9. Formal correctness requires 16/16 applicable-required after answers, zero critical errors, zero historical-authority misuse, and no unresolved grading dispute. Separately report compliance-probe results, root bytes, managed-block bytes, and the routine Markdown unique-byte median. Missing records or tool drift make the affected gate incomplete rather than correct by assumption.
10. Count root, mirror, new reference, route, other documentation, source, and repeated returns using the existing role map and physical-attempt reporter. Root/block byte budgets are hard feature criteria. An aggregate reading-efficiency claim additionally retains the existing 30% routine Markdown median reduction threshold; root compaction may pass its structural criteria while that broader cost goal fails. Moving the same reading into a reference cannot count as avoided reading.
11. Recompute reports from raw records in an independent directory, archive the manifests/prompts/tools/reviews, and verify a worktree-external copy. Report exact measured scope, sample limits, and backup durability. Do not claim lower end-to-end development time from file size, reader submission time, or unchanged practical success.
12. Reuse prior public tests for guidance size/candidate revisions, document exemption and protected fingerprints, mirror synchronization, and reader heading access. Run focused regressions and narrow static checks per code slice; run the applicable standard lane and one final integration `pr-standard` on the frozen candidate. Report Real E2E selection from actual integrated paths, and do not broaden every document edit into a full-stack test run.
13. A standalone root-guidance structural acceptance does not depend on implementing the navigation feature. Combined delivery may share unchanged environment evidence and a final integration gate, but independent effects require separately identified comparisons and after candidates. Publish the exact gate result without editing the tested candidate after execution starts.

## Out of Scope

- Reorganizing task-domain branches, changing public product behavior, or modifying protected upstream module bodies.
- Removing mandatory graph analysis, weakening UNKNOWN or HIGH/CRITICAL handling, widening the Markdown-only exemption, or accepting incomplete code-change analysis.
- Deleting managed-block markers to bypass checks, manually restoring them after every run, or modifying generated runtime caches as the durable solution.
- Changing the GitNexus graph engine, query schema, risk classification, model provider, or installed global skills.
- Implementing the retrospective's general evaluator, timing, process-supervision, reporting, or backup repairs.
- Adding a new practical coding acceptance exercise; the maintainer confirmed existing CLI checks plus reading acceptance as the validation boundary.
- Altering historical scores, asserting general development speed gains, splitting implementation tickets, or running model-backed acceptance during specification publication.

## Further Notes

- This is retrospective item 6. Reference candidate: `docs/disclosure-dual-track @ dbd6c2df7099b11d9bd1406ff282bf01360b079d`. The current [root source](../../AGENTS.md) and [mirror](../../CLAUDE.md) contain the managed block; this spec does not itself change them.
- Existing constraints and seams: [document checker](../../scripts/check_documents.py), [guidance size checker](../../scripts/check_agent_guidance.py), [guidance mirror tool](../../scripts/sync_agent_guidance.py), [document hygiene entry](../../scripts/check_doc_hygiene.sh), and [document governance](../governance/document-governance.md). The exemption check currently requires its lead phrase inside the managed block.
- The local CLI runner is `.gitnexus/run.cjs`; its generated location is not a new tracked source of project policy. Determine the installed generator's supported configuration from local code/help before choosing regeneration integration.
- [Engineering terminology](../../CONTEXT.md), [decision index](../decisions/README.md), and the [latest final verdict](../experiments/disclosure-dual-track-ticket10-final-verdict-2026-10-09.md) provide the terminology, current decisions, and prior-effectiveness limits.
- Publication follows [local specifications and work tickets](../agents/issue-tracker.md). This is a ready-for-agent draft proposal; accepted decisions, delivered implementation, and validated behavior remain distinct states.
- Related independent specification: [task-branch navigation](2026-10-09-disclosure-task-branch-navigation-spec.md). The two specifications preserve a common baseline and permit implementation sequencing without requiring simultaneous changes.
