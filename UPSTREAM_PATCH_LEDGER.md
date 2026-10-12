# Upstream Patch Ledger

对 `backend/packages/harness/`（上游 DeerFlow harness）的每一处修改必须在此登记，
含测试证据、原因、Owner 与移除条件（架构基线 §"架构不变量"上游修改纪律）。
仅改 `backend/app/`（AgentPlatform 控制面）或 `backend/packages/agentplatform-extension/`
（扩展包）不属上游修改，无需登记。

> **唯一权威登记处**（2026-10-01 起）：本文件是 harness 本地补丁的唯一权威台账。
> 对照命令（2026-10-05 起锁定 v2.1.0）：`git diff 345f08be00c8a9495079b732a39b46aa9af1584e -- backend/packages/harness/deerflow`
> （`345f08be0` 即 `v2.1.0` 标签所指提交；登记裁决见 2026-10-05 巡检行）。
> `docs/upgrades/deerflow-main-0f7d8709/UPSTREAM_PATCH_LEDGER.md` 已冻结为历史档案，
> 后续巡检只更新本文件。

## 巡检记录

| 日期 | 候选 | 结果 |
| --- | --- | --- |
| 2026-09-08 | m0 票 03（deerflow-main-0f7d8709 全量巡检） | 对照 `0f7d8709` 实测 20 个差异文件，全部归属 PATCH-002..015，无未登记差异；上游锁定 `0f7d8709`，各 open 行移除条件均未因上游变化满足，逐项复评结论均为 keep（见下表）。 |
| 2026-09-13 | feature/m4-knowledge-revisions（M4 票 06 Gate 5/6 巡检） | 本轮涉及 `community/ragflow/client.py`（PATCH-001）；未发现未登记的上游修改。GitNexus 在本工作区不可用（无索引、npx 无法引导，见 dev-log），以人工调用方分析替代。 |
| 2026-10-01 | v2.1.0 合并前置（票 01） | 发现 4 个未登记 sandbox 补丁文件并补登记（见 PATCH-016..019）；PATCH-016/017 与上游 v2.1.0 变更重叠。全面对账 44 个 harness 文件（43 个代码文件 + 1 个文档）后另发现 15 个未登记文件，补登记为 PATCH-020..032（其中 `config/app_config.py`、`runtime/runs/manager.py` 与既有行共享文件），44 个原始 harness 文件全部归属、未登记清零；本候选新增 17 个 CLAUDE.md 文档，预算据此从 44（43 代码 + 1 文档）修订为 61（43 代码 + 18 文档），代码预算仍为 43（见"2026-10-01 全量对账"）。 |
| 2026-10-01 | v2.1.0 收敛票 10（合并后复评） | 对照 `git diff v2.1.0 --name-only -- backend/packages/harness/deerflow` 实测 44 个差异文件全部映射到 PATCH 行、未映射 0（PATCH-030 的 `skills/storage/user_scoped_skill_storage.py` 因被上游 v2.1.0 等价实现吸收而退出差异集；票 06 的 `versions/20261001_rejoin_upstream_line.py` 新进入差异集，归 PATCH-015）。逐行复评 PATCH-001..032：31 行 keep、PATCH-006 维持 closed、1 项 absorbed（P030 的 user_scoped 条款，其余 5 条款仍为本地差异，行保持 open）。另在 canonical 对照命令路径之外发现 `backend/packages/harness/pyproject.toml` 携带未登记本地差异（`python-docx>=1.1.2`，引入提交 `7ae6b5907`，与 PATCH-032 同提交），不在本轮登记范围，移交后续票补登记或明确豁免。 |
| 2026-10-05 | D6 裁决票（v2.1.0 有效锁定 SHA 登记） | owner 裁决并经代码核对确认：v2.1.0 合并后的有效上游锁定点为 `v2.1.0` 标签所指提交 `345f08be00c8a9495079b732a39b46aa9af1584e`，头部对照命令已随之更新。依据：① 2026-10-01 合并后复评即以 `git diff v2.1.0` 为 canonical 对照命令，44 个差异文件全部映射到 PATCH 行；② 合并提交 `85075252a` 的上游侧父提交为本地集成线（`51dbcc14`，其上含 tag 之后 2416 个本地提交），tag 是唯一稳定的上游锚点，中间集成头属本地历史；③ 本轮复核 scoped 差异 65 个文件，与修订预算 61（43 代码 + 18 文档）及后续候选的持续登记口径相容。`backend/packages/harness/pyproject.toml`（python-docx）仍为既有行标注的待登记项。 |
| 2026-10-11 | PR-only CI 门禁修复（结构化注册表落地） | 按 `scripts/check_upstream_patches.py` 的结构化注册表要求完成首次登记：注册表 pin 2026-10-05 裁决的有效上游锁定点 `345f08be0`（v2.1.0），CI `test-lane-shadow` 的 `--upstream-baseline` 同步由 `0f7d8709` 更新为 `345f08be0`（旧 pin 会把上游自身演进计为"未登记差异"，产生虚假治理记录）。实测对照 `345f08be0` 差异 66 文件（45 代码 + 21 文档），全部归属：PATCH-001..032 按登记表映射（PATCH-030 的 `user_scoped_skill_storage.py` 已被上游吸收，注册表仅列其余 5 文件），新增 PATCH-033（`extensions/ordering.py`，引入提交 `fea7dc178`）、PATCH-034（`tools/builtins/update_agent_tool.py`，引入提交 `a959b99be`）、PATCH-035（20 个 harness `CLAUDE.md` 指导文档镜像，10-01 巡检行计入预算但未设登记行，本行补齐归属）。预算据此从 61（43 代码 + 18 文档）修订为 66（45 代码 + 21 文档）：代码 +2 为 PATCH-033/034 新登记文件（65→66 的增量即 10-05 之后的 `fea7dc178`），文档 +3 为镜像计数自 10-01 合并后的实际增量（17→20，合并自身带入）。 |
| 2026-10-11 | 批次1治理票 49（04-M7 台账补登记） | 登记对照命令前缀之外的 harness 差异：`backend/packages/harness/pyproject.toml`（2026-10-01 巡检行移交的待登记项，`python-docx` 条款）补登记为 PATCH-036（合并 develop 时因 fault-zeroing 登记 issue #22 撞号，重编为 PATCH-037，内容不变），覆盖该文件全部本地差异（`python-docx>=1.1.2`，引入提交 `7ae6b5907`；`pymupdf4llm>=0.0.17,<2`，引入提交 `44498da80`）。该文件在对照命令 `-- backend/packages/harness/deerflow` 前缀之外，与结构化注册表 `paths` 同 scope，不进注册表、不占 66 文件预算；`python3 scripts/check_upstream_patches.py --base HEAD --upstream-baseline 345f08be0` 复测 pass。同票核对 04-M7 指认的内置工具消息文案一行变更归属：即 `update_agent_tool.py` 迁移脚本路径文案修正，2026-10-11 结构化注册表落地行已登记为 PATCH-034（原因/修改/测试/Owner/移除条件齐全，注册表携 current 验证证据），无重复登记。 |
| 2026-10-11 | 批次4整改票 59（07-H1 上游 PR 候选登记） | 本地修复 `frontend/src/app/api/memory/[...path]/route.ts` catch-all 代理的路径穿越（07-H1：Next 动态段解码后拼回 pathname，`new URL` 归一化 `..`/`%2e%2e` 使 `/api/memory` 前缀失效，`GET /api/memory/..%2F..%2Fv1%2Fadmin` 可达网关任意路径）。上游 `v2.1.0`（`345f08be0`）内同名文件同病（仅 `BACKEND_BASE_URL` 环境变量回退链不同），整理为上游 PR 候选与 P003/P011/P014/P032 并列进下轮收敛 reassess：目标仓库 `bytedance/deer-flow`，diff 草稿与 PR 正文见 `docs/upgrades/upstream-pr-candidates/memory-proxy-path-traversal.md`（段白名单 + 重编码拼接 + 构造后 `pathname.startsWith("/api/memory/")` 断言，拒绝返回 404）。该文件属前端面（非 `backend/packages/harness/` 差异），不进结构化注册表、不占 66 文件预算；本地验证：`tests/unit/app/api/memory/[...path]/route.test.ts` 新增 6 条穿越用例先红（6/6 失败）后绿，`tests/unit/app/api/memory/route.test.ts` 与登录面共享 `next-path` 校验收敛用例全绿。 |
| 2026-10-11 | 批次4整改票 61（03 渠道族上游 PR 候选登记） | 本地修复渠道生命周期与循环亲和五件（03-H1/H2/M3/M4/M6+M5）：Telegram/DingTalk 轮询线程死亡后清 `_running` 并覆写 `is_running` 检查线程存活（与既有 Feishu/Discord 覆写对齐）；飞书 stop() 断开 lark WS（`_disconnect` 有界提交 + 停 SDK 循环阻断无限自动重连）并置 `_stopped` 屏蔽旧实例事件；Slack connect Future 保存 + done callback 清 `_running`；Discord 身份附加并入 `_publish_reserved` 以 attach+commit 协程提交网关主循环（对齐 Slack `_publish_inbound_with_connection`）、`/connect` 绑定比照 Telegram 提交主循环；manager 默认 inbound 文件 reader 收敛为白名单式（无注册 reader 的渠道丢弃 URL 附件并告警）。上游 `v2.1.0`（`345f08be0`）内 `slack.py:145`/`feishu.py stop`/`telegram.py`/`dingtalk.py`/`discord.py:578`/`manager.py:1107` 同病，整理为上游 PR 候选进下轮收敛 reassess：目标仓库 `bytedance/deer-flow`，三模式 diff 草稿与验证证据见 `docs/upgrades/upstream-pr-candidates/channel-lifecycle-loop-affinity.md`。适配器与 manager 属 `backend/app/` 控制面（非 harness 差异），不进结构化注册表、不占 66 文件预算；本地验证：`tests/unit/channels/test_channel_lifecycle_contracts.py` 新增 10 条合同测试先红（8/8 目标用例失败）后绿，`backend/tests/unit/channels/` 1480 passed 全绿，邻接面（root tests/test_channels.py 等 6 文件）全绿。 |
| 2026-10-13 | 批次5整改票 63（04-M5 registry 重复注册语义 + 上游 PR 候选登记） | 补登记 PATCH-038：`extensions/registry.py` 的 `runtime_evidence()` 由无条件 append（重复注册静默 `[-1][1]` 取最后一个、前者被覆盖且无诊断，04-M5）改为单 provider 拒绝重复——桶内已有注册即抛 `ValueError` 并命名既有/被拒 source，经 loader 既有失败路径变为回滚 + error diagnostic + `required` 启动中止；`extensions/__init__.py` 的 `resolve_runtime_evidence_hooks` 行为不变，docstring 由 "the latest" 收敛为单 provider 语义。两文件与 PATCH-024 注册行共享，按 PATCH-004/023 共享文件先例在结构化注册表并列登记（重叠 ownership，不新增差异文件、不占 66 文件预算），PATCH-024 的 current_verification 同步复验刷新（35 passed）。上游比对结论与票面预判相反：`git show deerflow/main`（`81fa17c15ab`）与 `345f08be0`（v2.1.0）内 `extensions/__init__.py`/`registry.py` 均无 `resolve_runtime_evidence_hooks`/`runtime_evidence`——runtime evidence 注册缝为 fork 本地新增（`ef2ed33dd`，PATCH-024 面），上游今日无同病可提；上游 PR 候选按"候选登记+diff 草稿"收口（与 #59/#61 同口径，实际提交由用户决定），语义为：若该注册缝随 PATCH-005 移除条件（runtime 暴露 receipt/evidence contribution callbacks）等路径上提上游，单 provider 确定性语义须随提案原生携带，草稿见 `docs/upgrades/upstream-pr-candidates/registry-duplicate-evidence-hooks.md`，并列进下轮收敛 reassess。本地验证：新增 4 条合同测试（registry 跨源/同源拒绝、loader 双 spec 显式失败/required 中止）先红（4 failed）后绿，三文件合计 75 passed；治理门 `check_upstream_patches.py --base f0a33e741 --upstream-baseline 345f08be0` pass。 |
| 2026-10-13 | 批次5整改票 64（02-M6 企业定制接缝 expand：monkeypatch→registry 契约，过渡态） | 登记三处新上游接缝面（PATCH-039/040/041）：`tools/tools.py` 的 `get_available_tools` 尾端 consult `resolve_tool_scopes`（工具装配 tool-scope 缝，新差异文件，预算 66→67、代码 45→46）；`subagents/executor.py` `_create_agent` consult `resolve_subagent_middlewares`（子代理组装中间件缝，与 PATCH-028 共享文件）；`agents/lead_agent/agent.py` `_assemble_lead_agent` consult `resolve_builtin_tool_overrides`（builtin 工具覆盖缝，与 PATCH-010 共享文件）。配套注册面在 `extensions/registry.py`/`extensions/__init__.py` 增三桶（`tool_scopes`/`subagent_middlewares`/`builtin_tools`，全部单 provider：重复注册注册期 `ValueError`，语义与 #63 PATCH-038 一致）+ 进程默认 setter（解析链 extensions 参数→进程 loaded 集→进程默认，对照 `resolve_runtime_evidence_hooks` 先例）。**过渡态（expand）**：三处原导入期 monkeypatch（`executor_bridge` 两处 `_install_scope_aware_*`、`agent_bootstrap.install()` 属性改写）保留且默认仍生效；新轨经 env 开关启用（`IDEER_TOOL_SCOPE_SEAM`/`IDEER_SUBAGENT_MIDDLEWARE_SEAM`/`IDEER_BUILTIN_TOOL_SEAM` = `registry`），注册方为 workflows v2 executor_bridge（前两缝，归属：ContextVar 与 FilesystemScopeMiddleware 均在 app 层，agentplatform_extension 不可 import app）与 agent_bootstrap（第三缝，归属：canonical 工具本体所在）；合同测试（`tests/unit/workflows/test_v2_executor_bridge_seam_contract.py`、`tests/unit/agentplatform/test_agent_bootstrap_seam.py`、registry/loader/boundary 增量）证明两轨可独立启用且行为等价（含 #55 先例子进程探针：registry 轨断言上游绑定零改写，legacy 轨探针锁定旧改写仍在）。**移除条件（contract 各批落地后）**：monkeypatch 移除、开关删除后，三缝的移除条件=上游 harness 提供等价扩展点并被采纳（详见各行）；上游均无对应缝（`deerflow/main`/`v2.1.0` 比对），候选文档 `docs/upgrades/upstream-pr-candidates/host-seam-extension-points.md` 并列下轮收敛 reassess。 |

