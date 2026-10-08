---
id: disclosure-dual-track-protocol-v2-2026-10-08
kind: policy
status: current
owner: repository maintainers
scope: versioned reading answer protocol, rubric anchors, and independent grading calibration
last-verified: 2026-10-08
verified-against: docs/specs/2026-10-08-disclosure-dual-track-recovery-spec.md
---

# 渐进式披露阅读协议 v2

## 协议身份与双轨边界

本协议 ID 为 `disclosure-reading-v2`。双轨注册表将 `legacy-pdr-2026-10-07-16cc740f` 指向旧实验 `pdr-2026-10-07-16cc740f`，作为本次映射使用的旧轨兼容标识；历史冻结清单只记录 experiment ID，没有单独的 protocol ID 字段，因此此兼容标识不声称曾写入原清单。旧实验沿用其冻结的旧提示、答案、评分和阈值；原始记录与裁决永久保留，不回填本协议分数。新版正式轮次使用 `disclosure-reading-v2` 并单独报告 verdict。两轨都保留 8 个任务 × 每候选 2 次、每个候选 16 个逻辑槽的固定分母；失败槽不删除、不补抽。

新版结果通过 `all 16/16 applicable-required answers correct`、零 critical error、零历史权威误用、零未裁决分歧，以及常规任务 pooled Markdown unique-byte median 比冻结 baseline 至少下降 30% 才能判通过。缺答案或 submission-time / cost 证据使相应门禁 incomplete；不得用失败关闭时钟代替提交耗时。新版未通过时，旧轨不启动。各轨单独列协议 ID、候选和冻结输入、样本数、正确率、失败类别、成本、门禁与限制；不得合并分数或将新版结果追溯改写为旧实验成绩。

旧协议的任务数、门槛、读数、分数与 verdict 以票11报告为准。下面的锚点只用于 v2。候选侧必须在正式会话开始前冻结内容清单、证据角色映射、任务文本、评分锚点、工具配置和队列；评分者不因候选名称改变规则。

## 任务答案格式

每份答案必须且只需提交以下六个字段。字段名保持与旧记录兼容；内容按 v2 锚点评分。

| 字段 | 需要回答的内容 |
| --- | --- |
| `entry` | 真实代码或公开 seam 的起点，以及题目给出的行为如何落到该处。任务未指定实现对象时，指出仍缺少的具体事实，不虚构文件或组件。 |
| `constraints` | 影响本题行为的当前不变量、所有权、边界和必须保留的约束。 |
| `authorities` | 支撑结论的当前规范及精确章节、符号或测试；区分指引、契约、实现和测试证据。 |
| `relevant_decisions` | 触发时适用的 decision、ledger 或生命周期约束；未触发时明确写“不适用”并给出条件。 |
| `validation` | 本题第一项聚焦验证、匹配静态检查及完成阶段适用 lane；注明只计划还是实际运行及结果。 |
| `unknowns` | 未由任务或已查证材料决定的事实、已检查边界，以及会改变实现或评分的未决条件。无未决项时写明依据。 |

一个事实只要在任一字段中清楚出现即可认定表达存在；字段位置、逐字复述和文件命名风格本身不计分。引用应足以让第三方定位证据，未读内容不得声称已核实。历史报告只能作历史证据，不能替代当前规则。

## 评分规则

每个锚点由两位评分者独立标为 `met`、`missed` 或 `not-applicable`，附答案摘录和候选证据。任务总体正确要求全部适用必答锚点 `met` 且无 critical error。任一必答遗漏导致该任务不正确；条件锚点仅在触发时进入必答集合。辅助锚点单列报告，不影响正确性。无法确认任务条件时，不得默认为不适用：列入 unknowns，并按题面决定是否计为缺失。

严重遗漏（critical error）是会导致实际实现破坏题目明确保护的不变量、采用错误权威作为当前契约，或执行明显不匹配/不安全验证的错误陈述或建议。普通遗漏是必答信息未出现但没有相反或危险主张。锚点之间不抵消；辅助锚点正确不能抵消必答缺失。评分不得以答案长度、读了多少字节、是否猜中 rubric wording 或报告了额外无害信息代替证据判断。

证据来源按优先级使用：冻结候选中的当前 `AGENTS.md` / `CLAUDE.md` 规则（以仓库约定认定 AGENTS 是源）、当前契约或规范、候选源码与测试、适用 decision / ledger。历史报告仅支持历史归因。路径或章节指向错误、候选中不存在、或无法支持该主张的引用不构成证据。两个等价表述若表达同一边界和适用条件，按语义判定，不要求固定术语。

## 冻结任务与评分锚点

必答锚点是任务可观察的完成要求；条件锚点只在题面条件成立时必答；辅助锚点用于诊断，不计任务正确率。下表列证据角色与定位方向，正式冻结时为每个候选绑定实际路径、章节 / 符号和摘要，不把答案位置放入读者提示。

