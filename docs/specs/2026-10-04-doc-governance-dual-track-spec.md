---
id: docs-specs-2026-10-04-doc-governance-dual-track-spec
kind: plan
status: current
owner: repository maintainers
scope: governing spec for documentation dual-track governance — the public docs-site three-batch track (status vocabulary, index repair, navigation, iDeer pages) and the engineering documentation disclosure track (checker, task routes, project state, guidance reduction, and the 49 body-audit batches, in progress as of 2026-10-04); the dual-track red lines (upstream add-only, local free, mixed semantic-merge) bind every batch
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ d964b3963
triage: ready-for-agent
---

# 文档体系双轨治理

## Problem Statement

三类读者都在文档上浪费时间。新开发者或 coding agent 从 `AGENTS.md` 出发，遇到断裂的索引（测试写作规范未被测试总纲收录）、过期的学习路线（10 处失效路径）和两条互不提及的启动路径（人类 README 与 agent Install.md），5 分钟内到不了正确上下文。运维者面对三个并列的部署入口，分不清离线实操权威是哪一份。企业内网用户打开文档站，看到的是上游 DeerFlow 的介绍（52 页含 DeerFlow 品牌词），而不是自己用的 iDeer 产品；已存在的 iDeer 页面（`why-ideer`、`deploy-your-own-ideer`）因未注册导航而不可见。维护者无法用 `status:` 判断一篇决策是否现行，因为正文混用 `accepted / implemented / binding contract / passed for <date>`，17 个文件验证日期停在 2026-07-15。

## Solution

按已锁定的 9 项决策分三批治理。首批修复开发者效率：统一状态词、补索引断裂、修正失效路径、标注运维权威、接通 agents.md 互链。第二批收敛冗余：架构三重声明分工、权限双主降级、大小写双份二选一、计划补状态头；文档站介绍类上游页摘导航、Tier 0–2 约 17 页转写。第三批新建中文 iDeer 用户页 7–8 页。全程遵守双轨红线：上游轨文件只加不改、本地轨自由改、混合轨语义合并；改动走 `develop` 线。

## User Stories