### 2026-09-08 巡检逐项结论（2026-10-01 自历史档案迁入，内容保持原文）

| ID | Conclusion | Reassess |
|---|---|---|
| PATCH-002 | keep — the extension (`EvidenceLifecycleContributor`) owns the envelope only in binding/authorization configurations; the harness stamp is the runtime guarantee of a bare envelope for non-participating extensions, pinned by `tests/test_extension_task_lifecycle.py::test_start_and_stop_reach_contributors_in_order`. Removal requires upstream (not the extension) to own bare-envelope seeding | next upstream sync |
| PATCH-003 | keep — doc-only alignment of `config/AGENTS.md` with the upstream `memory_config.py` schema (files otherwise identical); the guidance stays where profile authors read it. Candidate to upstream verbatim, then revert the local line | next upstream sync |
| PATCH-004 | keep (schema clause) — compatibility-import clause verified satisfied (see row); the schema itself remains until upstream provides equivalent durable-workflow limits | next upstream sync |
| PATCH-005 | keep — the extension API ships `MiddlewareContributor`, but the runtime-owned receipt key and the sub-agent citation verdict are not exposed through it, so the receipt→evidence bridge cannot move behind the extension boundary yet | next upstream sync |
| PATCH-007 | keep — no upstream Code Evidence contract exists | next upstream sync |
| PATCH-008 | keep — no upstream scanner contract matching the fixed command/finding shape | next upstream sync |
| PATCH-009 | keep — removal condition (upstream/extension persistence contract for Workflow V2 tables and Run Evidence) still unmet; full DB execution verified 2026-09-08 (see row) | upstream contract, or the Workflow ExecutionTarget milestone (M10) |
| PATCH-010 | keep — upstream offers post-assembly observers only; no pre-assembly frozen-input seam | next upstream sync |
| PATCH-011 | keep — upstream SQLite connect hook assumes a sync driver | next upstream sync |
| PATCH-012 | keep — upstream projection config cannot express run-scoped frozen skill closures | next upstream sync |
| PATCH-013 | keep — upstream admission mints its own run id unconditionally | next upstream sync |
| PATCH-014 | keep — guards are permanent no-ops on fresh databases; removal is hygiene only | once no deployed database predates `20260908_unify_migration_chains` (M0 rollout complete) |
| PATCH-015 | keep — registration of the ticket-01 unified-entry machinery the inspection found unlisted; the machinery itself is verified and load-bearing for every deployed pre-merge database | next upstream sync |

### 2026-10-01 全量对账（票 01）

`git diff 0f7d8709d3bbf0be26460b6277fbad9329302243 --name-only -- backend/packages/harness/deerflow`
实测 44 个文件（36 修改 + 8 新增），逐个归属如下（路径省略
`backend/packages/harness/deerflow/` 前缀；带 `*` 的文件承载两个登记项的改动）：

| 登记项 | 文件（44） |
| --- | --- |
| PATCH-001 | `community/ragflow/client.py` |
| PATCH-002 | `extensions/notify.py` |
| PATCH-003 | `config/AGENTS.md` |
| PATCH-004 | `config/workflow_runtime_config.py`、`config/app_config.py*` |
| PATCH-005 | `agents/middlewares/tool_receipt_middleware.py`、`tools/builtins/task_tool.py` |
| PATCH-006 | `persistence/bootstrap.py`（含 legacy 表 `create_all` 块，与 PATCH-031 配套）、`persistence/migrations/env.py` |
| PATCH-007 | `uploads/code_evidence.py` |
| PATCH-008 | `uploads/code_analysis.py` |
| PATCH-009 | `persistence/models/workflow_v2.py` |
| PATCH-010 | `agents/lead_agent/agent.py`、`agents/lead_agent/prompt.py` |
| PATCH-011 | `persistence/engine.py` |
| PATCH-012 | `sandbox/local/local_sandbox_provider.py` |
| PATCH-013 | `runtime/runs/manager.py*` |
| PATCH-014 | `persistence/migrations/versions/0001_baseline.py` |
| PATCH-015 | `persistence/migrations/_chain_meta.py`、`persistence/migrations/alembic.ini`、`persistence/migrations/versions/20260908_unify_migration_chains.py` |
| PATCH-016 | `sandbox/local/local_sandbox.py` |
| PATCH-017 | `sandbox/tools.py` |
| PATCH-018 | `sandbox/encoding.py` |
| PATCH-019 | `sandbox/search.py` |
| PATCH-020 | `agents/middlewares/tool_error_handling_middleware.py` |
| PATCH-021 | `community/aio_sandbox/aio_sandbox_provider.py` |
| PATCH-022 | `community/ragflow/tools.py` |
| PATCH-023 | `config/app_config.py*`（`KnowledgeConfig`；其余差异属 PATCH-004） |
| PATCH-024 | `extensions/__init__.py`、`extensions/registry.py` |
| PATCH-025 | `models/openai_codex_provider.py` |
| PATCH-026 | `runtime/journal.py` |
| PATCH-027 | `runtime/runs/worker.py`、`runtime/runs/manager.py*`（`persist_current_record`；其余差异属 PATCH-013） |
| PATCH-028 | `subagents/executor.py` |
| PATCH-029 | `subagents/registry.py` |
| PATCH-030 | `agents/middlewares/input_sanitization_middleware.py`、`client.py`、`extensions/gateway.py`、`skills/frontmatter.py`、`skills/projection.py`、`skills/storage/user_scoped_skill_storage.py` |
| PATCH-031 | `persistence/models/legacy_tables.py`、`persistence/models/__init__.py` |
| PATCH-032 | `utils/readability.py` |

## 登记项

### PATCH-001: RAGFlow 管理端 client 兼容 v0.27+ 批量文档端点

- **文件**: `backend/packages/harness/deerflow/community/ragflow/client.py`
- **修改**: `parse_document` 改用批量解析端点
  `POST /datasets/{id}/documents/parse`（body `{"document_ids": [...]}`）；
  `get_document_status` 改经列表端点解析单文档状态（单文档 GET 返回非 JSON）；
  `delete_document` 改为 JSON body `{"ids": [...]}`（旧 query 参数形式被拒绝）；
  新增 `create_dataset`、`list_dataset_documents`（M4 发布/对账所需）。
- **原因**: 真实 RAGFlow v0.27.1 隔离栈验收（M4 票 06）发现单文档 parse 404、
  单文档 GET 非 JSON、DELETE query 形式被拒——既有单元测试的假 client 无法暴露。
- **测试**: `tests/test_ragflow_client.py`（批量 parse、列表化状态、JSON body 删除、
  create/list 端点、分页与响应形）；真实 provider 验收脚本全链路通过（dev-log）。
- **Owner**: knowledge 域维护者
- **移除条件**: 上游 RAGFlow 社区 client 提供等价能力（批量 parse/状态/删除/建库）
  并被本仓库采纳时，可整体移除。

### PATCH-002..015（2026-10-01 自 docs/upgrades/deerflow-main-0f7d8709/UPSTREAM_PATCH_LEDGER.md 整体迁入，行内容保持原文）

