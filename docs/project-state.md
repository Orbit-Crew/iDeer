---
id: project-state
kind: reference
status: current
owner: repository maintainers
scope: develop 线候选的七域实现/集成/验证状态摘要
last-verified: 2026-10-06
verified-against: develop @ 002b29878 plus this worktree; document governance section only
---

# 项目状态（候选口径）

> audience: coding agents, developers, maintainers<br>
> canonical-path: `docs/project-state.md`

本页包含不同候选的领域快照。**2026-10-06 仅重核文档治理与本页第 7 节**，基于 `develop @ 002b29878` 加本次修复；第 1–6 节未重跑产品验收，沿用下述原候选记录。

第 1–6 节保留 2026-10-04 文档改造期间的领域快照，原记录涉及 `9de1de284` 与后续文档候选 `ba5c37163`。这些状态尚未在当前 develop 上复核；各节所引证据只适用于其记录的候选，不能据此推断当前产品状态。第 7 节记录本次实际检查的文档治理状态。

状态口径（本页固定词汇）：

- **实现状态**描述能力是否存在于代码树并由跟踪文档记载；决策被接受（accepted）不等于已实现，跟踪文档无实现记录的一律写 `not recorded`。
- **集成状态**描述该能力与其他子系统的接合方式及登记的兼容面（如 harness 补丁、provider 绑定）。
- **验证状态**只承认**当前候选**上的跟踪验证产物；第 1–6 节的产品验收未在本次候选运行；第 7 节的实际检查见修复记录。历史 lane/验收结果仅属于其记录时的候选，一律标注"历史"引用，不构成当前验证。
- **证据**仅引用跟踪文件；gitignored 的 `dev-log/` 与 `.scratch/` 不作为证据。

未完成工作的唯一入口是 [backlog.md](backlog.md)；本页的 next work 只给指针，不在本页复制待办目录，也不在此维护能力目录之外的第二份清单。

## 1. 对话与运行时（chat/runtime）

- **Candidate/branch**: 本页候选（见页首）。
- **Implementation**: Gateway run/thread 路由与 harness 运行时代码在树中（`backend/app/gateway/routers/runs.py`、`backend/packages/harness/deerflow/runtime/runs/manager.py`）；Thread 生命周期、Run 事件流与流式去重契约由 `backend/docs/THREAD_LIFECYCLE.md`、`backend/docs/RUN_EVENT_STREAM.md`、`backend/docs/STREAMING.md` 记载。上游 v2.1.0 已并入本候选历史（合并提交 `85075252a`，经 `git merge-base --is-ancestor 85075252a HEAD` 核对）。
- **Integration**: 运行时相关 harness 补丁（PATCH-002/005/013/026/027 等）在[根补丁台账](../UPSTREAM_PATCH_LEDGER.md)登记为 open，2026-10-01 对照 v2.1.0 复评 keep。
- **Verification**: **not run at this candidate**。[v2.1.0 DoD 清单](upgrades/deerflow-v2.1.0/DoD_CHECKLIST.md)记录的后端全量与 `pr-standard` 结果属于合并候选（提交批次 `1f18d4170..c18d47b59`、候选 `2a7bcd9d4`），为历史记录。
- **Limitations**: 同一 DoD 清单在其候选上记录 `frontend-mock-e2e` 367/414（lane exit 1），剩余失败"登记 develop 跟进"；该缺口在本候选是否仍存在未复验。
- **Evidence**: `backend/docs/THREAD_LIFECYCLE.md`、`backend/docs/RUN_EVENT_STREAM.md`、`backend/docs/STREAMING.md`、[根补丁台账](../UPSTREAM_PATCH_LEDGER.md)、[DoD 清单](upgrades/deerflow-v2.1.0/DoD_CHECKLIST.md)（历史）。
- **Current contract**: [任务路由 · 对话提交与流式状态](agents/task-routing.md)（含 runtime 模块指南与流式契约链接）。
- **Next work**: DoD 清单登记的 mock E2E 跟进项落地并在当前候选复跑；下次上游同步按台账移除条件复评运行时补丁行。
- **Owner**: runtime maintainers（据补丁台账 owner 列）。