1. As a new developer, I want one task-to-document map from AGENTS.md, so that I reach the right authority within 5 minutes.
2. As a coding agent, I want the ADR naming rule to be single-valued, so that I create new ADR files with the correct pattern.
3. As a coding agent, I want the decision status enum to be machine-checkable, so that I can tell current from archived without guessing.
4. As a developer writing tests, I want the test-writing规范 indexed from the testing纲要, so that I find the Mock boundary rules in one hop.
5. As a developer following the learning roadmap, I want every path in it to exist, so that I do not hit dead references.
6. As an operator doing offline deployment, I want exactly one marked authoritative runbook, so that I never follow a stale deployment chapter.
7. As an operator troubleshooting MCP tools, I want the排故手册 linked from the operations entry, so that I find it without searching.
8. As a tester, I want the coverage matrix verification date to match the testing纲要, so that I trust it as current.
9. As a maintainer, I want each plan file to carry a status header, so that I can separate active plans from history.
10. As a maintainer, I want duplicate evidence files to exist in exactly one path, so that md5-identical copies do not confuse audits.
11. As an auditor, I want each harness patch decision recorded with reason, owner and removal condition, so that upstream-sync reviews have a paper trail.
12. As an intranet user, I want the docs site navigation to show iDeer pages, so that I learn the product I actually use.
13. As an intranet user, I want the DeerFlow introduction pages hidden from navigation, so that I am not taught a different product.
14. As an intranet user, I want the application section to lead to the iDeer user manual, so that usage instructions match the screens I see.
15. As an intranet user, I want first-conversation and workspace tutorials written for iDeer, so that the steps work on my deployment.
16. As a public developer, I want the harness and reference docs to keep describing DeerFlow functionality, so that runtime API documentation stays accurate.
17. As a public developer, I want zero-brand generic pages to stay as-is, so that shared concepts are not forked pointlessly.
18. As a bilingual user, I want the English manual stub to declare itself as a stub, so that I switch to the Chinese manual instead of reading an incomplete page.
19. As a release owner, I want the releases index to carry audience and verification fields, so that it meets the same bar as other indexes.
20. As a future upstream-sync operator, I want upstream-owned doc files byte-identical to upstream, so that the next merge stays clean.
21. As a coding agent, I want a task-to-document route that names the current contract, code entry point, conditional decisions, and validation, so that I can begin implementation without browsing unrelated history.
22. As a coding agent, I want each document pointer to state both what its target contains and when to read it, so that context is disclosed only when the task reaches that branch.
23. As a maintainer, I want global rules, task routing, module context, current references, decisions, and historical evidence to have distinct roles, so that one fact has one authoritative home.
24. As a coding agent, I want project state to distinguish implementation, integration, and verification for a named candidate, so that accepted decisions and historical test results are not mistaken for shipped, validated behavior.
25. As a maintainer, I want historical plans and snapshots explicitly scoped to their period or candidate, so that useful history remains available without appearing to be current implementation guidance.
26. As a coding agent, I want decisions indexed by topic with their current conclusion, scope, and reread trigger, so that I can trace relevant rationale without loading every decision record.
27. As a maintainer, I want machine checks to catch missing metadata, broken local references, conflicting authorities, and invalid decision supersession, so that documentation drift is detected on the candidate revision.
28. As a maintainer, I want protected upstream documents and immutable evidence registered without rewriting their bodies, so that governance can describe their applicability while preserving provenance.
29. As a new coding agent, I want representative tasks evaluated in independent sessions before and after the change, so that reduced reading effort does not come at the cost of wrong guidance.
30. As a contributor, I want local rules and their generated CLAUDE.md mirrors kept synchronized, so that each supported agent receives the same valid instructions.

## Implementation Decisions

已锁定的 9 项决策（grilling 共 8 问 + 差异审计，全部经用户确认）：

- 双轨边界：上游轨（`frontend/src/content` 内 DeerFlow 原生页、`docs/ARCHITECTURE.md`、harness 内文档）只加页头声明或新增跳转页、不改正文；本地轨（`docs/manual/`、治理、testing、decisions、adr、architecture 概览、离线治理、backlog）自由改；混合轨（`backend/docs/ARCHITECTURE*`、根 `README*`）语义合并。
- 术语：DeerFlow 指上游项目、iDeer 指本仓企业产品、Harness 指运行时、App 指完整应用；`AgentPlatform` 仅指仓库名。输出统一使用该词汇。
- 状态词：一次性映射到 `current / draft / superseded / archived`，原词保留为副字段（`decision-outcome:` / `enforcement:`）；上游轨文件不动。
- 手册单源：源留本地 `docs/manual/`，前端 manual 页改跳转。
- 导航策略：介绍类替换、功能类保留；`_meta.ts` 属语义合并区可改。
- iDeer 页分级：Tier 0 直接复用 4 页、Tier 1 纯品牌转写约 8 页、Tier 2 重命名核对约 5 页、Tier 3 中文实质重写 7–8 页、英文暂冻。
- iDeer 版以 en 页为基线（en 在 mcp、memory、harness-vs-app 等页领先 zh）。
- 本说明偏离 to-spec 模板一处：模板要求不写具体文件路径，但本文是文档治理规约，文档路径即模块接口，故保留路径表。

第一批（5 个独立切片）：domain.md 命名行修正与 ADR 补状态头；decisions/governance/testing 状态词映射与 releases 补字段；testing 纲要收录写作规范与矩阵日期对齐；learning-roadmap 路径表重写与 operations 权威标注；AGENTS.md 三行互链与 README/Install 分流。

第二批：架构三重声明分工、权限双主降级、AUTH 大小写双份二选一、pr-evidence 删双份、plans/superpowers 补状态头、根散档判归档；文档站介绍类摘导航、Tier 0–2 转写、`why-ideer`/`deploy-ideer` 注册导航、手册单源落地。