| ID | Path / symbol | Reason local behavior is required | Upstream alternative considered | Removal trigger | Verification | Status |
|---|---|---|---|---|---|---|
| PATCH-002 | `deerflow/extensions/notify.py` (`notify_task_start/stop`) | Initialize and finalize the shared Run Evidence Envelope at the runtime task lifecycle boundary | Upstream task lifecycle hooks do not own AgentPlatform's cross-cutting evidence envelope | Remove when the AgentPlatform extension owns this lifecycle binding without a harness patch | `tests/test_extension_task_lifecycle.py`, extension API contract tests | runtime evidence maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream task lifecycle hooks still have no evidence-envelope ownership; local notify.py adds the `RunEvidenceEnvelope` stamping) |
| PATCH-003 | `deerflow/config/AGENTS.md` (memory schema guidance) | Document the merged host-shared/pluggable Memory schema and migration boundary | Upstream documentation does not describe AgentPlatform's legacy profile migration | Remove when equivalent guidance is supplied by the extension/config package | `tests/test_memory_manager_pluggable.py` | memory configuration maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `config/AGENTS.md` still documents the legacy flat memory schema line; no equivalent host-shared/pluggable guidance exists) |
| PATCH-004 | `deerflow/config/workflow_runtime_config.py`, `deerflow/config/app_config.py` (`WorkflowRuntimeConfig`) | Move durable workflow admission/lease limits into the DeerFlow-owned configuration schema while preserving AgentPlatform compatibility imports | No upstream workflow-v2 config model covers the AgentPlatform durable workflow limits | Remove compatibility import after all AgentPlatform callers use the DeerFlow symbol directly; retain schema until upstream provides equivalent limits | `tests/unit/workflows/test_v2_runtime_config.py` (3 passed), Ruff check/format | workflow runtime maintainers | open — compatibility-import clause verified satisfied 2026-09-08 (zero AgentPlatform-side compat imports remain; all consumers import the DeerFlow symbol directly), only the schema clause still blocks — reassessed 2026-10-01 vs v2.1.0: keep (upstream has no `workflow_runtime_config.py`/`WorkflowRuntimeConfig`; `subagent_runtime`/`run_ownership` cover different concerns) |
| PATCH-005 | `deerflow/agents/middlewares/tool_receipt_middleware.py` (`ToolReceiptMiddleware._stamp_message`), `deerflow/tools/builtins/task_tool.py` (`_record_run_evidence_verification`) | Forward runtime-owned tool receipts and sub-agent verification verdicts into the AgentPlatform Run Evidence Envelope when the optional extension is active | Upstream receipt middleware/task tool have no enterprise Run Evidence sink; message-carried receipts remain unchanged without the extension | Remove once the runtime exposes equivalent extension callbacks for receipt contribution | `tests/test_tool_receipt_middleware.py`, extension boundary tests (44 combined), receipt projection tests | runtime evidence maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `extensions/run_evidence.py` is a read-only projection reader with no receipt/evidence write seam) |
| PATCH-006 | `deerflow/persistence/bootstrap.py`, `deerflow/persistence/migrations/env.py` (`deerflow_alembic_version`) | Isolate DeerFlow migration state from AgentPlatform's control-plane Alembic head during dual runtime | A shared `alembic_version` table cannot represent two independent histories | Remove only after a verified single forward-only migration chain replaces both histories | `tests/unit/persistence/test_unified_chain_adoption.py` (8 passed), Ruff | persistence maintainers | **closed 2026-09-08** — chains unified by merge revision `20260908_unify_migration_chains` (single `alembic_version`, `alembic heads` single-head verified); dedicated table bridged and dropped via `_chain_meta.adopt_unified_version_state`; control-plane `alembic.ini`/`env.py` retired; fresh/existing/dual-recorded/control-plane-only/pre-alembic DB shapes verified — reassessed 2026-10-01 vs v2.1.0: closed unchanged (residual `bootstrap.py`/`env.py` diffs are the P015/P031 unified-chain machinery, not a revival of the dedicated-table bridge) |
| PATCH-007 | `deerflow/uploads/code_evidence.py` (`package_root`) | Expose only the caller-scoped frozen package path to runtime tools after Code Evidence acceptance moved to AgentPlatform | No upstream Code Evidence contract exists; runtime tools need a neutral path projection | Remove when the runtime provides an equivalent package-root capability through the extension API | `tests/unit/gateway/test_code_evidence_package.py` (13 passed), Ruff | code evidence maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `uploads/` ships only `manager.py`; no Code Evidence contract exists) |
| PATCH-008 | `deerflow/uploads/code_analysis.py` (scanner inventory/normalization/report contract) | Keep deterministic, shell-free C analysis available to the DeerFlow built-in tool while removing the product implementation from `ideer` | No upstream scanner implementation provides AgentPlatform's fixed command and finding contract | Remove when the extension/runtime API supplies the same fixed scanner contract | `tests/unit/gateway/test_code_analysis.py` (5 passed), Ruff | code analysis maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `uploads/` has no scanner implementation matching the fixed contract) |
| PATCH-009 | `deerflow/persistence/models/workflow_v2.py` | Provide a DeerFlow-owned Workflow V2 model namespace for Gateway/runtime callers while keeping the enterprise table family out of standalone DeerFlow's generic model registry | Upstream runtime has no AgentPlatform Workflow V2 tables or Run Evidence fields | Remove only after Workflow V2 tables and Run Evidence are represented by an upstream/extension persistence contract | Gateway, Worker, Store, RunRecord and resource-governance service now import the DeerFlow namespace; six-table Alembic/ORM contract plus standalone/combined metadata checks passed; duplicate `ideer` Workflow mapping deleted; full DB execution verified on both backends (`tests/integration/workflows/test_v2_db_execution.py`: unified-chain `upgrade head` over an empty SQLite and PostgreSQL database and over a 20260715-shaped legacy database, driving the six-table family through Store/RunRepository and the Gateway canonical-run + Worker lease-takeover path) | workflow persistence maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `persistence/models/` has no Workflow V2 namespace, only `run_event.py`) |
| PATCH-010 | `deerflow/agents/lead_agent/agent.py` (`FrozenAgentInputs`, `assemble_lead_agent(frozen=...)`, `_intersect_tool_groups`, read-only update_agent withholding, skill tool-policy application), `deerflow/agents/lead_agent/prompt.py` (`soul_override`, `requested_skill_name`) | Canonical resource runs must assemble from the server-frozen UUID/version/hash closure instead of the mutable on-disk agent store, with caller tool-group intersection and read-only semantics; the per-Run frozen carrier cannot be expressed through the process-global agent store or client-injectable configurable keys | Upstream extension API offers assembly observers (post-assembly) but no pre-assembly input override; the agent store is process-global and cannot represent per-Run isolation | Remove when upstream exposes a pre-assembly frozen-input parameter or an equivalent extension seam | `tests/unit/agentplatform/test_frozen_agent_inputs.py` (5 passed, incl. the escaped `<soul>` block regression), `tests/unit/agentplatform/test_runtime_adapter.py` (2 passed), lead-agent model resolution + assembly descriptor + prompt suites (110 passed combined) | agent runtime maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `assemble_lead_agent(config, *, app_config)` still has no `frozen=` pre-assembly seam; upstream `prompt.py` has no `soul_override`/`requested_skill_name`) |
| PATCH-011 | `deerflow/persistence/engine.py` (`init_engine` SQLite connect hook) | Upstream executes synchronous `PRAGMA journal_mode=WAL/...` on the DB-API cursor inside SQLAlchemy's connect event; with aiosqlite that adapted connection cannot run sync cursor calls, so the hook is bridged through `dbapi_conn.run_async` to keep WAL/foreign-key/busy-timeout semantics on the async engine | Upstream connect hook assumes a sync driver; no extension point exists for driver-specific connect configuration | Remove when upstream's SQLite connect hook supports async drivers (or upstream adopts the same bridge) | Gateway/persistence suites on the SQLite backend (WAL asserted in integration persistence tests) | persistence maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `_enable_sqlite_wal` still drives the DB-API cursor synchronously with no `run_async` bridge) |
| PATCH-012 | `deerflow/sandbox/local/local_sandbox_provider.py` (`RUN_SKILL_VIEW_RESOLVER` hook, `_build_thread_path_mappings` forced-view branch) | Canonical runs key their sandbox on a run-scoped identity and must serve the run's frozen, hash-verified skill closure read-only at `/mnt/skills` — fail-closed when the view is missing — instead of the mutable per-thread projection; the run-snapshot concept does not exist upstream, and the hook keeps the dependency direction (the runtime never imports `app.agentplatform`) | Upstream projection config cannot express per-run frozen closures; the enterprise layer installs the resolver at startup (`app.agentplatform.resources.canonical_sandbox.install_run_skill_view_resolver`) | Remove when upstream exposes an equivalent pre-acquire mapping override or a run-snapshot projection contract | `tests/unit/resources/test_canonical_sandbox.py` (6 passed, incl. fail-closed case) | sandbox maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream sandbox projection has no run-snapshot concept and no resolver hook; applies to PATCH-021 equally) |
| PATCH-013 | `deerflow/runtime/runs/manager.py` (`create_or_reject(..., run_id=...)`, `_admit_thread_operation(..., run_id=...)`) | Canonical resource runs must admit the Run under the server-frozen run id: `prepare_run` freezes the dependency closure and run-skill view under `canonical_run_id` before `start_run` admits the record, so the Run row, `run_resource_snapshots`, and evidence binding must share one identity. Upstream's admission mints a fresh uuid unconditionally and offers no id override | No upstream extension seam or admission parameter carries a caller-supplied run id | Remove when upstream admission accepts a caller-supplied id (or an equivalent identity-binding hook) | `tests/test_run_repository.py`, `tests/test_run_manager.py` (129 passed); exercised end-to-end by `tests/integration/api/test_shared_resource_run_e2e.py` | runtime maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream `create_or_reject` still mints its run id unconditionally; local `run_id` parameter survives the merge) |
| PATCH-014 | `deerflow/persistence/migrations/versions/0001_baseline.py`, `app/agentplatform/persistence/migrations/versions/16147afec43b_add_departments_and_users_ext_tables.py`, `app/agentplatform/persistence/migrations/versions/c4d5e6f7a8b9_add_missing_core_tables.py`, `app/agentplatform/persistence/migrations/versions/f3a2b1c4d5e6_add_disabled_column_and_indexes.py` (inspector-guarded `create_table` / `add_column` / `create_index` blocks) | The unified migration chain (`20260908_unify_migration_chains`) can replay these revisions against databases where the tables already exist via `Base.metadata.create_all` (runtime-only Gateway DBs recorded at the runtime head) or via the other chain (control-plane-only DBs recorded at the control-plane head); `op.create_table` would crash with `table already exists`, and SQLite batch `add_column` on an already-present column builds a contradictory column-order dependency (`CircularDependencyError`) | Restamping such databases below the affected revisions is impossible (single version row) and replaying history is forbidden; guarding mirrors `create_all`'s `checkfirst` semantics | Remove when no deployed database predates `20260908_unify_migration_chains` (the guards are permanent no-ops for fresh databases, so removal is hygiene, not correctness) | `tests/unit/persistence/test_unified_chain_adoption.py`, `tests/integration/persistence/test_migration_schema.py` (unified-chain suites incl. the create_all-current stamp and pre-alembic enterprise pins), fresh/existing/dual-recorded/control-plane-only/pre-alembic SQLite upgrade matrix, Ruff | persistence migration maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (guards remain permanent no-ops on fresh databases; deployed pre-unification databases still exist) |
| PATCH-015 | `deerflow/persistence/migrations/_chain_meta.py`, `deerflow/persistence/migrations/alembic.ini`, `deerflow/persistence/migrations/versions/20260908_unify_migration_chains.py` (unified-chain entry machinery, registered 2026-09-08 after being found unlisted by the ledger inspection) | One forward-only chain must serve both historical migration trees: the merge revision joins them under a single `alembic_version`; `_chain_meta` is the chain-identity single source and the adoption state machine that restamps legacy databases (dedicated-table, hybrid, create_all-current, pre-alembic shapes); the ini plus `version_locations` pair exposes both version directories to every `command.upgrade`. 2026-10-01 (deer-flow v2.1.0 sync, ticket 06): the second chain divergence — upstream extended the runtime line linearly past the branch point `0018` to `0025_repair_run_change_seq` — is re-joined by the no-op merge revision `versions/20261001_rejoin_upstream_line.py` with `down_revision = ("20260918_knowledge_publish_eval_gate", "0025_repair_run_change_seq")`; `alembic heads` verified single-head (`20261001_rejoin_upstream_line`), no existing database restamped (forward-only discipline) | Upstream keeps two independent trees with no merge revision and no adoption machinery | Remove only when upstream represents both historical chains natively or no deployed database needs the adoption restamp paths; the merge revision itself is permanent chain history | `tests/unit/persistence/test_unified_chain_adoption.py`, `tests/integration/persistence/test_migration_schema.py` (unified-chain suites), fresh/existing/dual-recorded/control-plane-only/pre-alembic SQLite upgrade matrix, dual-backend `tests/integration/workflows/test_v2_db_execution.py` | persistence migration maintainers | open — reassessed 2026-10-01 vs v2.1.0: keep (upstream version line stays linear through `0025_repair_run_change_seq` with no adoption machinery; `20261001_rejoin_upstream_line` is permanent chain history) |