| ID / 场景 | 具体题目行为 | 必答锚点 | 条件锚点 | 辅助锚点 | 主要证据来源 |
| --- | --- | --- | --- | --- | --- |
| UI | 在设置页现有外观中加一个可选 header action；不开启时旧界面不变，点击调用父级给定回调。 | `entry` 指向题目确定的设置页/组件与展示 seam；`constraints` 保持可选、默认关闭、回调由 owner 持有及 UI/领域逻辑分层；`validation` 覆盖开关两态和点击回调。 | 若改生成 UI，说明改 registry/source 而非生成产物；若涉及客户端交互才启用 client state。 | 命名、Tailwind `cn()`、最窄 lane。 | `frontend/AGENTS.md`；具体页面与组件源码/测试；前端测试约定。 |
| Chat submit | 同一 Turn 的 pending submit 被重复触发时只允许一个提交副作用；随后可继续正常提交下一 Turn。 | 指出 submit gate 和 Turn 生命周期 owner；保持同 Turn 去重而不误拦下一 Turn；测试重复提交及后续提交。 | 若题面包含 stream 事件，区分 submit gate 与消息合并；涉及持久化/Run 恢复时加对应生命周期契约。 | draft/附件预上传顺序、共享页面接线。 | `frontend/src/AGENTS.md`；`turn-submit.ts` / `hooks.ts`；turn-submit focused tests。 |
| Chat SDK merge | SDK 可把同一消息拆成多个 chunk；合并结果按消息 ID 保持一条消息，且增量内容完整。 | 明确 SDK message chunk assembly 与 canonical ID 去重 owner；指出相同 ID 合并内容、不同 ID 保留独立消息；验证重复 ID 多 chunk。 | 若跨 run/历史/实时来源，说明每个来源的身份和合并边界。 | 展示排序、增量渲染性能。 | `frontend/src/AGENTS.md` 中 SDK/消息规则；thread stream/merge 源码与测试。 |
| Chat Gateway | Gateway SSE 重连或重复投递同一事件时，客户端不把一个事件当作两个不同事件；Gateway 仍遵守传输契约。 | 区分 Gateway 事件交付与 UI message merge；列出事件 identity/stream owner 及准确 transport invariant；验证重投递/重连路径。 | PAT observer cancel/auth 行为只有题面提及时要求；否则写不适用。 | SDK 下游消息组装。 | `backend/docs/STREAMING.md` Gateway/SSE 章节；Gateway SSE consumer / contract tests。 |
| Chat embedded stream | `DeerFlowClient.stream()` 同一逻辑消息可跨 mode 发送；避免重复消息且 usage 统计不丢失。 | 指出嵌入式 stream 的独立 owner；保留三个 ID set 各自用途，不能合并；分别核验跨模式重复和 usage。 | 只有题面含 Gateway 同步变更时增加 Gateway 锚点。 | SDK/UI 最终顺序。 | `backend/docs/STREAMING.md` 三个 ID set 章节；`client.py` 与 `backend/tests/test_client.py`。 |
| Knowledge | 资源列表按用户可见范围过滤后再分页，返回 canonical identity/visibility；provider binding 不暴露给客户端。 | `entry` 指向 `/api/resources` list 和可见性服务 seam；`constraints` 过滤先于分页且服务端保留 provider binding；测试跨页不可见项不泄露且总数一致。 | 仅当任务改变资源发布、归档或 fork 生命周期时触发生命周期 decision。 | create endpoint / 双层真源边界。 | 根 `AGENTS.md` Enterprise interfaces；resources router/service；visibility contract tests。 |
| Permissions | 共享资源列表仅显示用户有权查看的资源，过滤在分页前；角色操作能力仍按矩阵执行。 | 区分 visibility 与 role-operation authorization；指出当前规则、矩阵与代码 seam；测试至少一个允许和一个拒绝边界。 | 可见性申请、KB/provider 身份、设备本地执行仅在题面触发时读对应流程/decision。 | 管理员路径或性能。 | `docs/permission-model-redesign.md` 当前原则/可见性节、`docs/permission-matrix.md` 核心矩阵；authz/resource service；contracts。 |
| Tests | 将一个已有单测从旧路径迁入新分层，保持收集节点和断言；同步迁移记录。 | 指出当前目录和测试层；先查迁移流程再改测试，保持断言；运行聚焦测试和 inventory。 | 仅 lane 合约变化时才展开对应 PR/lane 组合，删除测试时核对删除登记要求。 | 按实际文件选 Vitest/Rstest。 | `docs/testing/README.md`、`test-migration-ledger.md`、inventory 工具与节点。 |
| Runtime | 取消一个运行中任务后不得重复执行已提交的远程副作用；恢复时遵循租约与状态生命周期。 | 指出 Run/Thread 生命周期和取消/恢复 owner；区分回滚与不可撤销远程副作用；验证取消和恢复合同。 | 仅改 harness 时按 Extension → Adapter → 登记 patch 并验证 customization disabled/enabled；事件投影仅在触及时读其 contract。 | 本地设备执行授权边界。 | `backend/docs/development-reference.md` Run recovery 章节；Run manager/worker/store；recovery contract tests。 |
| Upstream | 吸收新的上游 harness 行为时保留本地企业约束，逐项处理冲突并记录兼容验证。 | 确认有效 upstream lock；冲突按行为/契约逐条裁决；分别报告 sync、product integration、compatibility validation。 | 涉及 harness patch 时登记理由、替代、影响、验证、owner、移除条件。 | 上游纯镜像路径规则。 | 根 `AGENTS.md` Enterprise changes；`UPSTREAM_PATCH_LEDGER.md`；升级冲突记录与验证。 |
| History | 追溯一条旧验收结果并判断其能否证明当前候选通过，同时给出当前状态检查路径。 | 将旧结果标为历史证据，不冒充当前验证；指出当前任务来源、候选和待办/限制的核验来源；未知事实如实列出。 | 若引用历史裁决，须保留其冻结口径和数值；如任务未提供当前候选则明确未知。 | 当前任务路由页与决策索引。 | `docs/agents/task-routing.md` 停止条件；任务 spec/issue；相关 dated evidence 与当前 candidate state。 |

