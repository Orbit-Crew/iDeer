---
id: docs-archive-2026-readme
kind: index
status: current
owner: repository maintainers
scope: topic registry of the docs/archive/2026 partition: archived testing, permission, optimization, offline, and governance materials with their current replacement entries, plus the retention rule
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ ba5c37163
---

# 2026 年历史文档

> audience: maintainers, auditors, incident reviewers<br>
> status: current<br>
> owner: repository maintainers<br>
> last-verified: 2026-10-04<br>
> canonical-path: `docs/archive/2026/README.md`

本目录登记已结束的计划、审计和阶段性材料。历史正文已物理迁移到本目录；旧路径不再保留跳转桩。登记项中的 canonical path 是归档后的主题入口。登记项的"结论与当前替代入口"列给出各项的现行权威；从历史材料出发的任务先读该列，不把归档正文当作现行依据。

## 已归档主题

| 主题 | 原始材料 | 结论与当前替代入口 |
| --- | --- | --- |
| 测试体系重组 | [`testing/multi-role-testing.md`](testing/multi-role-testing.md) | 原 QA 说明过时；以 [`docs/testing/coverage-matrix.md`](../../testing/coverage-matrix.md) 和迁移账本为准。 |
| AI 验证技能执行摘要 | [`testing/ai-code-validation-executive-summary.md`](testing/ai-code-validation-executive-summary.md) | validator/orchestrator skill 为历史方案，当前工作树不可调用；现行测试权威以[覆盖矩阵](../../testing/coverage-matrix.md)和 [lane 运行手册](../../testing/test-lane-runbook.md)为准。 |
| AI 验证技能体系分析 | [`testing/ai-code-validation-skill-analysis.md`](testing/ai-code-validation-skill-analysis.md) | 历史方案分析与时点优化提案，提案未落地；现行以 [`docs/testing/`](../../testing/README.md) 权威文档为准。 |
| 前端测试补全计划 | [`testing/frontend-test-coverage-plan.md`](testing/frontend-test-coverage-plan.md) | 分支战役时点计划，已执行完毕（完成数据见同目录总结）；测试计数与 spec 清单不代表当前布局，以覆盖矩阵为准。 |
| 前端测试补全总结 | [`testing/frontend-test-coverage-summary.md`](testing/frontend-test-coverage-summary.md) | 时点验证证据，不构成当前验证；现行测试权威为[覆盖矩阵](../../testing/coverage-matrix.md)。 |
| 截图测试全覆盖计划 | [`testing/screenshot-test-coverage-plan.md`](testing/screenshot-test-coverage-plan.md) | 计划未按原样实施（目标 spec 现位于 `frontend/tests/e2e/visual/`）；以覆盖矩阵为准。 |
| 测试覆盖率提升计划 | [`testing/test-coverage-improvement-plan.md`](testing/test-coverage-improvement-plan.md) | 覆盖率数字与缺口清单为 2026-06-13 时点；现行覆盖权威为[覆盖矩阵](../../testing/coverage-matrix.md)。 |
| 测试增强路线图 | [`testing/test-enhancement-roadmap.md`](testing/test-enhancement-roadmap.md) | 目录重组已按 `backend/tests/{unit,integration,contracts}` 落地，其余条目未逐一核对；以覆盖矩阵和 [lane 运行手册](../../testing/test-lane-runbook.md)为准。 |
| 测试目录重组计划 | [`testing/test-reorganization-plan.md`](testing/test-reorganization-plan.md) | 重组其后以不同布局落地；测试迁移与删除的唯一记录权威为[迁移账本](../../testing/test-migration-ledger.md)。 |
| 测试缺口完善方案 | [`testing/testing-gap-remediation-plan.md`](testing/testing-gap-remediation-plan.md) | 视觉回归与 a11y 方案已落地，其余未核对；依托的 validator skill 已归档；以覆盖矩阵为准。 |
| 测试工具接入实现计划 | [`testing/testing-tools-integration-plan.md`](testing/testing-tools-integration-plan.md) | 主要产物已在树中（pytest-xdist、`backend/tests/factories/`、Lighthouse CI、dependency-cruiser）；以覆盖矩阵和 lane 运行手册为准。 |
| 验证最佳实践指南 | [`testing/validation-best-practices.md`](testing/validation-best-practices.md) | validator skill 历史工作流，验证级别与命令不对应现行车道；以 [lane 运行手册](../../testing/test-lane-runbook.md)和[覆盖矩阵](../../testing/coverage-matrix.md)为准。 |
| 验证流程缺口分析 | [`testing/validation-gap-analysis.md`](testing/validation-gap-analysis.md) | 时点分析证据，缺口后续修复情况未逐一复核；以覆盖矩阵为准。 |
| Workflow 缺陷验证记录 | [`testing/validation-log.md`](testing/validation-log.md) | 三轮全绿为 2026-06-09 候选的时点记录；以覆盖矩阵和[迁移账本](../../testing/test-migration-ledger.md)为准。 |
| validation-orchestrator 实施计划 | [`testing/validation-orchestrator-implementation-plan.md`](testing/validation-orchestrator-implementation-plan.md) | 历史设计未在当前候选保持实施状态；现行验证路径为 [lane 运行手册](../../testing/test-lane-runbook.md)与仓库 CI。 |
| 全量验证剩余问题 | [`testing/validation-remaining-issues-plan.md`](testing/validation-remaining-issues-plan.md) | 时点验证证据，其后演进未逐一复核；以覆盖矩阵和 lane 运行手册为准。 |
| 权限模型审计 | [`permission/permission-model-audit-2026-07-05.md`](permission/permission-model-audit-2026-07-05.md) | 审计证据保留；设计以 [`docs/permission-model-redesign.md`](../../permission-model-redesign.md) 为准。 |
| 权限模型待实现清单快照 | [`permission/permission-backlog-history-2026-07-06.md`](permission/permission-backlog-history-2026-07-06.md) | v1.3 候选的时点待实现清单，其开项已在后续候选落地；现行待办以 [`docs/backlog.md`](../../backlog.md)（PERM 条目）为准，设计以 [`docs/permission-model-redesign.md`](../../permission-model-redesign.md) 为准。 |
| 企业内网优化方案 | [`optimization/`](optimization/) | 计划与阶段路线归档；当前运维入口为离线部署作业指导书。 |
| 测试计划与验证报告 | [`testing/`](testing/) | 计划、差距分析和验证日志归档；当前责任以测试规范、覆盖矩阵和迁移账本为准。 |
| AI 测试工具评估 | [`testing/ai-test-tools-integration.md`](testing/ai-test-tools-integration.md) | 工具选型和验证证据归档；不作为默认测试门禁。 |
| 离线分支问题与变更报告 | [`offline/`](offline/) 和归档根目录 | 分支历史证据归档；当前分支和发布规则以离线产品线治理方案为准。 |
| 文档盘点与导入决策 | [`governance/document-system-audit-2026-06-28.md`](governance/document-system-audit-2026-06-28.md)、[`decisions/intranet-source-import-decision-2026-07-15.md`](decisions/intranet-source-import-decision-2026-07-15.md) | 历史盘点和决策证据归档；当前入口以 `docs/README.md` 和 `docs/decisions/README.md` 为准。 |
| 功能规划与开发跟踪快照 | [`governance/feature-backlog-history-2026-07-15.md`](governance/feature-backlog-history-2026-07-15.md) | 2026-07-15 候选的时点 backlog 快照；当前未完成事项唯一入口为 [`docs/backlog.md`](../../backlog.md)。 |

## 归档规则

归档文档保留来源、日期和结论，不作为当前操作步骤。需要删除时，必须先完成全量引用扫描、内容覆盖审查和人工确认。
