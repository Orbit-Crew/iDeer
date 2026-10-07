---
id: task-routing
kind: index
status: current
owner: repository maintainers
scope: nine engineering task domains
---

# Task Routing

按任务域进入文档的路由页。根 `AGENTS.md` 只承载全局义务；本页是全局规则与模块参考之间的指针层，为九个常见任务域各给出四元组：当前契约（读哪些文档）、代码入口（真实路径）、条件决策（何时读哪个 decision/ledger）、验证入口（聚焦检查 → lane → PR gate 的第一跳）。

每个指针 = 目标内容一句话 + 触发条件。本页不复制目标文档正文；链接目标必须真实存在。

配套入口（不与本页重复）：

- [工程文档入口](../README.md)：按读者与主题的文档索引。
- [技能路由](skill-routing.md)：何时调用哪个技能、阶段边界与优先级。
- [本地规格与工单](issue-tracker.md)：spec 与工单的存放与流转约定。
- [领域建模指南](domain.md)：术语与 ADR 的维护流程。
- [决策索引](../decisions/README.md)：ADR 与 dated decision 的总索引。

## 停止条件

当以下五项已识别，停止读文档，开始源码验证：

1. 编辑入口——要改的代码路径；
2. 适用约束——当前契约文档；
3. 相关决策——任务触及时才读的 decision/ledger；
4. 验证路径——聚焦检查 → lane → PR gate 的第一跳；
5. 未决状态——是否存在未实现的 spec、待办或已知限制。

决策全文、账本历史、验收报告等其余材料都是条件阅读：只在本页标注的触发条件命中时打开。文档阅读不以"读得多"为目标；历史测试结果永远不能满足当前候选的验证。

## 1. 普通前端组件（UI-only 变更）

- **当前契约**：[frontend/AGENTS.md](../../frontend/AGENTS.md)——前端模块约定与命令（任务涉及前端目录时读）；[CONTEXT.md](../../CONTEXT.md)——工程术语权威（工作台、Scenario Tab/Agent Pill/Task Chip 等用词拿不准时读）。
- **代码入口**：UI 组合在 `frontend/src/components/`（工作台组件在 `frontend/src/components/workspace/`），领域逻辑在 `frontend/src/core/`，路由在 `frontend/src/app/`。
- **条件决策**：把上游/DeerFlow 能力引入前端时读 [ADR 0005](../adr/0005-preserve-workbench-experience-when-adopting-deerflow-features.md)（保留工作台体验基线）；调整能力导航结构时读 [ADR 0001](../adr/0001-workbench-capability-navigation.md)。
- **验证入口**：聚焦 Vitest 用例放 `frontend/tests/unit/`，跑 `cd frontend && pnpm check`；实现完成跑 frontend 标准 lane；PR gate 为 `pr-standard`。

## 2. 对话提交与流式状态（chat submit / stream state）

- **当前契约**：[deerflow runtime 模块指南](../../backend/packages/harness/deerflow/runtime/AGENTS.md)——运行时模块的现行约束（任务涉及 `backend/packages/harness/deerflow/runtime/` 时读）；[STREAMING.md](../../backend/docs/STREAMING.md)——流式事件语义与按 message-id 去重不变量（改流式交付或消息合并时读）；[CONTEXT.md](../../CONTEXT.md)——Thread/Run/Turn 术语。
- **代码入口**：Gateway 侧 `backend/app/gateway/routers/runs.py`、`backend/app/gateway/routers/thread_runs.py`；运行时侧 `backend/packages/harness/deerflow/runtime/runs/manager.py` 与 `backend/packages/harness/deerflow/runtime/stream_bridge/`；前端 `frontend/src/core/api/client.ts` 与 `frontend/src/components/workspace/chats/`，提交链、重复提交围栏、草稿与附件预上传由 `frontend/src/core/threads/turn-submit.ts` 承担；流式状态在 `frontend/src/core/threads/hooks.ts`；`frontend/src/core/threads/use-thread-page.ts` 负责页面共享接线（聊天页 `frontend/src/app/workspace/chats/[thread_id]/page.tsx` 经 `useThreadPage` 接线）。
- **条件决策**：触及线程生命周期时读 [THREAD_LIFECYCLE.md](../../backend/docs/THREAD_LIFECYCLE.md)；改 run 事件流时读 [RUN_EVENT_STREAM.md](../../backend/docs/RUN_EVENT_STREAM.md)；触及 Run/Thread 生命周期、持久化或流契约时遵循根 `AGENTS.md`"Enterprise changes and upstream compatibility"节的保留约束。
- **验证入口**：聚焦 pytest（`backend/tests/`）+ 最窄静态检查；实现完成跑匹配的标准 lane；PR gate 为 `pr-standard`。