### PATCH-016: LocalSandbox.read_file 编码嗅探（GB18030）

- **文件**: `backend/packages/harness/deerflow/sandbox/local/local_sandbox.py`
- **修改**: `read_file` 改为整文件字节读取后经 `sniff_decode` 严格解码
  （UTF-8 → UTF-8 BOM → GB18030），返回携带嗅探标签的 `DecodedText`
  （标签只作元数据、绝不嵌入文本，str_replace 读改写往返不变）；行切片与 grep
  共用 universal-newline 行号契约；`grep` 结果透传 `match.encoding`。
- **原因**: fault-zeroing 工具链承诺 GBK 中文源码/日志可读
  （`resources/skills/fault-zeroing/SKILL.md` 与 code-evidence 上下文中间件）；
  此前非 UTF-8 文本要么解码失败、要么被 `errors="replace"` 静默替换成乱码。
  引入提交 `280298ad7`（feat(sandbox): sniff GB18030 encoding in read_file and grep）。
- **测试**: `backend/tests/unit/sandbox/test_encoding_sniffing.py`
  （`test_read_file_carries_gb18030_encoding_label`、`test_read_file_gbk_line_slice`、
  `test_read_file_sliced_read_keeps_line_numbers_aligned`、
  `test_read_file_preserves_trailing_newline_on_full_read` 等）；
  `backend/tests/test_local_sandbox_provider_mounts.py::test_read_file_line_range_reads_file_in_single_pass`。
- **Owner**: fault-zeroing 域维护者
- **移除条件**: 上游 sandbox 读取路径提供等价编码嗅探（UTF-8→GB18030 严格序）
  并被本仓库采纳时。注意：与上游 v2.1.0 的 read_file 变更重叠，合并时须逐 hunk
  比对后再定去留。

### PATCH-017: read_file/grep 工具层渲染编码标记

- **文件**: `backend/packages/harness/deerflow/sandbox/tools.py`
- **修改**: `read_file` 工具输出在 GB 命中时前置 `[encoding: GB18030]` 标记行
  （`read_current_file_content` 同步处理，保证 ReadBeforeWriteMiddleware
  哈希的字节与读工具所见一致）；`_format_grep_results` 在每个 fallback 解码
  文件的行组前插入标记；二进制错误文案改为"supports UTF-8 and GB18030"。
- **原因**: 同 PATCH-016（同一提交 `280298ad7`）——工具层须向 agent 显式暴露
  非 UTF-8 命中，避免 agent 把 GB 文本当乱码或误改写。
- **测试**: `backend/tests/unit/sandbox/test_encoding_sniffing.py`
  （`test_read_file_tool_prepends_gb18030_marker_for_gbk_file`、
  `test_grep_tool_output_carries_gb18030_group_marker`、
  `test_str_replace_on_gb_file_never_persists_the_marker_line`、
  `test_read_file_tool_illegal_bytes_report_binary_file_error` 等）。
- **Owner**: fault-zeroing 域维护者
- **移除条件**: 上游 read_file/grep 工具层渲染等价编码标记并被采纳时；
  与上游 v2.1.0 变更重叠，合并时逐 hunk 比对。

### PATCH-018: sandbox 编码嗅探共享模块（新增）

- **文件**: `backend/packages/harness/deerflow/sandbox/encoding.py`
- **修改**: 新模块：`sniff_decode`（严格嗅探序 + NUL 字节守卫，拒绝二进制
  落入 GB18030 伪解码）、`DecodedText`（携带标签的 str 子类）、
  `encoding_label_of`、`universal_newlines(_lines)`、`with_encoding_prefix`。
- **原因**: read_file 与 grep 共享同一解码契约与行号契约（`280298ad7`）。
- **测试**: `backend/tests/unit/sandbox/test_encoding_sniffing.py`
  （`test_sniff_decode_pure_ascii_is_utf8_without_label`、
  `test_sniff_decode_gbk_hits_gb18030_fallback`、
  `test_sniff_decode_binary_with_nul_keeps_explicit_error`、
  `test_with_encoding_prefix_adds_marker_line_only_for_gb_hits`、
  `test_encoding_label_of_plain_str_is_none` 等）。
- **Owner**: fault-zeroing 域维护者
- **移除条件**: 上游 sandbox 提供等价 sniff/带标签解码能力并被采纳时。

### PATCH-019: grep 严格解码与编码标注

- **文件**: `backend/packages/harness/deerflow/sandbox/search.py`
- **修改**: `find_grep_matches` 弃用 `errors="replace"`，改为整文件
  `sniff_decode` 严格解码；无法解码的文件按二进制跳过；`GrepMatch` 新增
  `encoding` 字段；行号与 read_file 共用 `universal_newline_lines` 契约。
- **原因**: 同 PATCH-016/018（`280298ad7`）——旧路径对 GB 文本产生静默乱码
  匹配，对混合内容行号与 read_file 切片不对齐。
- **测试**: `backend/tests/unit/sandbox/test_encoding_sniffing.py`
  （`test_find_grep_matches_decodes_gbk_file_and_labels_matches`、
  `test_find_grep_matches_skips_undecodable_file_without_crashing`、
  `test_find_grep_matches_single_file_root_with_illegal_bytes_yields_no_matches`、
  `test_grep_match_encoding_defaults_to_none_for_other_providers` 等）。
- **Owner**: fault-zeroing 域维护者
- **移除条件**: 上游 grep 提供等价严格解码与编码标记并被采纳时。

### PATCH-020: workflow 子代理终止型中间件子集

- **文件**: `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`
- **修改**: 新增 `_WORKFLOW_SUBAGENT_RUNTIME` ContextVar
  （`workflow_subagent_runtime` / `reset_workflow_subagent_runtime`）与
  `_filter_workflow_subagent_middlewares`：workflow 子代理组装图时只保留
  input 消毒、工具错误/回执/LLM 错误、ThreadData、Sandbox、SafetyFinish、
  日期上下文等终止型中间件，其余（守卫、durable-context、扩展钩子等
  条件型 after-model 边）被滤除，由显式 max_turns/timeout 兜底。
- **原因**: LangGraph 条件工具路由在完整原生中间件图与 workflow
  ThreadData/Sandbox before-agent 钩子组合下无法终止 workflow 子代理
  （已完结节点会被路由回模型）。引入提交 `ca65c5770`
  （feat(knowledge): complete M4 revision publish and run freeze）。
- **测试**: `backend/tests/test_tool_error_handling_middleware.py::test_workflow_subagent_runtime_avoids_non_terminating_after_model_hooks`。
- **Owner**: workflow 域维护者
- **移除条件**: 上游/workflow 执行器提供终止型子代理中间件组装开关
  （或中间件图可组合终止）并被采纳时。

### PATCH-021: AIO sandbox 挂载 canonical Run 冻结技能视图

- **文件**: `backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py`
- **修改**: 引入与 PATCH-012 相同的 `RUN_SKILL_VIEW_RESOLVER` 中立钩子；
  `_build_thread_path_mappings` 命中 run 视图时强制只读挂载冻结视图，
  视图缺失即 fail-closed（`Canonical Run Skill view is missing`）。
- **原因**: AIO（容器池）沙箱与本地沙箱必须对 canonical Run 施加同一份
  冻结只读技能闭包；钩子保持依赖方向（harness 不 import `app.agentplatform`）。
  引入提交 `6a79bab11`（fix(sandbox): mount frozen skill aliases in aio runs）。
- **测试**: `backend/tests/test_aio_sandbox_provider.py::test_canonical_run_skill_view_mounts_frozen_root`、
  `::test_canonical_run_extra_mounts_do_not_overlay_frozen_skill_root`；
  resolver 安装侧 `backend/tests/unit/resources/test_canonical_sandbox.py`
  （含 fail-closed 用例）。
- **Owner**: canonical-run 域维护者（与 PATCH-012 同域）
- **移除条件**: 与 PATCH-012 相同——上游暴露 pre-acquire 映射覆盖或
  run-snapshot 投影契约并被采纳时，两行同步移除。

### PATCH-022: RAGFlow 检索工具遥测/端点脱敏/文档级检索范围

- **文件**: `backend/packages/harness/deerflow/community/ragflow/tools.py`
- **修改**: `_record_retrieval_metric` 低基数检索遥测
  （operation/result/latency_ms/error_category，不含查询与身份数据）；
  连接错误分支不再向模型回显内部 `base_url`（§51：端点只进 admin 侧告警日志，
  模型只见脱敏错误码与异常类名）；`_retrieve_dataset_groups` 新增
  `document_ids_by_dataset` 文档级检索范围（修订发布按冻结文档集合检索）。
- **原因**: 引入提交 `5d35c6d77`/`094f4d7f0`（knowledge 生命周期与授权检索）、
  `67c991c90`（Gate 1 脱敏验收发现连接错误分支向模型泄露内部 base_url）。
- **测试**: `backend/tests/test_ragflow_tools.py::test_connection_error_does_not_leak_internal_base_url`、
  `::test_connection_error_is_english_and_does_not_leak_key`；文档级范围经
  扩展包 `knowledge/runtime_adapter.py` 传入，由
  `backend/tests/unit/knowledge/test_knowledge_revisions.py`（修订文档集合）
  覆盖；`knowledge_metric` 遥测断言待补。
