---
id: docs-readme
kind: index
status: current
owner: repository maintainers
scope: entry index of engineering documentation: reader routes, current-authority table, and archive pointers
last-verified: 2026-10-10
verified-against: worktree docs/doc-disclosure-followup @ bf065a2d0
---
# 工程文档入口

> audience: developers, operators, testers, maintainers<br>
> status: current<br>
> owner: repository maintainers<br>
> last-verified: 2026-10-06<br>
> canonical-path: `docs/README.md`

这里是开发、运维、测试和内部治理文档的入口。面向最终用户和公开开发者的产品说明，请从公开文档站（部署后路由 `/zh/docs` 与 `/en/docs`；仓库内内容源见[中文文档内容](/frontend/src/content/zh/)与[英文文档内容](/frontend/src/content/en/)）开始；`skills/**` 及其专用资料不属于本入口的治理范围。

## 按读者进入

- [开发人员](development/README.md)：开发环境、架构、后端参考、扩展和设计决策。
- [运维人员](operations/README.md)：安装、部署、配置、升级、监控、备份和排障。
- [测试人员](testing/README.md)：测试分层、覆盖矩阵、E2E、真实浏览器测试和迁移账本。
- [架构与治理](architecture/README.md)：系统边界、产品线约束和决策入口。

## 当前权威文档

状态约定：`current` 指导当前工作，`draft` 表示待评审提案，`superseded` 必须指向替代文档，`archived` 只保留历史证据。旧验证记录不能证明当前候选已通过。

每个主题只保留一个当前事实来源；入口页只提供适用范围和跳转，不复制正文。

| 主题 | 当前权威来源 |
| --- | --- |
| 按任务域进入文档 | [任务路由](agents/task-routing.md)：九个常见任务域的当前契约、代码入口、条件决策与验证入口 |
| 用户使用与公开开发 | 公开文档站（部署路由 `/zh/docs`；内容源 [frontend/src/content/zh/](/frontend/src/content/zh/)） |
| 测试覆盖与迁移 | [coverage-matrix.md](testing/coverage-matrix.md)、[test-migration-ledger.md](testing/test-migration-ledger.md) |
| 权限模型与矩阵 | [permission-model-redesign.md](permission-model-redesign.md)、[permission-matrix.md](permission-matrix.md) |
| 离线产品线治理 | [offline-product-line-governance-plan.md](offline-product-line-governance-plan.md) |
| 离线部署作业 | [禁公网内网离线部署作业指导书](deployment/禁公网内网离线部署作业指导书.md) |
| 架构基线 | [架构索引](architecture/README.md)、[项目架构概览](architecture/overview.md)、[后端架构](../backend/docs/README.md) |
| 领域词汇 | [工程术语权威 CONTEXT.md](../CONTEXT.md)、[领域建模指南](agents/domain.md)；[UI 术语对照表](plans/2026-08-26-term-glossary.md) 仅覆盖界面显示语言 |
| Agent 工作流 | [技能路由](agents/skill-routing.md)、[规格与工单发布](agents/issue-tracker.md) |
| 待实现规格与工单 | [GitHub Issues](https://github.com/Orbit-Crew/iDeer/issues)（`to-spec`/`to-tickets` 输出，`ready-for-agent` 标签；[specs/](specs/) 目录为历史归档） |
| 架构决策 | [ADR 与决策索引](decisions/README.md) |
| 上游兼容基线与补丁 | [上游锁定记录](upgrades/deerflow-main-0f7d8709/UPSTREAM_LOCK.md)、[根上游补丁账本](../UPSTREAM_PATCH_LEDGER.md)、[本地运行时补丁账本](local-runtime/PATCH_LEDGER.md) |
| 技能树治理与上游技能升级 | [skill-tree-governance.md](governance/skill-tree-governance.md)（权威关系、锁定 SHA 登记与升级流程；技能包内容本身不属本入口治理范围） |
| 披露阅读会话收集器 | [disclosure-reading-collector-2026-10-07.md](governance/disclosure-reading-collector-2026-10-07.md)（隔离读取、六字段提交与尝试审计） |
| 披露阅读实验最终裁决 | [ticket11 汇总](governance/disclosure-readability-experiment-pdr-2026-10-07-ticket11.md)（32个槽的评分、门槛与限制） |
| 双轨披露阅读票07结果 | [正式结果与审计](experiments/disclosure-dual-track-ticket07-results-2026-10-08.md)（v2评分、物理成本、恢复复算与未通过门槛） |
| 双轨披露实作票08与票09裁决 | [正式结果与条件裁决](experiments/disclosure-dual-track-ticket08-results-2026-10-09.md)（六次隔离实作；因新版门槛未满足，旧轨未执行） |
| 双轨披露票10最终状态 | [四轨状态与最终裁决](experiments/disclosure-dual-track-ticket10-final-verdict-2026-10-09.md)（工程交付、文档卫生、新版未通过、旧轨未执行及恢复证据） |
| 披露分支热点、reviewer 矩阵与验收 | [热点证据](experiments/disclosure-branch-hotspots-2026-10-09.md)、[reviewer-only 适用性矩阵](experiments/disclosure-branch-review-matrix-2026-10-09.md)、[票05 导航验收报告](experiments/disclosure-branch-navigation-acceptance-2026-10-09.md)（仅供评审与评估；不得进入 reader prompts、冻结候选或任务路由） |
| 披露分支与 ROOT 工程交付结项 | [工程交付与测量状态](experiments/disclosure-branch-root-engineering-delivery-2026-10-10.md)（实现已交付；NAV 门禁 incomplete；ROOT 正式阅读未启动并由用户决定延期） |
| 当前工程待办 | [backlog.md](backlog.md) |

## 披露改进规格状态

- [具体改动分支导航](specs/2026-10-09-disclosure-task-branch-navigation-spec.md)与[ROOT GitNexus 指引精简](specs/2026-10-09-root-gitnexus-guidance-compaction-spec.md)的工程实现均已交付并归档。NAV 正式正确性、阅读成本仍 incomplete；ROOT 正式阅读没有启动。用户已决定停止 ROOT 阅读实验。详见[工程交付结项](experiments/disclosure-branch-root-engineering-delivery-2026-10-10.md)及[NAV 验收报告](experiments/disclosure-branch-navigation-acceptance-2026-10-09.md)。

这两份规格分开记录实现与效果。归档状态表示当前工程收尾已记录，不代表任何效果门禁通过；NAV 和 ROOT 的效果状态分别按各自证据报告。

## 历史证据

已结束的计划、审计、事故复盘和阶段总结进入 [`docs/archive/`](archive/README.md)。历史正文已物理迁移，旧路径不保留跳转桩；评估依据见[文档留存必要性评估](document-retention-assessment.md)。

Product release provenance and version records are documented in [release records](releases/README.md). The [branch governance](offline-product-line-governance-plan.md) separates mirror updates, product integration, and compatibility validation.
