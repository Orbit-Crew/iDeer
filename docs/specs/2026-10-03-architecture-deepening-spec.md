---
id: docs-specs-2026-10-03-architecture-deepening-spec
kind: plan
status: archived
owner: repository maintainers
scope: architecture-deepening design record for eight candidates — role-to-permission actor ladder, knowledge module seam, turn-submit and thread-page frontend modules, workflow_worker package split with run/registry seams, contract single ownership, skill-selection consolidation, and the i18n single seam; upstream attribution compared against deerflow v2.1.0 (345f08be)
archived-reason: implemented in this candidate — backend/app/agentplatform/resources/actors.py, frontend/src/core/threads/use-thread-page.ts, frontend/src/core/skills/selection.ts, the backend/app/workflow_worker/ package (run_session.py, registry.py, entrypoint.py), and backend/tests/unit/resources/test_resource_actors.py all exist (checked 2026-10-04); the nine tickets lived in the delivery workspace .scratch/architecture-deepening/, which is not committed to the candidate, and no local branch architecture-deepening remains — the body's ticket and branch names are historical delivery references
triage: ready-for-agent
---

# 架构深化设计记录（八候选）

- 日期：2026-10-03
- 状态：设计已收敛；九张工票已全部实施（分支 `architecture-deepening`，2026-10-03；集成分支终验 `pr-standard` 全部子车道 status=0，集成期修正两条测试断言随候选记录于迁移台账）
- 来源：2026-10-02 按改动热度驱动的架构评审（报告为会话产物，不入库）；三个探索代理提供文件:行号证据；上游归属按 deerflow v2.1.0（345f08be）比对
- 术语：turn（一轮）已录入根 `CONTEXT.md` 的 Execution 区
- 工票：`.scratch/architecture-deepening/issues/01`–`09` 按本规格切分

## 总体决策

1. 交付顺序：八个候选全部设计完成后分波实施。
2. 波次：W1 后端授权（候选 2 → 1）、W2 前端对话（候选 3 → 4）、W3 工作流（候选 5 → 6）、W4 小项（候选 7、8，可穿插）。
3. 上游策略（按文件归属调查修正版）：
   - 后端候选（1、2、5、6）涉及文件全部为 iDeer 本地自有（`agentplatform/`、`workflow_worker.py`、resources 系路由在上游不存在），就地深化，无上游冲突面。
   - 前端候选（3、4、7、8）涉及文件几乎全部来自上游（v2.1.0 合并对 `core/threads/hooks.ts` 做过 1068 行语义合并、`input-box.tsx` 345 行、i18n 三件套键并集）：新深模块一律放本地新文件，上游文件只在调用点做最小替换。本地自有例外：`slash-suggestions.ts`（81 行）。
4. PR 与车道：每候选一个 PR。候选 2 是授权变更，跑授权标准车道 + `pr-standard`；候选 1 涉及持久化契约，补对应 contract 与 integration 检查；其余按各自标准车道；PR 门槛统一 `pr-standard`。测试移动与删除一律记入 `docs/testing/test-migration-ledger.md`，并重跑 `python3 scripts/test_inventory.py`。
5. 决策问答编号沿用评审会话：Q1-Q4 总体（上文四条），Q5-Q12 逐候选（下文各节）。

## 候选 2：角色到权限的 actor 阶梯（W1 第一 PR）

- 问题：把用户角色映射为权限的不变量在 12+ 处重复拼装，存在三种漂移变体（角色回退 `unknown`、回退 `viewer`、权限裁剪为 READ|USE），兄弟路由为避 import 环互相引用私有助手（`knowledge_tests.py:25`、`visibility_applications.py:313-317`）。
- 决策（Q5=a）：新模块 `backend/app/agentplatform/resources/actors.py`；网关与 agentplatform 的全部调用点经它构造 actor；两处路由间私有 import 直接删除，不留过渡别名。
- 调用点清单：`routers/resources.py:347-361`（规范版）、`gateway/services.py:1535,1553`、`canonical_agent_run_preparation.py:101,126`、`user_deletion.py:234`、`routers/admin.py:834`、`routers/assistants_compat.py:90`、`knowledge/worker.py:68-78`、`tools/zeroing_run_tool.py:143-163`、`agent_bootstrap.py:109`、`tools/setup_agent_tool.py:62`、`tools/update_agent_tool.py:63`。
- 实施要点（GitNexus 影响分析，2026-10-03）：`resources.py:_resource_actor` 上游影响 73 处、风险 CRITICAL，全部为其文件内 67 个直接调用；因此规范函数改为对 `actors.actor_from_user` 的一行委托（签名不变，调用面零改动），漂移站点逐个迁移。已验证的 TDD 首片：`tests/unit/resources/test_resource_actors.py` 红（模块缺失）→ 绿（8 项），随本轮回退撤销，实施时重建。
- 拆分口径：阶梯（`role_permissions`）与 `actor_from_user` 进共享模块；`knowledge/worker.py` 的账号状态策略（缺失/禁用用户保 READ 底）与 `zeroing_run_tool.py` 的运行时上下文抽取留在调用点，经 `role_permissions` 取权限。
- 约束：保留本地授权否决语义（2026-09-08 决策）；抽取只集中构造，不改变角色授予的内容（漂移回退按规范阶梯修正属预期修复）。
- 测试：自建阶梯的夹具（`tests/unit/knowledge/test_knowledge_documents.py:40-47`、`test_knowledge_tests_api.py:91-97` 等）改为共用构造器；断言与覆盖不变。