- **Owner**: knowledge 域维护者
- **移除条件**: 上游检索工具提供等价遥测/脱敏/文档级范围能力并被采纳时。

### PATCH-023: AppConfig 新增 KnowledgeConfig

- **文件**: `backend/packages/harness/deerflow/config/app_config.py`
  （仅 `KnowledgeConfig` 段；该文件其余本地差异属 PATCH-004）
- **修改**: 新增 `KnowledgeConfig`（`publish_eval_required`、
  `reconciliation_interval_seconds`）并挂到 `AppConfig.knowledge`。
- **原因**: M4 修订发布/对账需要 harness 侧配置 schema（引入提交 `ca65c5770`）。
- **测试**: 待补（schema 本身无专测；修订发布/对账行为由
  `backend/tests/unit/knowledge/` 系列覆盖）。
- **Owner**: knowledge 域维护者
- **移除条件**: 上游 app config 提供等价 knowledge 配置 schema，或该配置
  迁回控制面并被采纳时。

### PATCH-024: extension 注册面扩展（ToolContributor / RuntimeEvidenceHooks）

- **文件**: `backend/packages/harness/deerflow/extensions/__init__.py`、
  `backend/packages/harness/deerflow/extensions/registry.py`
- **修改**: `LoadedExtensions`/`ExtensionRegistry` 新增 `tool_contributors` 与
  `runtime_evidence_hooks` 桶（含 mark/rollback/install 位置快照与
  `resolve_runtime_evidence_hooks` 解析入口）。
- **原因**: 扩展 API 需要在不 patch harness 的前提下贡献运行时证据钩子与
  工具；引入提交 `3bc6aa7a8`（m6 retrieval/eval）、`f3cd1793d`（M8 设备执行环）。
- **测试**: 端到端由 `backend/tests/test_run_worker_delivery.py::test_retrieval_evidence_is_persisted_with_terminal_run`
  与 `backend/tests/unit/knowledge/test_retrieval_receipts.py`（经扩展包
  runtime_evidence 注册驱动）覆盖；注册桶本身的单元测试待补。
- **Owner**: evidence/extension 边界域维护者
- **移除条件**: 上游 extension API 原生提供等价 ToolContributor/
  RuntimeEvidenceHooks 注册面并被采纳时。

### PATCH-025: Codex provider 错误详情安全渲染

- **文件**: `backend/packages/harness/deerflow/models/openai_codex_provider.py`
- **修改**: 新增 `_safe_error_detail`：流式错误响应先 drain 再解析（规避
  `ResponseNotRead`）、字典键白名单（detail/error/message/code/type）、
  截断 500 字符并去换行；`HTTPStatusError` 分支记录 status/request-id/detail
  告警日志。其余差异为 import/格式重排。
- **原因**: 引入提交 `c8534ea0b`（fix(workflows): preserve state across
  parallel control nodes）与 `7d6c44e8f`（M9 runtime/Windows lane）；
  此前 rate-limit/provider 错误无 actionable 诊断且可能泄露凭据。
- **测试**: `backend/tests/test_codex_provider.py::test_safe_error_detail_is_bounded_and_selective`、
  `::test_safe_error_detail_reads_streaming_error_responses`。
- **Owner**: models 域维护者
- **移除条件**: 上游 Codex provider 提供等价有界错误详情与拒绝日志并被采纳时。

### PATCH-026: RunJournal 首 token 计时（TTFT）

- **文件**: `backend/packages/harness/deerflow/runtime/journal.py`
- **修改**: `on_llm_new_token` 记录首个非空流式 token 的 `llm_ttft_ms` 日志
  （trace_id/caller/thread_id 维度，不缓存 token 块）；journal 挂
  `ensure_trace_id`；其余大段差异为纯格式重排。
- **原因**: 引入提交 `e4bcfa718`（feat(ttft): add multi-attachment timing
  diagnostics）。
- **测试**: `backend/tests/test_run_journal.py::test_on_llm_new_token_logs_only_first_non_empty_token`
  （gateway 侧另有 `backend/tests/unit/gateway/test_first_token_timing.py`）。
- **Owner**: runtime 可观测域维护者
- **移除条件**: 上游 RunJournal 提供等价首 token 计时并被采纳时。

### PATCH-027: Run 完成时归档 run evidence

- **文件**: `backend/packages/harness/deerflow/runtime/runs/worker.py`；
  `backend/packages/harness/deerflow/runtime/runs/manager.py`
  （仅 `persist_current_record`；该文件其余本地差异属 PATCH-013）
- **修改**: worker 收尾时经 `resolve_runtime_evidence_hooks` 读取当前 run 的
  证据绑定，写入 `record.metadata["run_evidence"]`（`archive_status`=
  archived/failed，失败时经 `persist_current_record` 重写）；manager 新增
  `persist_current_record`（完整持久化内存 run 记录含 metadata）。
- **原因**: 引入提交 `79556489f`（feat(knowledge): add retrieval receipt
  evidence view）、`3bc6aa7a8`——检索引用必须先归档成功才对模型可见（fail-closed）。
- **测试**: `backend/tests/test_run_worker_delivery.py::test_retrieval_evidence_is_persisted_with_terminal_run`；
  `backend/tests/unit/knowledge/test_retrieval_receipts.py::test_retrieval_citation_is_delivered_only_after_archive_callback_succeeds`、
  `::test_archive_failure_does_not_deliver_a_verifiable_citation`。
- **Owner**: evidence 域维护者
- **移除条件**: 上游 run 生命周期暴露等价完成时证据归档回调
  （RuntimeEvidenceHooks 上游化）并被采纳时。

### PATCH-028: 委托检索谱系回执

- **文件**: `backend/packages/harness/deerflow/subagents/executor.py`
- **修改**: `SubagentResult` 新增 `retrieval_receipts` 字段及
  update/snapshot（带锁）；子代理收尾时从 evidence hooks 绑定的
  `binding.retrieval_receipts` 收割，保持父任务可见的委托检索谱系。
- **原因**: 引入提交 `3bc6aa7a8`、`4595e95e4`（fix(evidence): preserve
  delegated retrieval lineage）。
- **测试**: `backend/tests/unit/knowledge/test_retrieval_receipts.py::test_retrieval_receipt_from_child_task_is_visible_to_parent`。
- **Owner**: evidence 域维护者
- **移除条件**: 与 PATCH-027 相同（RuntimeEvidenceHooks 上游化）后随之移除。

### PATCH-029: managed 子代理解析保留全局 runtime 覆盖

- **文件**: `backend/packages/harness/deerflow/subagents/registry.py`
- **修改**: `_managed_definitions` 解析默认存储前快照 subagents 配置单例，
  解析后若被 AppConfig 的同步副作用改写则恢复，避免丢弃
  `load_subagents_config_from_dict()` 刚设置的 runtime 覆盖。
- **原因**: 引入提交 `5fcb8fe6a`（fix(subagents): preserve global runtime
  overrides）。
- **测试**: `backend/tests/test_managed_subagent_registry.py::test_config_yaml_overrides_remain_explicitly_higher_priority`
  （覆盖优先级守护；单例快照/恢复路径无专测，待补）。
- **Owner**: subagents 域维护者
- **移除条件**: 上游 managed subagent 解析不再以配置单例副作用覆盖调用方
  覆盖时。

### PATCH-030: lane/测试环境加固捆绑（3d078973f）

- **文件**: `backend/packages/harness/deerflow/agents/middlewares/input_sanitization_middleware.py`、
  `backend/packages/harness/deerflow/client.py`、
  `backend/packages/harness/deerflow/extensions/gateway.py`、
  `backend/packages/harness/deerflow/skills/frontmatter.py`、
  `backend/packages/harness/deerflow/skills/projection.py`、
  `backend/packages/harness/deerflow/skills/storage/user_scoped_skill_storage.py`
- **修改**: 输入消毒 denylist 增补 `requested_skill`（与 PATCH-010 的
  `requested_skill_name` 联动防注入）；`client.py` 流关闭改经
  `contextvars.copy_context().run(_close_stream_generator, ...)`，同步关闭被
  委托的 agent 迭代器，使其 `finally` 在绑定 trace id 的上下文内执行；
  gateway 路由把 `/api/webhooks/github` 加入 CSRF 豁免；skills frontmatter
  允许 `description_zh`/`requires-internet`（企业捆绑技能）；projection 重建
  重试 2→5（吸收并发技能写入的短暂签名漂移）；user-scoped 存储把临时文件
  写入挪入投影锁内（避免并发写者把 temp 文件暴露给签名扫描）。
- **原因**: 引入提交 `3d078973f`（test: unify lanes and harden test
  environment）——统一测试 lane 时暴露的运行时正确性/健壮性修复一并合入。
- **测试**: `backend/tests/test_input_sanitization_middleware.py::test_denylist_covers_framework_authority_blocks`
  （denylist 反漂移守护）；`backend/tests/test_client.py::test_abandoned_embedded_stream_releases_execution_lease`；
  `backend/tests/test_github_webhooks.py`、`backend/tests/test_gateway_request_path.py`
  （CSRF 豁免）；`backend/tests/unit/skills/test_skills_validation.py`
  （`description_zh` 白名单）、`backend/tests/unit/gateway/test_resources_api.py::test_skill_description_prefers_description_zh`；
  `backend/tests/unit/skills/test_local_skill_storage_write.py::test_write_is_atomic_overwrite`；
  projection 重试上限与锁内临时文件路径无专测，待补。
- **Owner**: 平台工程（lane 加固）域维护者
- **移除条件**: 逐项评估——各修复被上游等价实现并采纳后按文件移除，
  本捆绑行不整体移除。
- **Reassess 2026-10-01（vs v2.1.0，票 10）**: `skills/storage/user_scoped_skill_storage.py`
  条款 **retired / absorbed by upstream v2.1.0**——上游已带等价的投影锁内原子
  临时文件写入，合并取上游版，本地文件与上游逐字节一致（blob `e7a652039`），
  该文件退出 v2.1.0 差异集；其余 5 文件条款（input_sanitization `requested_skill`
  denylist、`client.py` `copy_context` 关闭桥、gateway `/api/webhooks/github`
  CSRF 豁免、frontmatter `description_zh`/`requires-internet`、projection 重试
  2→5）经逐项核对仍为本地差异（上游 projection 为 `_MAX_REBUILD_ATTEMPTS = 2`），
  行保持 open。

### PATCH-031: legacy 表 ORM 对齐 create_all

- **文件**: `backend/packages/harness/deerflow/persistence/models/legacy_tables.py`（新增）、
  `backend/packages/harness/deerflow/persistence/models/__init__.py`
- **修改**: 无活跃 ORM 实体的历史表 `workflow_runs`、`skill_applications` 以
  Core `sa.Table` 形式登记进 `Base.metadata` 并从 models 包导出，保证全新
  `Base.metadata.create_all` 数据库与统一 Alembic 链 base→head 升级产出同构
  （`persistence/bootstrap.py` 中同表的 create_all 块与 PATCH-006/015 行配套）。