## 2. 资源权限（resource permissions）

- **Candidate/branch**: 本页候选（见页首）。
- **Implementation**: 权限模型与角色×操作矩阵为现行契约（[permission-model-redesign](permission-model-redesign.md)、[permission-matrix](permission-matrix.md)）；RBAC/visibility/resource service 代码在树中（`backend/app/gateway/auth/`、`backend/app/agentplatform/resource_service.py`）。
- **Integration**: [Resource Governance V2](decisions/2026-08-14-resource-governance-v2.md) 为 canonical-only 定案：`/api/resources` 唯一资源入口，旧名称路由已删除（[cutover 执行记录](governance/resource-governance-v2-cutover.md) §6，2026-08-15~17）。v2.1.0 合并把上游 `PROJECTS_*` 等权限并入授权并集（DoD 清单记载，历史）。
- **Verification**: **not run at this candidate**。cutover §6 的全量验收（backend 11933 passed 等）是 2026-08-17 候选的历史记录。
- **Limitations**: [backlog](backlog.md) PERM-01（权限模型剩余 API/UI 差异）与 PERM-02（审计日志与错误码核对）未完成；两份权限契约文档 `last-verified` 停在 2026-07-15，早于 v2.1.0 合并。
- **Evidence**: [permission-model-redesign](permission-model-redesign.md)、[permission-matrix](permission-matrix.md)、[V2 决策](decisions/2026-08-14-resource-governance-v2.md)、[cutover 手册](governance/resource-governance-v2-cutover.md)、[backlog](backlog.md)。
- **Current contract**: [permission-model-redesign](permission-model-redesign.md) + 根 `AGENTS.md`"Enterprise changes and upstream compatibility"节。
- **Next work**: [backlog](backlog.md) PERM-01、PERM-02。
- **Owner**: security and platform maintainers。

## 3. KnowledgeBase（知识库）

- **Candidate/branch**: 本页候选（见页首）。
- **Implementation**: [知识双层真源决策](decisions/2026-09-08-knowledge-dual-source-of-truth.md)（accepted）：KB UUID 是唯一企业身份，Provider 只持索引状态真源；知识模块代码在树中（`backend/app/agentplatform/knowledge/`）；修订发布/对账机制经 harness 配套补丁落地。
- **Integration**: RAGFlow provider 兼容 v0.27+ 批量端点（PATCH-001）、检索遥测/端点脱敏/文档级检索范围（PATCH-022）、`KnowledgeConfig` schema（PATCH-023）；检索回执经运行时证据钩子在 Run 完成时归档（PATCH-024/027/028）。均见[根补丁台账](../UPSTREAM_PATCH_LEDGER.md)。
- **Verification**: **not run at this candidate**。[knowledge gate 验收报告](testing/)（gate1/gate8 等）是各自 gate 候选的历史记录；台账 PATCH-022/023/024 行内明确记录"待补"断言。
- **Limitations**: 台账登记的待补测试（knowledge_metric 遥测断言、KnowledgeConfig 专测、扩展注册桶单测）；[总方案](../architecture/AgentPlatform_后续工作总方案_2026-09-08.md) D3 记录 2026-09-08 时点无可用 RAGFlow 实例（当时事实，现状未复核）；正式 Published Dataset 不允许从 Provider 侧直接编辑（决策后果）。
- **Evidence**: [双层真源决策](decisions/2026-09-08-knowledge-dual-source-of-truth.md)、[根补丁台账](../UPSTREAM_PATCH_LEDGER.md)（PATCH-001/022/023/024/027/028）、[知识库实施方案](../architecture/AgentPlatform_知识库能力建设实施方案_CodingAgent版_2026-09-04.md)、`docs/testing/knowledge-gate1-acceptance-report.md`、`docs/testing/knowledge-gate8-acceptance.md`（历史）。
- **Current contract**: 根 `AGENTS.md`"Enterprise interfaces"节（KnowledgeBase 列表/创建走 `/api/resources` 并经治理可见性过滤）+ [双层真源决策](decisions/2026-09-08-knowledge-dual-source-of-truth.md)。
- **Next work**: 补台账"待补"断言；知识主线已过 M4——[M4 Gate 5/6 验收记录](knowledge/M4_GATE_ACCEPTANCE.md)记载 Gate 5/6 于 2026-09-15 验收通过（历史证据），Gate 7 验收见 [M5 验收报告](testing/m5-gate7-acceptance-report.md)（历史）；当前推进指向[总方案](../architecture/AgentPlatform_后续工作总方案_2026-09-08.md) M5 及后续里程碑。
- **Owner**: knowledge 域维护者（据补丁台账 owner 列）。