## 候选 1：知识模块接缝（W1 第二 PR）

- 问题：知识模块接口面（5 个 service 构造器、7 种错误类型、commit 纪律、provider 管道、ORM 模型泄漏）几乎与实现等宽；守卫、提交、审计、provider-503 落在路由里，守卫一处漂移 409≠404。
- 决策（Q6=a）：`knowledge/` 包内新增门面，五个 service 保留为实现；门面收拢可见性守卫、provider 获取、提交、审计、统一错误分类；路由收缩为解析即调用。`knowledge_tests.py` 两处 409 统一为 404（`ResourceNotFound` 语义）。
- 约束：保持 Resource Governance V2 表面不变（`/api/resources` 规范来源、可见性过滤）；不重开数据源决策。
- 测试：8 个网关测试文件停止 patch 路由模块全局，改为在接缝注入；409 断言更新为 404；ORM 表注册副作用随接缝收进模块。

## 候选 3：turn-submit 模块（W2 第一 PR）

- 问题：发送一条消息是作曲器、页面、流模块的六文件握手；防重复围栏独立实现三次（`chat-page.tsx:245`、`input-box.tsx:463,1613`、`hooks.ts:2285`）；生命周期回调存进第三方 refs（`hooks.ts:2289-2294`）。
- 决策（Q7=a）：新本地模块（`core/threads/` 下新文件）拥有草稿恢复、附件预上传、围栏、失败策略；第一版只管消息提交链，`/goal`、`/compact` 与建议 fetch 不收。上游文件只在调用点替换。
- 测试：提交链行为测试迁至模块接口；`input-box.test.tsx` 保留接线冒烟；页面测试卸下提交守卫断言（随守卫迁走）。

## 候选 4：thread-page 模块（W2 第二 PR）

- 问题：对话页面被拼装三次（`chat-page.tsx` 607 行仅剩 showcase 消费方；`chats/[thread_id]` 711 行对上游 5 行薄壳已结构分叉；agents 页 507 行），welcome 态、空对话重定向、停止/分支各自重复，注释块逐字复制。
- 决策（Q8=a）：钩子形状；本地新文件 `frontend/src/core/threads/use-thread-page.ts` 拥有共享逻辑，三个路由保留各自 JSX；不恢复上游薄壳形状（另案收敛决策）。
- 测试：流接线、重定向、welcome 态断言迁至钩子测试；两个页面测试文件（1586/879 行）收缩为适配器断言。

## 候选 5：run 模块（W3 第一 PR）

- 问题：`execute_workflow_task`（约 195 行）熔合十来条策略且无内部接缝；验收脚本重实现 fork-interrupt 恢复协议（`run_fault_zeroing_acceptance.py:109-129,252-275`）；集成测试 mock 被测单元自己的内部（`test_fault_zeroing_worker_runtime.py:302`）。
- 决策（Q9=a）：`workflow_worker.py` 升级为同名包；`__init__.py` 回导出 `main` 与 `execute_workflow_task`（外部 import 零改动）；执行与恢复协议进 `run_session.py`，暴露 `execute(task)` 与 `resume(run, command)` 两个入口；注册表构建进 `registry.py`；验收脚本与队列循环改调入口。
- 测试：集成测试跨 execute/resume 接缝；废除 mock `build_canonical_registry` 的做法；`RecordingAgent` 是合法适配器，保留。

## 候选 6：契约唯一归属（W3 第二 PR）