第三批：中文 Tier 3 新建 7–8 页；`application/*` 不建 iDeer 版，导航指向 `manual/index`。

## Testing Decisions

好的测试只断言外部可观察行为，不逐字审查正文。采用 6 条最高可达缝（seam），覆盖一批即覆盖一批的全部文件：

1. frontmatter 枚举断言：目标目录下 `status:` 取值全部落在四态内（grep 计数为零即过）。
2. 索引链接存在性断言：各 README 索引的链接目标文件全部存在。
3. 导航注册断言：新建 iDeer 页全部出现在对应 `_meta.ts`；摘除的上游页全部不在导航。
4. 重复指纹断言：已知的 md5 双份路径只剩一处。
5. 品牌词残留断言：新建 iDeer 页内无 `deerflow`/`DEER_FLOW`/`bytedance` 残留（零品牌复用页除外）。
6. 上游零 diff 断言：受保护的上游轨文件与上游快照无差异。

先行依据：`docs/document-retention-assessment.md` 第 6 节复核命令是同类断言的先例；`scripts/test_inventory.py` 是"清单即测试"的先例。文档改动不跑产品测试 lane，按测试 lane 运行手册中"普通本地变更只需聚焦回归 + 最窄静态检查"的精神，每片只需上述对应断言。

## Out of Scope

- 前端应用功能页（workspace、chats、settings、login 等 `page.tsx`）一律不动。
- 后端代码与 harness 运行时补丁登记不在本文范围（见补丁台账）。
- 英文 Tier 3 新建；英文仅注册既有 `why-ideer`/`deploy-ideer`。
- `posts/*` 上游版本线内容：摘导航，不转写，不删除。
- 向上游提交 PR：客观 bug 只报告，不在本地改上游文件。
- 删除上游文件：任何情况下不删除，只做导航可见性控制。

## Further Notes

- 基线（2026-10-04 实测）：`last-verified: 2026-07-15` 共 17 处；内容站含 DeerFlow 页 104 个（中英各 52）、含 iDeer 页 6 个；定性为纯品牌 11 页、实质 6 页、混合 42 页（zh 口径）。
- 分支规则：改动走 `develop` 线；`main` 仅镜像快进；已冻结的升级台账只读。
- 公开文档站这条轨道按三批工单推进：第二批依赖第一批的状态词与术语，第三批依赖第二批的导航；coding-agent 工程文档治理另按本规格后文的八组工单执行。

## Engineering Documentation Disclosure Track

本节扩展工程文档治理范围，不改变前述公开文档站三批工作、双轨边界和已确认的品牌／导航决策。工程文档改造在单独的票据组中实施；用户手册及公开文档站正文不属于该票据组。

### Problem Statement

工程规则、当前事实、模块参考、决策理由和历史证据分散在根规则、局部规则、架构文档、计划、快照和验收记录中。文档目录已有索引和同步机制，但缺少可执行的任务阅读路径、项目状态的统一摘要，以及能区分现行依据与历史背景的检索方式。部分文档混有已过期的流程指令或把历史勘察标为当前，且 ADR 命名要求相互冲突。Coding agent 因而可能读取过多无关材料，或把旧计划、已接受决策和历史测试结果误作当前实现状态。

### Solution

按渐进式披露组织信息：每次任务读取全局规则；识别任务后沿任务路由读取当前契约、模块入口和验证方法；只有触及设计边界或排查历史时才打开决策和历史证据。每层说明职责和触发条件，事实只维护在一个权威来源中。项目状态明确候选及实现、集成、验证状态。普通本地工程文档采用统一元数据；上游保护文档、冻结记录和不可变证据由本地伴随登记描述，不改其正文。

### User Stories