说明：上表含 11 个锚定场景，因为 Chat 被拆成 submit、SDK merge、Gateway、embedded 四条独立行为路径；正式实验仍是题目规定的八个任务域 UI、Chat、Knowledge、Permissions、Tests、Runtime、Upstream、History。每个 Chat 题面明确只选一条主路径，必要时再声明跨路径影响。不得把某条路径的答案套用于其他路径。

## 独立评分、裁决与校准样例

评分者 A、B 分别只查看同一冻结题面、候选快照、六字段答案和本协议，不查看对方决定、另一候选标签、运行耗时或成本。逐锚点记录决定与支持定位的候选证据。两人一致时冻结该结果；有分歧时，第三位裁决者独立检查原证据和双方理由，逐锚点作最终决定并说明依据。第三方不能引入新规则、外部知识或候选外资料。无法由冻结材料裁定时记 `unresolved`，新版门禁不得通过。

| 校准例 | 答案表达 | A/B 或裁决结论 |
| --- | --- | --- |
| 等价表达 | 题目要求 SDK 同 ID chunk 去重。答案写“same canonical message ID updates the existing message row and appends its chunk; a distinct ID creates a separate row”，没有逐字出现“dedup”。 | `met`。语义和证据相同即可；第三方若一人要求关键词、一人按语义通过，裁决去掉措辞偏好。 |
| 条件不适用 | UI 题只加纯展示组件，没有状态、生成文件或客户端交互；答案在 `relevant_decisions` 说明“无生成 registry/client-state 条件，故不适用”，并在 unknowns 确认题面未要求点击行为。 | 条件锚点 `not-applicable`，不算遗漏。若题面实际要求点击回调，则 client interaction 条件已触发，裁决为缺少必答。 |
| 辅助项漏写 | Knowledge 答案满足过滤先于分页、canonical visibility、服务端隐藏 provider binding 及 focused visibility test；没有提及 create endpoint。 | 必答全 `met` 时任务正确；create endpoint 若列辅助则记 auxiliary `missed`，不降总分。 |
| 严重遗漏 | Gateway 重复事件题建议每次收到 SSE 都 append 新消息，声称 UI 的 submit gate 会消除重复。 | Gateway event delivery 与 submit fence 混淆，破坏题目关键行为；必答 `missed` 且 critical error = 1，任务不正确。 |
| 不足以判适用 | 题面只说“修复聊天重复”，答案没说明是重复提交、SDK chunk、Gateway event 还是 embedded stream。 | 不猜测最方便的路径；task unknown 必答缺失，记 `missed`。若冻结题面自身没有指定路径，该任务题面应在正式冻结前修订，不进入计分。 |
| 历史误用 | 以旧报告的历史 PASS 或旧 scorer 的失败时钟作为当前候选的验证通过证据。 | 历史权威误用必答 miss；若因此宣称当前安全通过，记 critical error。旧报告中如实的冻结数值引用仍然有效。 |

校准在正式评分前完成：A/B 对所有样例分别评分并解释；只有规则理解达到一致、第三方对分歧可按本表稳定裁决，才冻结评分者。校准不得拿正式实验答案反向改锚点。锚点变更需新协议 ID、新样例和新冻结输入。

## 验证与状态记录

正式报告逐题列出必答、条件、辅助锚点分数及证据引用；分别报告 submitted、infrastructure failure、protocol failure、quota exhaustion、task timeout 和 wrong answer。缺失答案留在固定分母且不作语义评分。submission elapsed 从首次成功内容读取到已持久化答案；失败关闭时间另列。成本报告区分 Markdown、source/test/config、其他、重复返回与所有物理尝试；旧总 unique-byte 口径只用于旧轨。

开始新版正式会话前，完成工具验证、八题非评分 pilot、A/B 校准、文档治理、夹具自检和证据归档恢复。具体新版成本与旧轨门槛以 recovery spec 为准；本协议不修改旧评分或冻结门槛。