- 问题：契约声明式内容（五件产物清单、报告章节、覆盖类别、披露短语）在五处复述；一次规则改动是五文件编辑，靠 parity 测试缝合。
- 决策（Q10=a）：`contract.py` 为唯一来源；新增生成脚本从它产出沙箱副本；parity 测试保留守护；YAML 提示词与 SKILL/SOUL 文案改为引用契约（先例 `0f547a4c0`），契约短语本身不改。
- 约束：ADR-0004 的 fail-closed 语义与按运行钉定不动；沙箱无法 import `app.*`，内嵌副本仍是既定策略；改的是引用方式，不是执行方式。
- 测试：parity 测试保住；`RecordingAgent` 断言的披露短语不变（改的是提示词里的规则复述，不是短语本身）。

## 候选 7：技能选择收拢（W4）

- 问题：三条 UI 路径（"/" 打字流、SkillPicker 浮层、selectedSlashSkill 芯片）、两份同名 matcher（`input-box-helpers.ts:178` 与 `slash-suggestions.ts:51`，规则不同）、两套门控（`agentSkillNames` 无生产调用方）、"/name " 字符串协议散落三处（提交前缀 `input-box.tsx:1569-1574`、草稿 `composer-draft.ts`、`resolveComposerDraft:118-130` 退化规则）。
- 决策（Q11=a，用户已撤销"拆分两入口"的提议，两入口保持同等行为，符合 `docs/specs/2026-09-25-deerflow-frontend-experience-spec.md` 故事 46）：新本地模块 `frontend/src/core/skills/selection.ts`：
  - `offerableSkills(skills, allowedNames)` 单一门控（只留 `allowedSkillNames` 一套，智能体路由已传 `agent.skills`）；
  - `matchSkills(scope, query, reservedExtra?)` 单一 matcher，统一为"匹配名称或描述"（行为变化："/" 打字流开始匹配描述；条数上限保留；名称或描述为浮层现行规则）；
  - `select`/`clear`/`selected` 状态、`submitTextFor(text)` 产出前缀、`fromDraft(skillName, scope)` 吸收 `resolveComposerDraft` 退化规则；
  - 线上协议一字节不变（后端纯语法解析，UI 过滤本就只是建议，调查已证实）。
  - input-box.tsx 改动点：删 162 行别名 import、605-606 状态挪进钩子、1569-1574 换 `submitTextFor` 调用、1734-1759 与 1773-1779 两段 memo 换模块调用；芯片、下拉、浮层 JSX 不动。
  - 删除物：`filterSkillsForAgent`（helpers:166）、两份 matcher 合一、`agentSkillNames`/`agentSkillsLoading` prop、`task-input.ts` 的死代码 `prepareTaskSubmission`（仅测试引用，连同其测试删除并记账）。
- 测试：匹配规则单测迁至 selection.ts 接口（纯函数）；`slash-suggestions` 与 `input-box-helpers` 的 matcher 测试合并；`input-box-agent-skill-hydration.dom.test.tsx` 改用 `allowedSkillNames`；跨栈契约 `contracts/slash_skill_contract.json` 两侧测试跑通确认（协议未变，预期不受影响）。

## 候选 8：i18n 单一接缝（W4）

- 问题：每条新文案跨三文件编辑（`types.ts` 2,047 行手工接口）；页面硬编码中文绕过接缝（`chats/[thread_id]/page.tsx:639-644,83-84`、`agents/[agent_name]/chats/[thread_id]/page.tsx:449`）。
- 决策（Q12=a）：en-US 为真相之源，`Translations = typeof enUS`；`types.ts` 变派生；zh-CN 是适配器，缺键即类型错误；硬编码中文迁回 zh-CN.ts。
- 测试：locale 测试保留；缺键检查从运行时测试简化为编译期保证的部分按"覆盖不减"原则处理并记账。

## 已知事实备查（评审调查结论）

- 上游 `/agent` 命令仅存在于飞书、Telegram 渠道（`channels/manager.py:2841-2885`）；Web 委派是模型侧 `task` 工具（Ultra 模式），无作曲器语法。本次不新增。
- 后端对 "/name " 前缀是纯语法解析（`deerflow/skills/slash.py:38-49` 正则 + 保留名），普通对话里 UI 建议只是发现入口；智能体会话由闭包强制（`skill_outside_agent_closure` 409）。
- 内置 slash 命令仅 `/goal`、`/compact`（`input-box.tsx:709-723`）。