1. As a coding agent, I want each common task to lead from a concise route to its current contract, code entry point, relevant decisions, and checks, so that I can identify the right work surface quickly.
2. As a coding agent, I want an explicit stopping condition for document reading, so that I begin source verification once the applicable constraints and validation path are known.
3. As a maintainer, I want root rules to contain global invariants and task pointers while conditional procedures live behind those pointers, so that routine work carries less always-loaded context.
4. As a module owner, I want local agent guidance to contain only constraints needed before changing that module, so that detailed algorithms and incident histories remain available on demand.
5. As a maintainer, I want the architecture overview to describe current boundaries and execution relationships rather than duplicate workflow policy or temporary status, so that its claims have a stable purpose.
6. As a coding agent, I want a project-state index with candidate-scoped implementation, integration, verification, limitations, evidence, and next-step references, so that I can distinguish current capability from incomplete delivery.
7. As a coding agent, I want a topic index for decisions that shows current conclusions and when full rationale is required, so that historical alternatives are discoverable without becoming mandatory reading.
8. As a maintainer, I want superseded decisions linked in both directions and checked for cycles, so that the active rationale is unambiguous.
9. As a maintainer, I want a repository inventory that classifies every in-scope document and records protected files and exclusions, so that governance coverage is measurable.
10. As a maintainer, I want a read-only checker to validate document metadata, local links and anchors, authority uniqueness, routing completeness, decision relations, candidate references, and protected-file integrity, so that broken navigation is caught automatically.
11. As a contributor, I want checks against an explicitly selected revision to read only that revision, so that local uncommitted content cannot mask a candidate failure.
12. As a maintainer, I want generated CLAUDE.md mirrors synchronized from AGENTS.md after rule edits, so that supported agents receive consistent guidance.
13. As a new coding agent, I want ordinary implementation tasks and history-tracing tasks evaluated separately in clean sessions, so that navigation is both efficient and accurate.
14. As a maintainer, I want all current engineering references reviewed against source and validation evidence, so that a current label reflects reviewed applicability rather than a refreshed timestamp.

### Implementation Decisions