- **原因**: 引入提交 `3d078973f`——统一链接管两棵历史迁移树后，create_all-only
  安装必须包含链内全部表，否则两套全新安装形态发散。
- **测试**: `backend/tests/integration/persistence/test_migration_schema.py`、
  `backend/tests/unit/persistence/test_migration_versions.py`、
  `backend/tests/integration/persistence/test_migrate_skill_applications.py`。
- **Owner**: persistence 域维护者
- **移除条件**: 与 PATCH-014/015 同前提——legacy 表由上游/扩展持久层契约
  承载，或不再有部署前置于 `20260908_unify_migration_chains` 的数据库时。

### PATCH-032: readability 纯 Python 回退容错

- **文件**: `backend/packages/harness/deerflow/utils/readability.py`
- **修改**: `simple_json_from_html_string(use_readability=False)` 失败
  （IndexError/TypeError/ValueError）时记告警并回退空文章，不再让整页抓取崩溃。
- **原因**: 引入提交 `7ae6b5907`（fix(testing): make backend and smoke lanes
  hermetic）——hermetic lane 中纯 Python readability 路径崩溃。
- **测试**: `backend/tests/test_readability.py::test_extract_article_falls_back_when_readability_js_fails`、
  `::test_extract_article_re_raises_unexpected_exception`。
- **Owner**: tools 域维护者
- **移除条件**: 上游 readability 封装提供等价回退并被采纳时。

### PATCH-033: extension 排序约束解析去缓存

- **文件**: `backend/packages/harness/deerflow/extensions/ordering.py`
- **修改**: 移除 `core_ordering_constraints()` 上的 `functools.cache`，改为每次
  调用即时解析，并在 docstring 补注缓存为何会固定首轮解析结果（真实类或测试桩）。
- **原因**: 引入提交 `fea7dc178`（fix(ci): harden gates against missing ripgrep,
  stub aliasing and venv yaml）——测试基建经 `sys.modules` 换装中间件桩，缓存的
  首轮解析会把桩类固定进排序断言，毒化同进程后续全部断言（含 pytest-xdist
  各 worker 内的后续用例）。
- **测试**: `backend/tests/test_extension_ordering.py`（排序断言全量）。
- **Owner**: 平台工程（lane 加固）域维护者
- **移除条件**: 上游为该解析提供等价的非缓存/可重置语义，或本仓库测试基建不再
  经 `sys.modules` 换装中间件桩时移除。

### PATCH-034: update_agent 遗留布局错误提示路径修正

- **文件**: `backend/packages/harness/deerflow/tools/builtins/update_agent_tool.py`
- **修改**: 遗留共享布局拦截文案中的迁移脚本路径 `scripts/migrate_user_isolation.py`
  改为 `backend/scripts/migrate_user_isolation.py`（与脚本实际位置一致），其余无差异。
- **原因**: 引入提交 `a959b99be`（fix(agents): point legacy agent errors at
  backend/scripts migration path）——按原提示路径执行会因找不到脚本而失败，误导用户。
- **测试**: `backend/tests/test_update_agent_tool.py::test_update_agent_rejects_legacy_agent_when_user_dir_has_only_memory`（断言该错误文案）。
- **Owner**: agents 域维护者
- **移除条件**: 上游修正同一提示路径（或迁移脚本位置变化使提示随之调整）时移除。

### PATCH-035: harness 指导文档 CLAUDE.md 镜像

- **文件**: `backend/packages/harness/deerflow/` 下 20 个 `CLAUDE.md`
  （根目录及 agents、agents/memory、agents/middlewares、community/tavily、config、
  extensions、mcp、models、persistence/migrations、persistence/user、reflection、
  runtime、sandbox、skills、subagents、tools、tracing、tui、utils；完整清单以
  注册表 PATCH-035 paths 为准）
- **修改**: 为 harness 各包 `AGENTS.md`（上游 v2.1.0 原生文件；除 `config/AGENTS.md`
  属 PATCH-003 的本地对齐外均与上游一致）新增内容一致的 `CLAUDE.md` UTF-8 镜像，
  由 `scripts/sync_agent_guidance.py` 生成与校验。
- **原因**: 仓库纪律（根 `AGENTS.md` 为唯一规则源，`CLAUDE.md` 为其 UTF-8 镜像）；
  2026-10-01 巡检行已将镜像计入文档预算但未设登记行，本行补齐归属。
- **测试**: `python3 scripts/sync_agent_guidance.py --check`（镜像一致性门禁，
  CI test-contracts 调用）。
- **Owner**: 平台工程（文档治理）域维护者
- **移除条件**: 上游原生提供 CLAUDE.md 镜像或仓库放弃镜像纪律时整体移除。

### PATCH-036: 归零代码包混合语言扫描与本地报告只读访问

- **状态**: open，GitHub issue #22，`fix/22-fault-zeroing-static-analysis`。
- **文件**: `backend/packages/harness/deerflow/uploads/code_analysis.py`、
  `backend/packages/harness/deerflow/sandbox/tools.py`。
- **原因与修改**: 混合 C/C++、Python 包必须运行两组固定扫描器；Cppcheck
  原生 XML 来自 stderr，不能把 stdout 进度当报告解析。本地文件工具补充
  当前线程 `code-evidence` 树的只读访问，使模型能读取源码和扫描报告。
  执行错误按扫描器的正常退出码区分，汇总为 `partial` 并落盘失败原因；
  Ruff/Bandit 的告警退出码 1 保持正常扫描状态。
- **替代方案**: 工具注册、授权与 Run 包选择保留在 app/extension；仅返回
  扫描摘要无法满足模型读取报告与源码的契约。复制报告到 workspace 会引入
  第二套路径和同步状态，因此复用既有线程映射与读取工具。
- **影响**: `read_file`、`ls`、`glob`、`grep` 可读取线程内代码证据；不扩大写入
  路径，真实路径校验拒绝逃出证据树的符号链接，Run 创建核验包归属并记录选择快照。
- **验证**: Cppcheck 输出流回归先失败后通过，相关分析测试 33 passed；本地
  证据报告读取回归先失败后通过，沙箱相关测试 184 passed，Ruff 通过。
  真实 Agnes 浏览器 Run 已成功扫描混合包并读取两个报告；最终 `pr-standard`
  和正式工作流验收尚待完成，不以本记录声明整个 issue 已关闭。
  本次续验补充四扫描器异常退出和模型可见失败提示回归，分析相关测试
  38 passed，Ruff 通过；完整标准门禁结果另记在本次验收记录。
- **Owner**: fault-zeroing 域维护者。
- **移除条件**: 上游或可注册的 provider 读取策略提供等价的线程代码证据只读
  契约，固定分析器提供等价混合语言与 Cppcheck 输出流处理，并被本仓库采纳。

### PATCH-037: harness pyproject 依赖清单本地声明（python-docx / pymupdf4llm）

- **文件**: `backend/packages/harness/pyproject.toml`（harness 包依赖清单，位于对照命令
  `backend/packages/harness/deerflow` 前缀之外；2026-10-01 巡检行移交的待登记项，由
  2026-10-11 票 49 行补登记。结构化注册表 `paths` 与对照命令同 scope，本文件不进
  注册表、不占 66 文件预算，仅以本小节登记并按"修改"逐行对照）
- **修改**: 依赖清单新增两行本地声明，其余无差异：
  `python-docx>=1.1.2`（字母序插入 `packaging` 与 `pydantic` 之间）；
  `pymupdf4llm>=0.0.17,<2`（含注释：file_conversion auto 模式缺该 import 时静默
  回退 MarkItDown，缺失会安静降级，故在清单显式固定，使离线镜像携带、测试走真实路径）。
- **原因**: `python-docx` 引入提交 `7ae6b5907`（fix(testing): make backend and smoke
  lanes hermetic）——hermetic lane 须稳定驱动 docx 解析路径（`file_conversion` 的
  docx 转换依赖它，缺失时降级），不能依赖 markitdown extras 的传递解析；
  `pymupdf4llm` 引入提交 `44498da80`（build(harness): ship pymupdf4llm for the
  pymupdf PDF conversion path，特性提交 `ddfc988be`）——离线镜像须携带首选
  PDF→Markdown 转换器，避免 auto 模式静默回退。
- **测试**: `backend/tests/unit/tools/test_docx_rich.py`（docx 解析路径依赖
  python-docx）；`backend/tests/unit/tools/test_file_conversion.py`、
  `backend/tests/unit/tools/test_file_conversion_edge_cases.py`（pymupdf4llm 转换
  与回退路径）；`uv sync --locked` 依赖解析一致性。
- **Owner**: 平台工程（依赖/打包）域维护者
- **移除条件**: 上游 harness 清单原生声明同等依赖并被本仓库采纳，或对应转换路径
  从 harness 移除时，按行移除（两行独立评估，不整体捆绑）。
- **编号说明**: 原登记为 PATCH-036（2026-10-11 票 49），与 develop 侧 fault-zeroing
  登记（issue #22）撞号，合并时让位重编为 PATCH-037；内容不变。

### PATCH-038: extension registry runtime evidence hooks 重复注册确定性拒绝

- **文件**: `backend/packages/harness/deerflow/extensions/registry.py`
  （`ExtensionRegistry.runtime_evidence`）、
  `backend/packages/harness/deerflow/extensions/__init__.py`
  （`resolve_runtime_evidence_hooks` docstring 单 provider 语义澄清）。两文件与
  PATCH-024 注册行共享，结构化注册表按 PATCH-004/023 共享文件先例并列登记
  （重叠 ownership，不新增差异文件、不占 66 文件预算）。
- **修改**: `runtime_evidence()` 由无条件 append 改为单 provider 拒绝重复：桶内
  已有注册时抛 `ValueError`，错误消息命名既有注册 source 与被拒 source；异常经
  install() 传播，由 loader 既有失败路径处置（位置回滚 + error diagnostic，
  `required: true` 时 `ExtensionLoadError` 启动中止）。`resolve_runtime_evidence_hooks`
  解析行为不变（注册面保证 loaded 集至多一个 provider，`[-1][1]` 即唯一项），
  仅 docstring 由 "the latest" 收敛为单 provider 语义。
- **原因**: 此前重复注册静默按 `extensions.runtime_evidence_hooks[-1][1]` 取最后
  一个，前者被覆盖且无诊断（发现 04-M5，票 #63）；registry 其它桶为叠加语义，但
  runtime evidence 的全部消费方（`task_tool`、subagents executor、run worker、
  tool_receipt middleware）把解析结果当单一 hooks 对象使用，静默覆盖即缺陷本体，
  该桶只能单 provider。拒绝放在注册缝而非解析缝：错误在扩展装载期归属到具体
  source，复用 loader 全部既有失败机制，零新增运行时路径。唯一在树内注册方
  `agentplatform_extension.install` 的两个 `runtime_evidence(...)` 调用分支互斥，
  单次 install 至多注册一次；全库无其它注册点，合法场景不受影响。