## 4. Agent / Skill / Workflow（能力资源）

- **Candidate/branch**: 本页候选（见页首）。
- **Implementation**: [资源治理 V2](decisions/2026-08-14-resource-governance-v2.md) 决策状态 `implemented`：canonical-only 已硬切换（cutover §6 记录 2026-08-16 删除旧路由与模式开关）。故障归零执行内核按 [ADR-0004](adr/0004-fault-zeroing-hybrid-intake-and-shared-execution.md) 的 Implementation status（2026-09-29）记录为三入口端到端接线。[ADR-0007](adr/0007-agent-terminology-unification.md) 术语统一迁移已落地——依其 Implementation status 节（2026-10-04 核验，本工作树抽查可证）：`/workspace/agents` 路由与 `agent-*` 组件为 canonical，pre-unification `/workspace/capabilities/experts/*` 路径为永久重定向（`frontend/src` 无 `ExpertList` 与 expert 前缀组件，重定向辅助在 `frontend/src/app/workspace/agents/legacy-redirect.ts`）。
- **Integration**: canonical Run 冻结依赖闭包与技能视图经 PATCH-010/012/013/021（[根补丁台账](../UPSTREAM_PATCH_LEDGER.md)）；bundled seed 幂等升级与冲突语义在 V2 决策内定义。
- **Verification**: **not run at this candidate**。cutover §6 全量验收与 ADR-0004 所引集成测试（`backend/tests/` 内文件在树中存在）均为历史记录或未运行状态。
- **Limitations**: 平台级 SRS Result Contract 缺口按 [ADR-0006](adr/0006-srs-validation-defers-result-contract.md) 递延并立项 [backlog](backlog.md) SRS-01；ADR-0006 附录记录会话 canonical Run 服务"已安装版本"而非"快照冻结版本"的残余权衡，及其按 frontmatter `name` 过滤的既存失效模式；ADR-0007 的"半途迁移"重评触发已随迁移落地（2026-10-04）解除，其余重评触发见该 ADR。
- **Evidence**: [V2 决策](decisions/2026-08-14-resource-governance-v2.md)、[cutover 手册](governance/resource-governance-v2-cutover.md)、[ADR-0002](adr/0002-code-evidence-package-static-analysis.md)、[ADR-0004](adr/0004-fault-zeroing-hybrid-intake-and-shared-execution.md)、[ADR-0006](adr/0006-srs-validation-defers-result-contract.md)、[ADR-0007](adr/0007-agent-terminology-unification.md)、[backlog](backlog.md)。
- **Current contract**: [资源治理 V2 决策](decisions/2026-08-14-resource-governance-v2.md) + [任务路由 · Agent/Skill/Workflow](agents/task-routing.md)。
- **Next work**: [backlog](backlog.md) SRS-01（ADR-0007 迁移落地状态已核对并补实现记录，见其 Implementation status 节）。
- **Owner**: engineering maintainers（据决策 owner 列）。

## 5. 本地运行时（local runtime）

