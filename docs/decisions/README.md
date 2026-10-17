---
id: docs-decisions-readme
kind: index
status: current
owner: repository maintainers
scope: topic index for ADRs and dated decisions giving each record's one-line conclusion, scope, full-record trigger, and implementation/validation pointers; the linked decision bodies remain the authority for their content
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ b9e0ca1c3
---

# 设计决策

> audience: developers, architects, maintainers<br>
> status: current<br>
> owner: repository maintainers<br>
> last-verified: 2026-10-04<br>
> canonical-path: `docs/decisions/README.md`

决策状态使用 `current`、`draft`、`superseded` 或 `archived`。新 ADR 放在 `docs/adr/`，按 `NNNN-topic-name.md` 编号命名（这是全仓库统一的 ADR 命名规则，其他文档引用本约定）；既有 dated decision 保留在本目录。新增或变更决策时，同时更新本索引。

决策被接受只回答"定了什么"，不代表已实现或已验证；实现/集成/验证的候选级状态见[项目状态页](../project-state.md)。本索引按主题组织；每条给出一句话结论（出处为对应决策正文）、适用范围（scope）、何时读全文（trigger）与实现/验证指针。复议条件（reconsider-when）只在决策正文有记录时列出，不代决策正文发明结论。

## 按主题索引

### 工作台与产品形态（workbench / product）

- [0001 Workbench capability navigation](../adr/0001-workbench-capability-navigation.md) — 持久工作台导航收敛为五个入口，Expert-Skill-Connector 是单一能力中心并替代 Settings 的 Skill/Tool 入口，Memory 仍留 Settings。
  - scope：前端工作台导航与能力页动作统一；不改所有权、可见性与管理员权限边界。
  - trigger：调整工作台导航结构或能力页生命周期动作时读全文。
  - 实现/验证：[任务路由 · 普通前端组件](../agents/task-routing.md)；本决策被 [ADR 0005](../adr/0005-preserve-workbench-experience-when-adopting-deerflow-features.md) 细化（refined-by）。
- [0005 Preserve workbench experience when adopting DeerFlow features](../adr/0005-preserve-workbench-experience-when-adopting-deerflow-features.md) — 采纳 DeerFlow 能力时保留既有工作台体验：custom Agent 进 Expert 页、Skill 管理与 MCP 配置进 Skill/Connector 页、Scheduled Tasks 取独立入口。
  - scope：上游能力采纳的前端落位；本决策 refines [ADR 0001](../adr/0001-workbench-capability-navigation.md)。
  - trigger：把上游/DeerFlow 能力引入前端时读全文。
  - 实现/验证：[任务路由 · 普通前端组件](../agents/task-routing.md)。

### 术语与命名（terminology）

- [0007 Agent terminology unification](../adr/0007-agent-terminology-unification.md) — 代码与路由词汇统一为 "agent"，"专家"仅是 zh-CN 显示词；数据源不动，`/api/resources` 仍是唯一真源。
  - scope：路由/组件/测试命名与 locale 显示词；不重开资源数据源问题（由资源治理 V2 定案）。
  - trigger：改 Agent/Skill 命名或中英文显示词，或上游收敛需要做路径映射时读全文。
  - reconsider-when（正文有记录）：产品包装要求"专家"成为代码级品牌概念；上游重命名该概念本身；迁移半途停滞（同一收敛轮内完成或回退）。
  - 实现/验证：迁移落地状态未在跟踪文档记录（见[项目状态页 §4](../project-state.md)）；验证入口[任务路由 · Agent/Skill/Workflow](../agents/task-routing.md)。

### 资源治理与权限（resource governance）

- [Skill、Agent、Workflow 资源治理 V2](2026-08-14-resource-governance-v2.md) — 三类能力资源统一为 UUID 版本化的单一真源，canonical-only（无模式开关、旧名称路由删除）；每次新 Run 先解析完整依赖闭包并冻结快照。
  - scope：资源目录数据模型、存储与发布一致性、授权模型、依赖/运行/撤权、生命周期/转移/Fork、bundled seed 与迁移。
  - trigger：改资源生命周期、可见性、运行解析，或部署升级/回滚/bundled seed 时读全文；部署操作另读 [cutover 手册](../governance/resource-governance-v2-cutover.md)。
  - 实现/验证：决策头 `status: implemented`；执行记录见 [cutover §6](../governance/resource-governance-v2-cutover.md)（2026-08-17，历史）；验收矩阵见 [resource-governance-v2-acceptance-matrix](../testing/resource-governance-v2-acceptance-matrix.md)（历史记录）。当前候选的验证状态见[项目状态页 §2/§4](../project-state.md)。