- **影响**: 无扩展或恰好一个 provider 时行为不变（PATCH-024 验证命令复验
  35 passed）；第二次注册（同源或异源）显式失败；无扩展时
  `resolve_runtime_evidence_hooks` 仍回退进程全局默认（`get_runtime_evidence_hooks`）。
- **测试**: `backend/tests/test_extension_registry.py`
  （跨源拒绝、同源二次拒绝、首个注册存活）、`backend/tests/test_extension_loader.py`
  （双 spec 挂载第二个显式失败并回滚、error diagnostic 指认、
  `resolve_runtime_evidence_hooks` 返回首个 provider、required 中止启动）、
  `extension_test_fixtures/demo_extensions.py`（`install_evidence_hooks` fixture）。
  先红（4 条新用例全失败）后绿；三测试文件合计 75 passed。
- **Owner**: runtime evidence maintainers
- **移除条件**: 上游 harness registry 提供 runtime evidence 注册缝并内建等价的
  重复注册确定性语义（或吸收本补丁）并被本仓库采纳后，随 PATCH-024 一体评估
  移除；上游 applicability 核对比结论见
  `docs/upgrades/upstream-pr-candidates/registry-duplicate-evidence-hooks.md`
  （上游 `deerflow/main` 与 v2.1.0 均无该注册缝，候选为条件性 rider）。

### PATCH-039: 工具装配 tool-scope 扩展缝（02-M6，票 #64）

- **文件**: `backend/packages/harness/deerflow/tools/tools.py`
  （`get_available_tools` 尾端 consult `resolve_tool_scopes`）——新差异文件
  （预算 66→67、代码 45→46，见结构化注册表修正案）；配套注册/解析面
  `backend/packages/harness/deerflow/extensions/registry.py`（`tool_scopes` 单
  provider 桶）与 `extensions/__init__.py`（`resolve_tool_scopes` + 进程默认
  setter）与 PATCH-024/038 行共享（共享文件先例，不另占预算）。
- **修改**: `get_available_tools` 完成去重后、返回前 consult
  `resolve_tool_scopes(None)`；provider 存在时以
  `apply_tool_scopes(tools, subagent_enabled=...)` 的返回值替换工具列表，
  无 provider 时原列表原样返回（零行为变化）。注册方（app 层，expand 过渡态）:
  `app/agentplatform/workflows/v2/executor_bridge.py` 在
  `IDEER_TOOL_SCOPE_SEAM=registry` 时经 `set_default_tool_scopes` 注册
  `WorkflowKnowledgeToolScopes`（行为与 legacy 模块包装一致：pending scope 为
  None 时直通；`subagent_enabled=False`（native 委托，含缺省值）fail-closed 为
  空 `KnowledgeScope`；其余按 pending scope 收窄 knowledge_search）。legacy 轨
  （`deerflow.tools.get_available_tools` 包级绑定包装）保留且默认生效。
- **原因**: 企业 knowledge-scope 工具收窄此前靠导入期改写上游模块属性
  （02-M6 发现 1），双轨制要求改动集中在分界面：上游工具装配点 consult 注册
  契约，企业行为经 harness 扩展点注册。桶语义选单 provider：该缝是"对整份
  工具列表施加一条授权收窄策略"，消费方每次解析恰好一个 adapter；两个
  provider 组合是顺序敏感的静默交互（与 #63 runtime evidence 同理），注册期
  显式拒绝优于解析期静默叠加。
- **上游替代方案**: 上游 harness 今日无任何工具装配定制缝（`deerflow/main`
  `81fa17c15ab` 与 v2.1.0 `345f08be0` 比对）；若上游未来提供等价的 per-run
  工具收窄扩展点并被采纳，本缝 consult 调用与本地桶整体让位（见移除条件）。
- **测试**: `backend/tests/unit/workflows/test_v2_executor_bridge_seam_contract.py`
  （registry 轨 deny-by-default 矩阵、与 legacy 包装行为等价、无 provider 直通、
  子进程探针两轨）、`backend/tests/test_extension_registry.py`、
  `backend/tests/test_extension_loader.py`、
  `backend/tests/test_agentplatform_extension_boundary.py`（解析链/重复拒绝）。
- **Owner**: workflow 运行时与企业接缝维护者
- **移除条件**: 过渡态——contract 批次移除 `executor_bridge` 的
  `_install_scope_aware_tool_loading` 与 `IDEER_TOOL_SCOPE_SEAM` 开关后本缝成为
  唯一轨道；终态——上游 harness 在工具装配处提供等价的 per-run 工具收窄
  扩展点（或等价 capability）并被本仓库采纳时，移除 consult 调用与本地桶。
  上游比对无对应缝，候选 rider 见
  `docs/upgrades/upstream-pr-candidates/host-seam-extension-points.md`。

### PATCH-040: 子代理组装 middleware 扩展缝（02-M6，票 #64）

- **文件**: `backend/packages/harness/deerflow/subagents/executor.py`
  （`SubagentExecutor._create_agent` 在 `build_subagent_runtime_middlewares`
  之后 consult `resolve_subagent_middlewares` 并 append pending 列表）——与
  PATCH-028 注册行共享文件（共享文件先例，不新增差异文件、不占预算）。
- **修改**: `_create_agent` 组装完上游 middleware 链后 consult
  `resolve_subagent_middlewares(extensions)`（解析链：executor extensions
  参数→进程 loaded 集→进程默认）；provider 存在且 pending 非空时
  `middlewares = [*middlewares, *pending]`（追加在链尾，与 legacy 包装对
  `create_agent` kwargs 的追加位置一致），否则链原样组装。注册方（expand
  过渡态）: `executor_bridge` 在 `IDEER_SUBAGENT_MIDDLEWARE_SEAM=registry` 时
  经 `set_default_subagent_middlewares` 注册 `WorkflowMiddlewareSource`（读
  `_PENDING_FILE_SCOPE` ContextVar：workflow 执行上下文返回
  `RunWorkspacePathsMiddleware`/`FilesystemScopeMiddleware` 列表，其余调用方
  返回空 = passthrough）。legacy 轨（executor 模块 `create_agent` 绑定包装）
  保留且默认生效。
- **原因**: workflow 节点 file-access 中间件注入此前靠导入期包装 executor 模块
  的 `create_agent` 模块级绑定（02-M6 发现 2），影响一切经该绑定组装的 agent；
  接缝化后注入点收敛到 `_create_agent` 的显式 consult。桶语义选单 provider：
  pending 中间件集合是"当前执行上下文"的投影，两个 provider 对同一执行上下文
  各自声明集合无合并规则，注册期拒绝（同 #63 语义）。
- **上游替代方案**: 上游 `SubagentExecutor._create_agent` 今日无任何执行上下文
  middleware 贡献缝（比对同 PATCH-039）；`AgentBuildContext` 只携带注册期信息，
  无 per-execution 输入。若上游提供等价缝并被采纳，本缝让位（见移除条件）。
- **测试**: `backend/tests/unit/gateway/test_subagent_executor.py`
  （`TestCreateAgent::test_registry_seam_appends_pending_middlewares_after_upstream_chain`）、
  `backend/tests/unit/workflows/test_v2_executor_bridge_seam_contract.py`
  （provider 单元 + 子进程探针）、registry/loader/boundary 同 PATCH-039 行；
  端到端等价由 `tests/integration/workflows/test_v2_subagent_receipt_executed_workflow.py`
  （真实链路经 FilesystemScopeMiddleware 写沙箱产物）持续背书。
- **Owner**: workflow 运行时与企业接缝维护者
- **移除条件**: 过渡态——contract 批次移除 `_install_scope_aware_create_agent`
  与 `IDEER_SUBAGENT_MIDDLEWARE_SEAM` 开关后本缝成为唯一轨道；终态——上游
  subagent executor 提供等价的执行上下文 middleware 贡献扩展点（或
  `AgentBuildContext` 携带 per-execution 输入的等价机制）并被采纳时移除。上游
  无对应缝（比对同 PATCH-039），候选 rider 见同文档。

### PATCH-041: builtin 工具覆盖扩展缝（02-M6，票 #64）

- **文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
  （`_assemble_lead_agent` 在懒加载 `deerflow.tools.builtins` 后 consult
  `resolve_builtin_tool_overrides` 覆盖 `setup_agent`）——与 PATCH-010 注册行
  共享文件（共享文件先例，不新增差异文件、不占预算）。
- **修改**: bootstrap 装配路径上，`setup_agent` 经
  `builtin_overrides.resolve_builtin_tool("setup_agent", setup_agent)` 解析；
  无 provider（或 provider 不管该名）时用上游 stock 工具（零行为变化），
  非覆盖名恒回退 default。注册方（expand 过渡态）:
  `app/agentplatform/agent_bootstrap.py:install()` 在
  `IDEER_BUILTIN_TOOL_SEAM=registry` 时经 `set_default_builtin_tool_overrides`
  注册 `CanonicalBuiltinToolOverrides`（`setup_agent`→canonical 资源目录工具，
  其余 builtin 回退 default）；gateway 组合点（`app/gateway/services.py`）仍以
  `install()` 为唯一入口。legacy 轨（改写
  `deerflow.tools.builtins.setup_agent` / `...setup_agent_tool.setup_agent`
  两处模块属性并在 tool module 挂 `get_session_factory`）保留且默认生效；
  canonical 工具的 catalog session 缝统一为
  `app.agentplatform.agent_bootstrap.get_session_factory`（原经 tool module
  挂载属性间接可达，树内无其它读取方，测试面无断裂）。
- **原因**: canonical setup_agent 此前靠导入期改写上游两个模块属性全局生效
  （02-M6 发现 3）；接缝化后覆盖决策发生在唯一消费点（lead-agent bootstrap
  装配的 builtin 绑定处）。桶语义选单 provider：builtin 是 host 单例，两个
  provider 争夺同名 builtin 是组合错误，注册期拒绝（同 #63 语义）。
- **上游替代方案**: 上游 `_assemble_lead_agent` 今日对 builtin 工具无任何覆盖
  缝（比对同 PATCH-039）；若上游提供等价 builtin 替换/覆盖扩展点并被采纳，
  本缝让位（见移除条件）。
- **测试**: `backend/tests/unit/agentplatform/test_agent_bootstrap_seam.py`
  （两轨子进程探针、install 幂等、覆盖解析合同、canonical 行为：空 soul 拒绝、
  默认 agent SOUL 文件写入、无 session factory 回退 agent store）、
  registry/loader/boundary 同 PATCH-039 行；真实 E2E 由
  `tests/test_setup_agent_http_e2e_real_server.py`（Real E2E lane）背书。
- **Owner**: 资源目录（canonical agent）域维护者
- **移除条件**: 过渡态——contract 批次移除 `agent_bootstrap.install()` 的属性
  改写分支与 `IDEER_BUILTIN_TOOL_SEAM` 开关后本缝成为唯一轨道；终态——上游
  lead-agent 装配提供等价的 builtin 工具覆盖/替换扩展点并被采纳时移除。上游
  无对应缝（比对同 PATCH-039），候选 rider 见同文档。

## Enforcement

每次收敛提交前重跑对照命令并更新本台账；存在未登记差异即门禁失败。
属于 AgentPlatform 的运行时行为必须实现在 `backend/app/agentplatform/` 或
`backend/packages/agentplatform-extension/`，不得靠扩张本 fork 解决。

