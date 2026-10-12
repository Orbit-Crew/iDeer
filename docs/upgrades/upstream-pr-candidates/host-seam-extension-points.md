---
id: docs-upgrades-upstream-pr-candidates-host-seam-extension-points
kind: plan
status: current
owner: convergence maintainers
scope: 上游 PR 候选（02-M6，整改票 #64）：bytedance/deer-flow harness 三个企业接缝（工具装配 tool-scope、子代理组装 middleware、builtin 工具覆盖）的注册/consult 扩展点；条件性 rider（上游今日无对应缝），随下轮收敛轨与 P003/P011/P014/P032 及 registry-duplicate-evidence-hooks 并列 reassess，不作为本仓库长期门禁
last-verified: 2026-10-13
verified-against: 上游 deerflow/main（81fa17c15ab）与 v2.1.0（345f08be0）比对——get_available_tools 尾端、SubagentExecutor._create_agent、_assemble_lead_agent 的 builtin 绑定处均无任何扩展点 consult；extensions registry 也无对应桶（fork 本地扩展面，引入见台账 PATCH-039/040/041，2026-10-13 票 64 行）
---

# 上游 PR 候选：harness 企业接缝扩展点（02-M6，票 64）

- 状态：候选（条件性 rider；待下轮收敛轨一并 reassess；提交流程见
  `docs/offline-product-line-governance-plan.md` §修复轨/补丁卫生）。
- 目标上游仓库：`bytedance/deer-flow`（分支 `main`）。
- 来源:发现 02-M6（代码复审 2026-10-07）；本地重构见票 #64（台账 PATCH-039/
  040/041，`UPSTREAM_PATCH_LEDGER.md` 巡检记录 2026-10-13 票 64 行）。
- 上游比对结论：`deerflow/main`（81fa17c15ab）与 v2.1.0（345f08be0）的
  `tools/tools.py` / `subagents/executor.py` / `agents/lead_agent/agent.py`
  均无等价扩展点——三个 consult 调用点与 registry 三个桶全部为 fork 本地
  新增。因此本候选定位为条件性 rider：上游今天没有可被直接瞄准的同病代码，
  任何一个等价扩展缝（host 定制工具列表、子代理 middleware 贡献、builtin
  覆盖）若以任何形式上提上游，其确定性单 provider 语义与 consult 模式必须
  随提案原生携带，不得让"静默 last-wins/叠加"或"进程全局改写"进入上游。

## 三个缝与本地参考实现

| 缝 | consult 点 | registry 桶 | 桶语义 |
| --- | --- | --- | --- |
| 工具装配 tool-scope | `get_available_tools` 返回前 | `tool_scopes(ToolScopeAdapter)` | 单 provider（重复注册注册期 `ValueError`） |
| 子代理组装 middleware | `SubagentExecutor._create_agent` 链组装后 | `subagent_middlewares(SubagentMiddlewareSource)` | 单 provider |
| builtin 工具覆盖 | `_assemble_lead_agent` builtin 绑定处 | `builtin_tools(BuiltinToolOverrides)` | 单 provider |

单 provider 理由（三缝同构，与 #63 runtime evidence 一致）：每个缝的解析结果
都是"一个"对象/策略——一份对整份工具列表的授权收窄、一个当前执行上下文的
middleware 投影、一组对 host 单例 builtin 的覆盖决定。两个 provider 组合要么
顺序敏感（收窄叠加）、要么无合并规则（上下文投影、同名覆盖），静默 last-wins
或 append 都会把配置错误变成运行期行为漂移；注册期显式拒绝（指认既有注册方）
+ loader 既有回滚/诊断路径是确定性处置。解析链
`extensions 参数 → 进程 loaded 集 → 进程默认` 对照
`resolve_runtime_evidence_hooks` 先例（`deerflow/extensions/__init__.py`）。

## PR 草稿（条件性：随任一等价缝上提时携带）

- **标题**: `feat(extensions): single-provider host seams for tool scopes, subagent assembly middlewares and builtin tool overrides`
- **动机**: 宿主定制（企业授权收窄、执行上下文中间件、builtin 规范化替换）
  若无第一方扩展点，只能靠导入期改写上游模块属性——进程全局、不可归因、
  与扩展装载生命周期脱钩。三个缝把定制收敛到注册契约：无 provider 时上游
  行为零变化；有 provider 时行为在 consult 点可归因（LoadedExtensions 携
  source）。
- **修复要点**:
  1. registry 增三个单 provider 桶，重复注册抛 `ValueError` 命名既有/被拒
     source（复用 #63 语义），经 install() 传播由 loader 失败路径处置；
  2. 三个 consult 点（工具装配尾端、`_create_agent` 链后 append、builtin
     绑定处 resolve，default 回退 stock）——provider 缺失时零行为变化；
  3. 解析函数镜像 `resolve_runtime_evidence_hooks` 的三层回退；进程默认
     setter 供非 loader 宿主组合点注册（同对象幂等、异对象拒绝）。
- **测试**: registry 桶重复拒绝（跨源/同源）、loader 双 spec 显式失败回滚
  +required 中止、三 consult 点"无 provider 原样/有 provider 生效"合同、
  子进程探针（import 不留下进程全局改写）。

## diff 草稿（参考实现，票 #64 expand 落地）

上游无对应代码，以下为本仓 fork 内已落地的最小参考实现（引入见台账
PATCH-039/040/041）。关键形态：

```python
# registry（单 provider 桶，同 PATCH-038 runtime_evidence 语义）
def tool_scopes(self, adapter: ToolScopeAdapter) -> None:
    self._register_single(self._tool_scopes, "tool scopes", adapter)

# consult（tools/tools.py，get_available_tools 返回前）
scope_adapter = resolve_tool_scopes(None)
if scope_adapter is not None:
    unique_tools = list(scope_adapter.apply_tool_scopes(unique_tools, subagent_enabled=subagent_enabled))
return unique_tools

# consult（subagents/executor.py，_create_agent 链组装后）
middleware_source = resolve_subagent_middlewares(extensions)
if middleware_source is not None:
    pending = list(middleware_source.pending_middlewares() or ())
    if pending:
        middlewares = [*middlewares, *pending]

# consult（agents/lead_agent/agent.py，builtin 绑定处）
builtin_overrides = resolve_builtin_tool_overrides(None)
if builtin_overrides is not None:
    setup_agent = builtin_overrides.resolve_builtin_tool("setup_agent", setup_agent)
```

## 本地验证证据（2026-10-13，票 #64 expand 阶段）

- `tests/unit/workflows/test_v2_executor_bridge_seam_contract.py`：两轨
  fail-closed 矩阵与行为等价、无 provider 直通、子进程探针（registry 轨
  断言 `deerflow.tools.get_available_tools`/`deerflow.subagents.executor.create_agent`
  与 stock 同一性；legacy 轨锁定旧改写仍在——contract 批次翻转）；
- `tests/unit/gateway/test_subagent_executor.py`：seam 在上游链后 append
  pending middlewares（无 provider / 空 pending / 非空 pending 三态）；
- `tests/unit/agentplatform/test_agent_bootstrap_seam.py`：builtin 覆盖缝
  两轨探针、install 幂等、canonical 行为（空 soul 拒绝 / 默认 SOUL 落盘 /
  无 session factory 回退 agent store）；
- `tests/test_extension_registry.py` / `tests/test_extension_loader.py` /
  `tests/test_agentplatform_extension_boundary.py`：三桶重复拒绝、loader
  失败路径、解析链三层回退与进程默认注册语义。