- **Candidate/branch**: 本页候选（见页首）；域内历史交付记录使用其自有候选（见 Verification）。
- **Implementation**: 设备控制面 `backend/app/device_control/` 与 `local-runtime/` 在树中；M7 边界由[本地运行时架构](local-runtime/ARCHITECTURE.md)固定；M9 交付项（tray/pairing、会话失效、配置闭环、Streamable HTTP、Windows 凭据迁移）由[本地运行时补丁账本](local-runtime/PATCH_LEDGER.md)记录为不触及共享 harness。
- **Integration**: 经 `agentplatform-extension` 与 broker 协议接入；ExecutionTarget（[一等运行维度决策](decisions/2026-09-08-execution-target-first-class-dimension.md)）与双层授权（[本地否决权决策](decisions/2026-09-08-local-authorization-veto.md)）为语义基准；[本地安全模型](local-runtime/SECURITY_MODEL.md)固定"Server 授权委派、设备授权执行"。
- **Verification**: **not run at this candidate**。[M9 交付报告](local-runtime/M9_DELIVERY_REPORT.md)自我标注 lane 表为历史结果（候选 `feature/m9-local-mcp-secrets-tray` @ `2892a4fb`）。
- **Limitations**: 交付报告记录真实模型行为验收未完成（请求返回 HTTP 400）；`backend-llm` lane 因凭据契约继续跳过 11 项；本地执行走独立 `local-runtime` 专项 lane，Linux 开发环境保留受限文件回退（账本）。
- **Evidence**: [本地运行时补丁账本](local-runtime/PATCH_LEDGER.md)、[本地运行时架构](local-runtime/ARCHITECTURE.md)、[本地安全模型](local-runtime/SECURITY_MODEL.md)、[M9 交付报告](local-runtime/M9_DELIVERY_REPORT.md)（历史）、[测试矩阵](local-runtime/TEST_MATRIX.md)。
- **Current contract**: [本地安全模型](local-runtime/SECURITY_MODEL.md) + [任务路由 · 本地运行时补丁](agents/task-routing.md)。
- **Next work**: 交付报告记录的模型行为验收闭环；未来任何共享 harness 改动先在[本地运行时补丁账本](local-runtime/PATCH_LEDGER.md)加行。
- **Owner**: unknown（账本未记录单一 owner）。

## 6. 上游集成（upstream integration）