## 结构化注册表

机器可读注册表，由 `scripts/check_upstream_patches.py` 校验（CI `test-lane-shadow`
的 test-contracts job 调用，`--upstream-baseline` 必须与本表 `upstream_baseline`
pin 一致）。`paths` 为相对仓库根的 harness 前缀路径，必须覆盖对照基线下的全部
差异文件；base→head 有 diff 的补丁（含新登记行）必须 `verification_status: current`
并携带 `current_verification` 证据，未变补丁 `historical` 即可。修改本表时同步
更新 `budget_basis` 并在巡检记录留痕。预算 basis 语义：`code_files` 增长与
`previous_code_files` 偏离 base 注册表分配均须携带非空 `amendment` 修正案方为
合法；`document_files` 的任何变化须携带修正案，且 `previous_document_files`
必须与 base 注册表分配一致。

<!-- upstream-registry:start -->
```json
{
  "schema_version": 1,
  "upstream_baseline": "345f08be00c8a9495079b732a39b46aa9af1584e",
  "file_budget": 67,
  "budget_basis": {
    "code_files": 46,
    "document_files": 21,
    "previous_code_files": 45,
    "previous_document_files": 21,
    "amendment": "Ticket #64 (02-M6) registers PATCH-039 on a new upstream diff file, deerflow/tools/tools.py (get_available_tools consults the tool-scope seam at the end of assembly): 45+1 code files = 46, total 66->67. PATCH-040 (subagents/executor.py) and PATCH-041 (agents/lead_agent/agent.py) share files already registered by PATCH-028/010 (shared-file precedent PATCH-004/023) and add no budget files; the registry/resolve additions live on the PATCH-024/038 files. See the 2026-10-13 inspection row for ticket 64."
  },
  "patches": [
    {"id": "PATCH-001", "paths": ["backend/packages/harness/deerflow/community/ragflow/client.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-002", "paths": ["backend/packages/harness/deerflow/extensions/notify.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-003", "paths": ["backend/packages/harness/deerflow/config/AGENTS.md"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-004", "paths": ["backend/packages/harness/deerflow/config/workflow_runtime_config.py", "backend/packages/harness/deerflow/config/app_config.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-005", "paths": ["backend/packages/harness/deerflow/agents/middlewares/tool_receipt_middleware.py", "backend/packages/harness/deerflow/tools/builtins/task_tool.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-006", "paths": ["backend/packages/harness/deerflow/persistence/bootstrap.py", "backend/packages/harness/deerflow/persistence/migrations/env.py"], "verification_status": "historical", "lifecycle_status": "closed"},
    {"id": "PATCH-007", "paths": ["backend/packages/harness/deerflow/uploads/code_evidence.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-008", "paths": ["backend/packages/harness/deerflow/uploads/code_analysis.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/gateway/test_code_analysis.py tests/unit/agentplatform/test_analyze_code_evidence_tool.py tests/test_sandbox_tools_security.py tests/unit/resources/test_canonical_sandbox.py tests/integration/workflows/test_v2_run_record.py -q", "result": "213 passed (candidate incorporating develop cf10c6136)"}},
    {"id": "PATCH-009", "paths": ["backend/packages/harness/deerflow/persistence/models/workflow_v2.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-010", "paths": ["backend/packages/harness/deerflow/agents/lead_agent/agent.py", "backend/packages/harness/deerflow/agents/lead_agent/prompt.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/agentplatform/test_frozen_agent_inputs.py tests/unit/agentplatform/test_agent_bootstrap_seam.py -q", "result": "expand phase (ticket #64 builtin seam rides on this file): 12 passed"}},
    {"id": "PATCH-011", "paths": ["backend/packages/harness/deerflow/persistence/engine.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-012", "paths": ["backend/packages/harness/deerflow/sandbox/local/local_sandbox_provider.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-013", "paths": ["backend/packages/harness/deerflow/runtime/runs/manager.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-014", "paths": ["backend/packages/harness/deerflow/persistence/migrations/versions/0001_baseline.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-015", "paths": ["backend/packages/harness/deerflow/persistence/migrations/_chain_meta.py", "backend/packages/harness/deerflow/persistence/migrations/alembic.ini", "backend/packages/harness/deerflow/persistence/migrations/versions/20260908_unify_migration_chains.py", "backend/packages/harness/deerflow/persistence/migrations/versions/20261001_rejoin_upstream_line.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-016", "paths": ["backend/packages/harness/deerflow/sandbox/local/local_sandbox.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-017", "paths": ["backend/packages/harness/deerflow/sandbox/tools.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/gateway/test_code_analysis.py tests/unit/agentplatform/test_analyze_code_evidence_tool.py tests/test_sandbox_tools_security.py tests/unit/resources/test_canonical_sandbox.py tests/integration/workflows/test_v2_run_record.py -q", "result": "213 passed (candidate incorporating develop cf10c6136)"}},
    {"id": "PATCH-018", "paths": ["backend/packages/harness/deerflow/sandbox/encoding.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-019", "paths": ["backend/packages/harness/deerflow/sandbox/search.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-020", "paths": ["backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-021", "paths": ["backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-022", "paths": ["backend/packages/harness/deerflow/community/ragflow/tools.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-023", "paths": ["backend/packages/harness/deerflow/config/app_config.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-024", "paths": ["backend/packages/harness/deerflow/extensions/__init__.py", "backend/packages/harness/deerflow/extensions/registry.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/test_extension_registry.py tests/test_extension_loader.py tests/test_agentplatform_extension_boundary.py tests/test_run_worker_delivery.py::test_retrieval_evidence_is_persisted_with_terminal_run tests/unit/knowledge/test_retrieval_receipts.py -q", "result": "104 passed (expand phase, ticket #64 adds the three host-seam buckets and resolve functions on this file; registry, loader, boundary and PATCH-024 evidence lanes green)"}},
    {"id": "PATCH-025", "paths": ["backend/packages/harness/deerflow/models/openai_codex_provider.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-026", "paths": ["backend/packages/harness/deerflow/runtime/journal.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-027", "paths": ["backend/packages/harness/deerflow/runtime/runs/worker.py", "backend/packages/harness/deerflow/runtime/runs/manager.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-028", "paths": ["backend/packages/harness/deerflow/subagents/executor.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/gateway/test_subagent_executor.py tests/unit/knowledge/test_retrieval_receipts.py -q", "result": "expand phase (ticket #64 assembly seam rides on this file): 124 passed"}},
    {"id": "PATCH-029", "paths": ["backend/packages/harness/deerflow/subagents/registry.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-030", "paths": ["backend/packages/harness/deerflow/agents/middlewares/input_sanitization_middleware.py", "backend/packages/harness/deerflow/client.py", "backend/packages/harness/deerflow/extensions/gateway.py", "backend/packages/harness/deerflow/skills/frontmatter.py", "backend/packages/harness/deerflow/skills/projection.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-031", "paths": ["backend/packages/harness/deerflow/persistence/models/legacy_tables.py", "backend/packages/harness/deerflow/persistence/models/__init__.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-032", "paths": ["backend/packages/harness/deerflow/utils/readability.py"], "verification_status": "historical", "lifecycle_status": "open"},
    {"id": "PATCH-033", "paths": ["backend/packages/harness/deerflow/extensions/ordering.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && PYTHONPATH=.:tests uv run pytest tests/test_extension_ordering.py -q", "result": "12 passed"}},
    {"id": "PATCH-034", "paths": ["backend/packages/harness/deerflow/tools/builtins/update_agent_tool.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && PYTHONPATH=.:tests uv run pytest tests/test_update_agent_tool.py -q", "result": "27 passed"}},
    {"id": "PATCH-035", "paths": ["backend/packages/harness/deerflow/CLAUDE.md", "backend/packages/harness/deerflow/agents/CLAUDE.md", "backend/packages/harness/deerflow/agents/memory/CLAUDE.md", "backend/packages/harness/deerflow/agents/middlewares/CLAUDE.md", "backend/packages/harness/deerflow/community/tavily/CLAUDE.md", "backend/packages/harness/deerflow/config/CLAUDE.md", "backend/packages/harness/deerflow/extensions/CLAUDE.md", "backend/packages/harness/deerflow/mcp/CLAUDE.md", "backend/packages/harness/deerflow/models/CLAUDE.md", "backend/packages/harness/deerflow/persistence/migrations/CLAUDE.md", "backend/packages/harness/deerflow/persistence/user/CLAUDE.md", "backend/packages/harness/deerflow/reflection/CLAUDE.md", "backend/packages/harness/deerflow/runtime/CLAUDE.md", "backend/packages/harness/deerflow/sandbox/CLAUDE.md", "backend/packages/harness/deerflow/skills/CLAUDE.md", "backend/packages/harness/deerflow/subagents/CLAUDE.md", "backend/packages/harness/deerflow/tools/CLAUDE.md", "backend/packages/harness/deerflow/tracing/CLAUDE.md", "backend/packages/harness/deerflow/tui/CLAUDE.md", "backend/packages/harness/deerflow/utils/CLAUDE.md"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "python3 scripts/sync_agent_guidance.py --check", "result": "mirror consistency check passed (28 pairs)"}},
    {"id": "PATCH-038", "paths": ["backend/packages/harness/deerflow/extensions/__init__.py", "backend/packages/harness/deerflow/extensions/registry.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/test_extension_registry.py tests/test_extension_loader.py tests/test_agentplatform_extension_boundary.py -q", "result": "75 passed (new duplicate-registration contract tests red 4/4 before the fix, green after; PATCH-024 lane re-verified 35 passed)"}},
    {"id": "PATCH-039", "paths": ["backend/packages/harness/deerflow/tools/tools.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/workflows/test_v2_executor_bridge_seam_contract.py tests/unit/workflows/test_v2_agent_adapter.py tests/test_tool_deduplication.py -q", "result": "33 passed (expand phase: two-track equivalence matrix, no-provider passthrough and subprocess probes green with the legacy default track; tool assembly stock behavior re-verified by the dedup suite)"}},
    {"id": "PATCH-040", "paths": ["backend/packages/harness/deerflow/subagents/executor.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/gateway/test_subagent_executor.py -q", "result": "106 passed (expand phase: executor suite green incl. the registry seam appending pending middlewares after the upstream chain; shared file with PATCH-028)"}},
    {"id": "PATCH-041", "paths": ["backend/packages/harness/deerflow/agents/lead_agent/agent.py"], "verification_status": "current", "lifecycle_status": "open", "current_verification": {"command": "cd backend && UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests uv run --no-sync pytest tests/unit/agentplatform/test_agent_bootstrap_seam.py tests/unit/tools/test_setup_agent_tool.py tests/unit/agentplatform/test_frozen_agent_inputs.py -q", "result": "19 passed (expand phase: builtin override seam contract suite, stock tool suite and lead-agent frozen-input lane green with the legacy default track: probes of both tracks, install idempotency, canonical behavior)"}}
  ]
}
```
<!-- upstream-registry:end -->