### 知识（knowledge）

- [知识双层真源：治理真源与索引真源分离](2026-09-08-knowledge-dual-source-of-truth.md) — KB UUID 是唯一企业身份，Provider 只持索引状态真源，provider dataset ID 只是外部映射且模型不可接触。
  - scope：KB 身份与 Revision 语义、Provider 绑定与整体替换、三层职责分工（AgentPlatform 治理 / Provider 索引 / Harness 运行时）。
  - trigger：改知识数据流、Provider 对账，或接入第二 Provider 时读全文。
  - 实现/验证：知识模块 `backend/app/agentplatform/knowledge/`；验证入口[任务路由 · KnowledgeBase](../agents/task-routing.md)；gate 验收报告为历史证据。当前候选的验证状态见[项目状态页 §3](../project-state.md)。

### 本地执行与运行时维度（local execution / runtime dimensions）

- [ExecutionTarget 作为一等运行维度](2026-09-08-execution-target-first-class-dimension.md) — 执行位置显式声明为 `SERVER | USER_DEVICE`，禁止同一 Server Tool 按运行环境悄悄切换为本地执行。
  - scope：Workflow Step 执行声明字段、Run 冻结执行定位、`local.*` 名称仅作内部路由键。
  - trigger：改 Workflow Step 执行字段或设备任务路由时读全文。
  - reconsider-when（正文有记录）：上游 DeerFlow 引入等价执行位置抽象时，迁移至上游语义并撤销本地枚举。
  - 实现/验证：[任务路由 · 本地运行时补丁](../agents/task-routing.md)；[项目状态页 §5](../project-state.md)。
- [双层授权与本地否决权](2026-09-08-local-authorization-veto.md) — Server 决定"是否允许委派"、设备本地决定"是否允许执行"，两层必须同过，Local DENY 永远优先于 Server ALLOW。
  - scope：Assembly/Resource Scope 授权、设备本地复核、风险三级与 consent 绑定 request hash、outbound 通信方向。
  - trigger：改本地执行授权、consent 语义或 allowed roots 时读全文。
  - 实现/验证：[本地运行时安全模型](../local-runtime/SECURITY_MODEL.md)；[任务路由 · 本地运行时补丁](../agents/task-routing.md)；[项目状态页 §5](../project-state.md)。
- [批次 6 产品语义确认包](2026-10-15-product-semantics-decision-package.md) — 四项审查"待确认"统一裁决：archived 仅拦新增使用、不打断在途冻结快照（记录确认）；知识部署层 veto 工具未配置即拒绝、`datasets` 属性缺省不设限（改代码）；`list_devices` 管理员全局可见为显式设计（记录确认）；NetworkPolicy 判定补齐私网变体与元数据端点、DNS 级校验列为接线前条件（改代码）。
  - scope：资源运行时加载生命周期语义、知识 scope 部署层 veto 缺省、设备列表可见性边界、扩展侧 NetworkPolicy 判定口径。
  - trigger：改 `CanonicalResourceLoader` 生命周期检查、知识 scope veto 解析、设备列表路由授权或 NetworkPolicy 判定时读全文。
  - 实现/验证：`knowledge/scope.py` `deployment_allowed_datasets()`；回归见 `tests/unit/workflows/test_v2_knowledge_freeze.py` 与 `tests/test_agentplatform_extension_boundary.py`。

### 故障归零证据与结果契约（fault-zeroing evidence and result contracts）

- [0002 Code evidence package static analysis](../adr/0002-code-evidence-package-static-analysis.md) — 代码证据走只读 ZIP 证据包加隔离沙箱静态分析，平台不构建、不执行提交程序。
  - scope：代码证据端点与保留、扫描器契约与首个 C 规则档。
  - trigger：改代码证据端点、沙箱分析或扫描器 profile 时读全文。
  - 实现/验证：harness PATCH-007/008（[根补丁台账](../../UPSTREAM_PATCH_LEDGER.md)）。
- [0004 Fault-zeroing hybrid intake and shared execution](../adr/0004-fault-zeroing-hybrid-intake-and-shared-execution.md) — 每个新故障归零 Run 用混合证据接收与同一 Workflow 执行内核，Skill/Expert/Workflow 三入口不漂移。**supersedes: [ADR 0003](../adr/0003-fault-zeroing-evidence-modes.md)**。
  - scope：证据侧判定、Result Contract 版本固定、三入口接线与遗留模式退出。
  - trigger：改故障归零 intake、内核完成判定或三入口行为时读全文。
  - 实现/验证：ADR 正文 Implementation status（2026-09-29）记录端到端接线与等价性集成测试（该候选记录）；当前候选的验证状态见[项目状态页 §4](../project-state.md)。