- **Candidate/branch**: 本页候选（见页首）。
- **Implementation**: harness 补丁 PATCH-001..032 全量登记于[根补丁台账](../UPSTREAM_PATCH_LEDGER.md)：2026-10-01 对照 `0f7d8709` 44 文件零未登记、对照 `v2.1.0` 差异集零未映射。上游 v2.1.0 已并入本候选历史（合并提交 `85075252a`，经 `git merge-base --is-ancestor` 核对）。
- **Integration**: 收敛轨按 minor tag 吸收（[离线产品线治理方案](offline-product-line-governance-plan.md)）；v2.1.0 轮次档案在 `docs/upgrades/deerflow-v2.1.0/`（[锁定记录](upgrades/deerflow-v2.1.0/UPSTREAM_LOCK.md)、[冲突台账](upgrades/deerflow-v2.1.0/CONFLICT_LEDGER.md) 96 项处置、[DoD 清单](upgrades/deerflow-v2.1.0/DoD_CHECKLIST.md)）。
- **Verification**: **not run at this candidate**。DoD 清单的全量验证与 PATCH-001..032 复评属 2026-10-01 合并候选的历史记录。
- **Limitations**: (1) `backend/packages/harness/pyproject.toml` 携带未登记本地差异（`python-docx>=1.1.2`，提交 `7ae6b5907`），在 canonical 对照命令路径之外，台账移交后续补登记或明确豁免；(2) [v2.1.0 锁定记录](upgrades/deerflow-v2.1.0/UPSTREAM_LOCK.md)仍把 `0f7d8709` 列为 "currently locked baseline SHA"，合并之后尚无更新"有效锁定 SHA"的跟踪记录；(3) [离线产品线治理方案](offline-product-line-governance-plan.md)（`last-verified: 2026-10-01`）写明"当前兼容基线仍为 `0f7d8709`"，该句与已并入候选历史的 v2.1.0 合并提交并存，两种口径的裁决未见跟踪记录；(4) v2.1.0 轮新增 17 个 harness 文档，台账文档预算由 44 修订为 61。
- **Evidence**: [根补丁台账](../UPSTREAM_PATCH_LEDGER.md)、[v2.1.0 锁定记录](upgrades/deerflow-v2.1.0/UPSTREAM_LOCK.md)、[v2.1.0 冲突台账](upgrades/deerflow-v2.1.0/CONFLICT_LEDGER.md)、[v2.1.0 DoD 清单](upgrades/deerflow-v2.1.0/DoD_CHECKLIST.md)、[离线产品线治理方案](offline-product-line-governance-plan.md)、[0f7d8709 锁定记录](upgrades/deerflow-main-0f7d8709/UPSTREAM_LOCK.md)（冻结历史）。
- **Current contract**: 根 `AGENTS.md`"Enterprise changes and upstream compatibility"节 + [根补丁台账](../UPSTREAM_PATCH_LEDGER.md) + [离线产品线治理方案](offline-product-line-governance-plan.md)。
- **Next work**: pyproject 差异补登记或豁免；合并后有效锁定 SHA 登记；按治理方案完成产品升级验收并建立 `product/offline-2.x`。
- **Owner**: 各 PATCH 行 owner 见台账；域级 unknown（无单一跟踪记录）。

## 7. 验证基础设施（validation infrastructure）

- **Candidate/branch**: 本页候选（见页首）。
- **Implementation**: lane 执行器 `scripts/run-test-lane.sh`、测试清单 `scripts/test_inventory.py`、运行前检查 `scripts/test_preflight.py`、只读文档检查器 `scripts/check_documents.py` 在树中；lane 契约、覆盖映射与迁移账本由 [testing 文档群](testing/README.md)承载。
- **Integration**: Make 与 GitHub Actions 作为 lane 适配器（[覆盖矩阵](testing/coverage-matrix.md)规则记载）；文档治理清单与保护文件指纹由 `docs/governance/document-policy.json` 承载，检查器按候选校验清单覆盖、链接、权威唯一性、路由与 supersession。
- **Verification**: `develop @ 002b29878` 的文档检查为 0 findings、28 对指引一致、67 个保护指纹匹配。检查器当时仍漏查 supplements 正文与任务路由；本次修复以 CLI 回归测试补齐检查。产品 lane 结果与阅读复测结果见[本次修复记录](governance/disclosure-review-fixes-2026-10-06.md)，不得沿用旧候选的验收结果。
- **Limitations**: 覆盖矩阵的行为→测试层映射未在本候选复核，且按规格不得以批量刷新验证日期代替内容审查；[覆盖矩阵](testing/coverage-matrix.md)记载 PR standard lane "先 shadow 两周后转 blocking"，其转换是否已发生未在本候选复核。
- **Evidence**: [测试入口](testing/README.md)、[lane 运行手册](testing/test-lane-runbook.md)、[覆盖矩阵](testing/coverage-matrix.md)、[迁移账本](testing/test-migration-ledger.md)、`scripts/check_documents.py`、`docs/governance/document-policy.json`。
- **Current contract**: [测试入口](testing/README.md) + [lane 运行手册](testing/test-lane-runbook.md) + 根 `AGENTS.md` 测试指引节。
- **Next work**: 覆盖矩阵内容复核（对照当前候选与 v2.1.0 后的测试面，不得只刷日期）；文档治理原 59 票已完成并合入，后续补强也已合入；本次审查缺口及验收状态见修复记录。
- **Owner**: test maintainers（据 testing 文档 owner 列）。