## 3. 资源授权（visibility / RBAC / 权限）

- **当前契约**：[permission-model-redesign.md](../permission-model-redesign.md)——授权模型设计（改授权语义前读）；[permission-matrix.md](../permission-matrix.md)——角色 × 操作矩阵（判断某角色能否做某事时读）。
- **代码入口**：`backend/app/gateway/auth/`、`backend/app/gateway/routers/visibility_applications.py`、`backend/app/agentplatform/rbac_models.py`、`backend/app/agentplatform/visibility_models.py`、`backend/app/agentplatform/resource_service.py`。
- **条件决策**：涉及设备/本地执行的授权时读[双层授权与本地否决权决策](../decisions/2026-09-08-local-authorization-veto.md)；涉及资源可见性生命周期时读[资源治理 V2 决策](../decisions/2026-08-14-resource-governance-v2.md)。
- **验证入口**：auth/RBAC 变更必须跑匹配的标准 lane 与 `pr-standard`，并补齐对应 contract/integration 检查；GitHub Actions 对保护高危路径选择 Real E2E 时，交接 PR 须报告该选择（根 `AGENTS.md` 测试指引）。

## 4. KnowledgeBase（知识库）

- **当前契约**：根 `AGENTS.md`"Enterprise interfaces"节——KnowledgeBase 列表/创建走 `/api/resources` 并经 Resource Governance 可见性过滤，provider 基础设施绑定留在服务端（编辑 Knowledge Center 行为前读）；[知识双层真源决策](../decisions/2026-09-08-knowledge-dual-source-of-truth.md)——治理真源与索引真源的分工（改知识数据流时读）。
- **代码入口**：`backend/app/agentplatform/knowledge/`、`backend/app/gateway/routers/admin_knowledge.py`、资源目录 `backend/app/gateway/routers/resources.py`。
- **条件决策**：涉及资源生命周期（发布/可见性/fork）时读[资源治理 V2 决策](../decisions/2026-08-14-resource-governance-v2.md)；`docs/testing/` 下的 knowledge gate 验收报告是历史证据，仅在追溯验收历史时读，不构成当前契约。
- **验证入口**：`/api/resources` 契约的 contract 检查；匹配的标准 lane 与 `pr-standard`。

## 5. Agent / Skill / Workflow（能力资源）

- **当前契约**：[资源治理 V2 决策](../decisions/2026-08-14-resource-governance-v2.md)——draft/publish/visibility/fork/archive 生命周期（改资源目录行为前读）；[CONTEXT.md](../../CONTEXT.md)——Agent/Skill/Workflow/Resource 核心术语。
- **代码入口**：`backend/app/gateway/routers/resources.py`、`backend/app/agentplatform/resource_service.py`、`backend/app/agentplatform/skills/`、`backend/app/agentplatform/workflows/`、harness 技能加载 `backend/packages/harness/deerflow/skills/`。
- **条件决策**：改 Agent/Skill 命名或中英文显示词时读 [ADR 0007](../adr/0007-agent-terminology-unification.md)（Agent 术语统一）；`resources/skills/` 与 `skills/` 下的技能包内容不在工程文档治理范围。
- **验证入口**：匹配的标准 lane 与 `pr-standard`；资源契约变更补对应 contract 检查。

## 6. 本地运行时补丁（local runtime / 设备执行）