- Preserve the five disclosure tiers: global rules; task routing and project state; module context; decisions; historical evidence. Each route pointer names the target's purpose and the task condition that triggers reading it. Stop document exploration once the edit entry point, applicable constraints, relevant decision, validation path, and unresolved state are identified.
- Preserve single-source responsibilities: root rules define global obligations; task routing selects documents; architecture describes boundaries; project state summarizes candidate-scoped status; domain references define current behavior and invariants; CONTEXT defines engineering terminology; ADRs explain decisions; backlog lists unfinished work; plans define intended work; evidence records a specific candidate and environment.
- Add a concise task route covering ordinary frontend changes, chat/runtime, resource authorization, KnowledgeBase, Agent/Skill/Workflow, local runtime, configuration/deployment, tests, and upstream synchronization. Each task route provides current references, code entry point, conditional decisions, and validation entry point.
- Add a project-state page covering chat/runtime, resource authorization, KnowledgeBase, Agent/Skill/Workflow, local runtime, upstream integration, and validation infrastructure. For each area record candidate/branch, implementation state, integration state, verification state, limitations, evidence, current contract, next work item, and owner when known. Missing evidence is recorded as unverified or not run; historical passing results do not imply current verification.
- Extend the decision index with topic, current conclusion, scope, full-record trigger, and implementation/validation references. Preserve existing ADR and dated-decision filenames. New ADRs use numbered names; fix the conflicting filename rule. Keep accepted decision outcome separate from implementation and verification status, and encode supersession both ways without cycles.
- Apply frontmatter to ordinary locally maintained engineering documents: `id`, `kind`, `status`, `owner`, and `scope` are required. `status` is exactly `current`, `draft`, `superseded`, or `archived`; `kind` distinguishes index, reference, policy, decision, plan, snapshot, and evidence. Current factual references record `last-verified` and `verified-against` using a real candidate reference. Decision outcome, implementation state, and verification state remain separate fields. Superseded documents name their replacement; historical snapshots state their applicable period or candidate. Existing useful metadata and specification `triage` fields remain intact. AGENTS.md files do not require frontmatter.
- Maintain one machine-readable document policy/inventory for in-scope paths, protected upstream or immutable files, topic authority, exclusion rationale, and migration mapping. Document frontmatter remains the source of document state; the manifest must not duplicate that state. Persist the policy and its maintainer-facing contract as tracked governance documents so the checker and CI consume a durable candidate-scoped source. Authority uniqueness is evaluated by topic and scope, allowing distinct product-governance and upstream-implementation references where their scopes differ.
- Add a read-only `scripts/check_documents.py` command with `--repo-root PATH`, `--revision REF`, and `--json`. Without a revision it checks the working tree; with a revision it reads only that candidate. Exit codes are 0 for clean, 1 for contract findings, and 2 for configuration/read/execution failures. JSON reports candidate identity, inventory counts, and findings with rule ID, severity, file, location, and reason. It performs no repairs, dependency installation, or network probes. Parser dependencies are pinned through the repository lockfile.
- The checker validates inventory coverage and conflicting scope; metadata shape and unique IDs; topic-authority uniqueness; local Markdown links, reference links, images, and anchors; task-route reachability and validation pointers; decision supersession integrity; current-state candidate evidence; and protected-file content fingerprints. External URLs receive syntax checks only. Human review remains responsible for semantic agreement with code and for classifying ambiguous history.
- Preserve upstream-owned bodies, frozen upgrade records, and immutable acceptance evidence. Describe local applicability through the inventory/route index. If an immutable historical record refers to a prior path, preserve that record and make its candidate-scoped historical status explicit rather than rewriting evidence.
- Migrate in eight groups: (1) reproducible baseline, scope inventory, protected-file fingerprints, migration ledger, and before-change reading fixture; (2) checker plus a minimum test/decision navigation slice and resolution of known policy conflicts; (3) task routes and global guidance; (4) project state and decision traceability; (5) local agent-rule reduction and generated mirror synchronization; (6) complete engineering-document audit in bounded directory/topic batches; (7) independent before/after reading evaluation; (8) full-candidate CI gate and handoff.
- Group 5 local guidance reduction is split into bounded mirrored-pair batches of no more than 25 documents plus an aggregate reduction check. Group 6 is partitioned so each ticket has no more than 25 document bodies to verify; each document exceeding 1,000 lines is a singleton ticket. At accepted baseline `867f67096`, the manifest covers 360 tracked Markdown paths: 246 body-review documents, 56 agent-guidance files, 37 fixture/manual inventory-only files, and 21 protected-baseline paths. The group 6 batches cover the 246 body-review documents; all 49 batch scopes and line-count singletons are listed in the local ticket index. The protected-file sidecar retains all 67 baseline fingerprints, including protected artifacts outside the 360 Markdown paths. The inventory derives from `git ls-files` and explicitly excludes public-manual body changes. Do not batch-update verification dates without content review.
- Keep work on the `develop` line, use one self-contained worktree agent per ticket, and sequence tickets by genuine file/data dependencies. The final gate depends on every audit batch and the reading evaluation. Execute the completed engineering work through `orchestrate-worktrees` after this specification and local tickets are ready.
- For rule edits, regenerate matching CLAUDE.md with `python3 scripts/sync_agent_guidance.py --write`, then run `--check`. Preserve existing size checks. Reduce locally controlled always-loaded rule bytes by at least 30% from the recorded baseline without dropping valid rules; every migrated rule has an explicit destination in the ledger.
- After all documents pass, run full inventory checking in the existing PR and develop/product-branch checks. Retain the existing main fast-forward mirror policy. Do not add legacy-error exemptions or change workflow path-selection semantics.

### Testing Decisions

