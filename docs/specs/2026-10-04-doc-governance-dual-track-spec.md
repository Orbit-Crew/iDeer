---
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
- 下一步由 `/to-tickets` 拆成三批工单（含阻塞边：第二批依赖第一批的状态词与术语、第三批依赖第二批的导航），经 `orchestrate-worktrees` 执行。