- **当前契约**：[本地运行时补丁账本](../local-runtime/PATCH_LEDGER.md)——control-plane（backend/app、local-runtime）补丁登记（每个补丁改动前查、改动后登记 reason/alternatives/impact/validation/owner/removal）；[本地运行时安全模型](../local-runtime/SECURITY_MODEL.md)——本地授权、同意分级与 allowed roots（改本地执行语义前读）；[CONTEXT.md](../../CONTEXT.md)——ExecutionTarget/Local Policy/User Consent 术语。
- **代码入口**：`backend/app/device_control/`、`backend/app/gateway/routers/devices.py`。
- **条件决策**：ExecutionTarget 维度语义时读[一等运行维度决策](../decisions/2026-09-08-execution-target-first-class-dimension.md)；本地否决权时读[双层授权与本地否决权决策](../decisions/2026-09-08-local-authorization-veto.md)；harness 层（`backend/packages/harness/deerflow/`）补丁改登记根 [UPSTREAM_PATCH_LEDGER.md](../../UPSTREAM_PATCH_LEDGER.md)。
- **验证入口**：账本中列出的 patch-specific validation；匹配的标准 lane 与 `pr-standard`。

## 7. 配置与部署（configuration / deployment）

- **当前契约**：[运维入口](../operations/README.md)——安装、部署、配置、升级、排障的入口（部署/配置任务从这里进）；[离线部署作业指导书](../deployment/禁公网内网离线部署作业指导书.md)——内网离线部署的作业规程（离线环境交付时读）；[local ops notes](local-ops-notes.md)——deployment/security/session 文件的本地约定。
- **代码入口**：`config.example.yaml`（含 `config_version` 升级约定）、`docker/`、根 `Makefile`、`scripts/serve.sh`、`scripts/docker.sh`。
- **条件决策**：分支与产品线治理（`main` 仅快进镜像、develop 产品线）时读[离线产品线治理方案](../offline-product-line-governance-plan.md)；新增公开端口前读根 `AGENTS.md` Deployment Notes（nginx loopback 单一入口）。
- **验证入口**：环境问题先跑 `make doctor`；配置 schema 变更需提升 `config.example.yaml` 的 `config_version`；部署变更按作业指导书的检查执行。

## 8. 测试新增与迁移（test addition / migration）

- **当前契约**：[测试入口](../testing/README.md)——测试分层与目录约定（新增测试前读）；[测试 Lane 运行手册](../testing/test-lane-runbook.md)——lane 选择、聚合与交接契约（选 lane 或交接 PR 时读）；[覆盖矩阵](../testing/coverage-matrix.md)——行为到测试层的映射（判断该在哪层加测试时读）。
- **代码入口**：`backend/tests/{unit,integration,contracts}/`、`frontend/tests/{unit,e2e}/`、lane 执行器 `scripts/run-test-lane.sh`、`scripts/test_preflight.py`、`scripts/test_inventory.py`。
- **条件决策**：移动或删除测试时读[测试迁移账本](../testing/test-migration-ledger.md)（并同步登记）；lane 结果复用/重跑规则以 runbook 为准。
- **验证入口**：先跑聚焦测试；新增/移动测试后跑 `python3 scripts/test_inventory.py`；lane 前 preflight（lane runner 自动执行）；PR gate 为 `pr-standard`。

## 9. 上游同步（upstream sync）

- **当前契约**：根 [UPSTREAM_PATCH_LEDGER.md](../../UPSTREAM_PATCH_LEDGER.md)——当前 harness 补丁登记与移除条件（任何 harness 补丁改动前后读）；根 `AGENTS.md`"Enterprise changes and upstream compatibility"节——Extension → Adapter → 注册补丁的优先序、生命周期保留与双向兼容验证要求。
- **代码入口**：`backend/packages/harness/deerflow/`（`deerflow-harness` 包）。
- **条件决策**：追溯 0f7d8709 基线锁定与冲突裁定时读[上游锁定记录](../upgrades/deerflow-main-0f7d8709/UPSTREAM_LOCK.md)（冻结历史，只读）；分支与同步状态（镜像/产品集成/兼容验证分立）时读[离线产品线治理方案](../offline-product-line-governance-plan.md)。路径所有权偏好只是逐项评估的起点；每个冲突仍须按行为和契约单独裁定，并记录采用上游、保留本地或重新实现的理由与验证，不能整文件或全局地优先一方。
- **验证入口**：补丁登记检查 + 定制关闭/开启双向的兼容验证；匹配的标准 lane 与 `pr-standard`。