- Prefer observable CLI behavior tests: valid documents pass; invalid/missing fields, broken links, conflicting authorities, malformed supersession, stale protected fingerprints, and incomplete routes fail with stable rule IDs and locations. Verify the checker is read-only.
- Verify `--revision` isolation with a working-tree-only difference and confirm JSON and exit-code behavior for clean, finding, and operational-error cases.
- For document batches, run the focused checker and applicable AGENTS/CLAUDE sync and protected-file checks. Add no product test lane for prose-only changes.
- Run a before/after reading evaluation in eight fixed task classes: ordinary frontend component, chat submit/stream state, KnowledgeBase listing, resource authorization, Harness runtime, test addition/migration, upstream sync/local patch, and historical-decision applicability. Use two fresh sessions per task on the same model/tool setup; evaluators receive only the candidate and task prompt, not this specification's answer key. Record correctness, time to identify the edit/validation route, files/bytes read, and historical-source misuses.
- Acceptance requires every session to identify the applicable constraints, authority, relevant decision where applicable, and validation path correctly; zero cases treating a historical plan as current policy; and, for ordinary tasks excluding protected-upstream reading cost, median route-finding time at most five minutes with median reading volume reduced at least 30% from baseline. Report protected-upstream tasks separately. Rerun failed task classes after correction.
- After all work, run the repository's `pr-standard` once and report each sub-lane plus the parent `TEST_LANE_DURATION`; do not run `core-full` for this documentation-governance scope. Respect lane preflight and inventory requirements for any added tests. Report unavailable credentials, sandbox limitations, and timeouts as unexecuted/incomplete with the exact command and last observed test.
- Before editing any code symbol for the checker, perform GitNexus impact analysis; before committing, run `detect_changes` for the explicit worktree and review its completeness and risk. Documentation-only changes still require the graph check before commit as specified by the repository guidance.

### Out of Scope

- Public docs-site navigation, branding, and manual content already covered by the preceding three-batch track.
- Product code, runtime behavior, APIs, database schemas, and migrations.
- Rewriting protected upstream document bodies, frozen upgrade records, or immutable historical evidence.
- Automatically claiming semantic correctness from metadata/link checks, live external URL availability, or an old passing test result.
- Publishing GitHub issues, pushing/merging branches, or changing remote branch protection. The repository's local issue tracker publishes specifications in `docs/specs/` and tickets under `.scratch/`.
- Running `core-full`; this work is documentation governance rather than release or full-delivery acceptance.

### Further Notes

- The accepted baseline is the isolated `develop` worktree commit used to execute this specification. The initiating workspace and unrelated user changes remain outside the ticket scope. Record the baseline commit and a working-tree fingerprint when carrying authorized task changes into the worktree.
- Reading evaluation baseline and final runs use identical eight task prompts and two independent sessions per task. Each session starts without conversation history and reads only repository guidance available at the selected candidate. The evaluation report records candidate, model/tool configuration, elapsed time, files and bytes read, route/authority/decision/validation answers, and errors. Do not use evaluation answers as a substitute for source verification.
- The exact baseline inventory and ticket mapping are recorded in `.scratch/agent-doc-disclosure/ticket-index.json`; each ticket lists its actual scope and blocker IDs. Body-review and local-guidance batches contain at most 25 documents, and every body-review document over 1,000 lines is a singleton ticket. The captured inventory has 360 tracked Markdown paths and 49 body-review batches. Recompute only if the accepted baseline changes, and record any delta before dispatch. The baseline reading evaluation remains pending until the coordinator-owned clean-root run is available; do not claim measurements before then.
- The checker uses the repository's locked runtime and dependency versions. CI validates the candidate revision, never mutates or repairs documentation, and runs the complete inventory once the cleanup groups pass.
- Work-ticket group structure: baseline and contract; checker/minimum slice; routes and global rules; status and decision index; local-rule reduction; bounded full-document audit; independent reading evaluation; CI gate and handoff. Tickets are written locally with numbered blocking edges and `ready-for-agent` state, following the repository tracker contract.