- [0003 Fault-zeroing evidence modes](../adr/0003-fault-zeroing-evidence-modes.md) — **superseded**：已被 [ADR 0004](../adr/0004-fault-zeroing-hybrid-intake-and-shared-execution.md) 替代（replacement），原"document/code/hybrid 三模式选择"结论不再适用。
  - scope：仅历史；现行语义以 ADR-0004 为准。
  - trigger：仅在追溯证据模式设计史时读全文。
- [0006 SRS validation defers result contract](../adr/0006-srs-validation-defers-result-contract.md) — SRS 输出校验暂留 srs-writing Skill 内保底，平台级 Result Contract 递延并立项为 backlog 事项。
  - scope：Skill 内校验器形态、平台级 SRS Result Contract 的边界与代价。
  - trigger：改 SRS 校验、Run 完成判定或 Skill 冻结挂载时读全文。
  - reconsider-when（正文有记录）：SRS Run 非交互启动（调度器/渠道）导致确认门不可用；校验规则需跨 Skill 版本强一致；同类 Skill 增殖导致逐 Skill 校验器重复维护；真实事故交付了校验器未运行过的产物。
  - 实现/验证：立项指针 [backlog SRS-01](../backlog.md)；canonical 会话挂载翻译层记录见 ADR 附录（2026-09-29）。

### 上游同步与产品线（upstream sync / product lines）

- [离线产品线治理方案](../offline-product-line-governance-plan.md) — 团队仓库（origin）独立开发离线能力、deerflow 只读上游；收敛轨按 minor tag 吸收、修复轨仅安全/阻断缺陷；`main` 只做快进镜像。
  - scope：双轨上游策略、分支与发布模型、冲突裁决漏斗、补丁卫生与产品升级验收。
  - trigger：分支与产品线治理、上游收敛决策或产品升级验收时读全文。
  - 实现/验证：镜像流程与验收条款在同文；[根补丁台账](../../UPSTREAM_PATCH_LEDGER.md)是 harness 补丁唯一权威登记处。兼容基线口径的已知出入见[项目状态页 §6](../project-state.md)。

### 跨线里程碑编排（cross-line orchestration）

- [后续工作总方案（三线统一编排与决策记录）](../../architecture/AgentPlatform_后续工作总方案_2026-09-08.md) — Knowledge 主线先行（设备控制面 M7 是唯一并行线）；统一迁移链并关闭 PATCH-006 是 M2 硬前置，PATCH-009 全量 DB 验证是 M10 硬前置（决策记录 D1–D5）。
  - scope：里程碑顺序、硬前置与任务卡切片纪律；不替代基线与专项方案。
  - trigger：规划或启动里程碑、判定补丁关闭顺序时读全文；注意其状态基线为 2026-09-08，属时点记录。
  - 实现/验证：各里程碑交付以当时候选的验收记录为准；当前候选状态见[项目状态页](../project-state.md)。

### 测试资产治理（test suite governance）

- [backend/tests 双目录同名副本去重：采纳迁移收尾](2026-10-13-backend-test-dedup.md) — 148 对根/子目录同名测试副本按"根副本为合并基、子目录为规范位置"完成迁移收尾（选项 a），拒绝把双跑登记为已知状态；`tests/blocking_io/` 与根目录独有文件不在去重范围。
  - scope：backend/tests 同名测试副本的去重口径、冲突裁决规则与守卫机制；不改产品代码与用例语义归属。
  - trigger：移动/删除 backend 测试文件、解释 test-migration-ledger 2026-07-09 批次与现状的矛盾、或收到重复收集守卫报红时读全文。
  - 实现/验证：批次记录见 [test-migration-ledger](../testing/test-migration-ledger.md)；守卫为 `scripts/check_test_collection_duplicates.py`。

## 历史与专项设计

- [内网源码导入取舍分析（历史）](../archive/2026/decisions/intranet-source-import-decision-2026-07-15.md)
- [Superpowers 设计记录](../superpowers/specs/)

已结束决策进入[历史归档](../archive/README.md)，本目录的 dated decision 使用 `YYYY-MM-DD-topic-name.md` 命名，新 ADR 使用上面的编号约定。
