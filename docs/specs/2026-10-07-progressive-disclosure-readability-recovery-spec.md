---
id: docs-specs-2026-10-07-progressive-disclosure-readability-recovery
kind: plan
status: draft
owner: repository maintainers
scope: five follow-up improvements to progressive document disclosure and a fresh reading-effect acceptance experiment
last-verified: 2026-10-07
verified-against: worktree @ 42ad60e6484294f7379f6524e3728a029458bbd5 with existing disclosure review corrections
triage: ready-for-agent
---

# 渐进式文档披露阅读效果修复规格

## Problem Statement

渐进式披露的工程基础已经建立，但阅读效果验收尚未通过。最近一轮主评分为 13/16 个 after 答案正确，常规任务的阅读字节中位数下降 23.55%，未达到 30% 门槛。Runtime 的两次回答和 Permissions 的一次回答没有准确找到已有入口。Runtime 读得少，源于停在根指引，不能据此认定阅读效率提高。

独立评分之间存在分歧。同一份答案可能因必答要求、条件性约束或证据解释不同而得到不同结论。评估过程中也出现过工具调用和提交问题。这些问题需要分别诊断，不能全部归因于文档，也不能靠调整评分放宽要求。

维护者需要五项可执行的后续改进，并用新的独立实验判断它们是否有效。旧评估及其一次纠偏已经结束，本规格不追加旧评估的纠偏次数，不追改历史成绩。

## Solution

先统一评分规则，再完善“读到哪里可以开始开发”的判断和重点任务入口，随后减少无关阅读，最后通过非计分试验及完整正式验收判断效果。

| 步骤 | 交付物 | 可观察的完成条件 |
| --- | --- | --- |
| 1. 统一评分 | 八类任务的锚点规则、独立评分与分歧裁决协议 | 必答、条件必答、可选项有证据依据；摘要由逐项记录计算；所有分歧有处理结果 |
| 2. 明确阅读停止条件 | 根指引到任务路由的衔接、可验证的就绪判据 | 读者能指出契约、代码入口、条件决策、验证入口与真实未知项；仅复述根指引不能通过 |
| 3. 改进重点首跳 | Runtime、Permissions 的具体任务指引 | 读者找到正确责任边界和首个验证入口，能区分普遍约束与条件约束 |
| 4. 降低无关阅读 | Chat、Permissions、Upstream 的章节入口及按条件展开规则 | 保留现行契约和历史追溯能力；阅读日志能解释减少了哪些无关内容 |
| 5. 重新验收 | 非计分试验记录、冻结协议、32 个正式会话、审计与结论 | 满足下文全部正式门槛；失败时如实保留未完成状态 |

本规格已具备后续拆票所需的范围和验收条件。`ready-for-agent` 表示规格可用于拆票；`draft` 表示改进尚未实施和验收，不能用它替换当前工程契约。

## User Stories

1. As a coding agent, I want a clear route from root guidance to my task, so that I know what to read next.
2. As a coding agent, I want an explicit reading stopping rule, so that I can start verifying source without reading every document.
3. As a coding agent, I want the applicable current contract, so that I do not implement an obsolete proposal.
4. As a coding agent, I want a concrete code entry point, so that my first source inspection addresses the requested behavior.
5. As a coding agent, I want conditional constraints marked with their triggers, so that I read them when they apply.
6. As a coding agent, I want genuine unknowns distinguished from information I have not looked up, so that my handoff is accurate.
7. As a runtime developer, I want the Run and Thread lifecycle entry points, so that cancellation and restoration changes preserve their contracts.
8. As a runtime developer, I want the extension preference and patch obligations, so that I preserve upstream compatibility.
9. As a permissions developer, I want the authorization and visibility boundaries, so that resource changes use the current governance model.
10. As a permissions developer, I want local execution restrictions identified as conditional, so that I do not apply them to unrelated tasks.
11. As a chat developer, I want targeted submission and streaming references, so that I avoid reading unrelated runtime material.
12. As an upstream maintainer, I want per-conflict decision guidance, so that I preserve both local behavior and upstream fixes.
13. As a history reader, I want dated decisions linked to current authority, so that an old implementation claim does not become a current-status claim.
14. As a documentation maintainer, I want concise pointers with one authoritative source, so that summaries do not become competing contracts.
15. As an evaluator, I want complete tool instructions before timing begins, so that CLI discovery does not distort reading measurements.
16. As an evaluator, I want a mechanically validated answer format, so that submission errors are distinguishable from wrong answers.
17. As a scorer, I want required, conditional and optional anchors, so that I do not penalize an irrelevant omission.
18. As a scorer, I want evidence-based semantic equivalence rules, so that correct answers need not match prescribed wording.
19. As a reviewer, I want independent grades and explicit adjudication, so that disagreement cannot disappear inside an average.
20. As a reviewer, I want summaries calculated from individual grades, so that reported pass counts can be checked.
21. As a maintainer, I want non-scored trials before freezing a candidate, so that tooling defects can be repaired without contaminating formal results.
22. As a maintainer, I want fresh comparable baseline and after sessions, so that model or protocol changes do not masquerade as document improvements.
23. As an auditor, I want candidate hashes and complete read events, so that I can reproduce the byte and timing calculations.
24. As an auditor, I want failed and interrupted attempts retained, so that retries do not hide poor outcomes.
25. As a project owner, I want all original acceptance thresholds preserved, so that completion means the agreed result was achieved.
26. As a project owner, I want limitations and remaining failures reported, so that I can distinguish a completed experiment from an accepted improvement.

## Implementation Decisions

### 工作顺序与边界

1. 步骤 1 先确定规则；步骤 2 与步骤 3 基于规则完善入口；步骤 4 在契约完整的前提下降低阅读成本；步骤 5 先试验，再冻结并正式验收。文档实现线性执行，不要求按工作树并行分票。评估会话可以并行，最多三个，受实际工具能力约束。
2. 复用现有阅读收集器、答案提交、审计和评分流程作为主要端到端验证入口。优先修复现有协议，不增加另一套评估系统。工具错误、评分歧义、导航失败分别记录原因和证据。
3. 保留现有八类任务和六项回答字段。八类任务为 UI、Chat、Knowledge、Permissions、Tests、Runtime、Upstream、History。字段为 entry、constraints、authorities、relevant_decisions、validation、unknowns。

### 步骤 1：评分规则与裁决

4. 为每类任务建立有编号的锚点表。每个锚点说明语义、候选中的权威依据、严重性及必答类别。条件必答项必须写明触发条件；可选项缺失不扣正确性。不能要求背诵固定措辞、穷举所有关联文档或陈述与任务无关的细节。
5. 两名独立评分者先用不参加正式验收的样例校准。样例覆盖同义正确表达、根指引泛答、真正未知、未查阅却声称未知、条件未触发、历史误用和危险建议。正式评分者不读取对方结论，并尽可能隐藏候选身份；无法隐藏的内容在报告中说明。
6. 每个正式答案保存逐锚点证据和初评分。分歧交给第三位裁决者，按冻结规则引用答案与候选证据作出结论。不能以平均分抵消错误。规则本身无法裁决时，本次结论为未完成或不通过；修订规则必须开启新的实验，不能只修订不利答案的标准。
7. 正确数、错误数、严重错误数、历史误用数和最终门槛结论从逐项记录自动生成。摘要与逐项记录不一致时拒绝生成通过结论。旧报告存在评分分歧，不能直接作为新规则的标准答案。

### 步骤 2：可观察的阅读停止条件

8. 复用任务路由已有的五项停止条件，改进其可发现性和执行效果。读者必须能给出适用的当前契约、具体代码入口、条件性决策、第一项验证及后续 lane、真实未知项。已从入口可查明的信息不能直接标记未知。
9. 根指引只保留通用规则和任务路由入口。领域细节按任务展开，历史材料只在追溯决策或处理兼容问题时读取。满足停止条件后转向源代码核验，不能把“找到文件名”当作“实现已验证”。
10. 收集器只验证回答结构和证据完整性，不向读者泄露评分锚点，不提供答案提示，也不因语义不完整而暗中要求重答。正式会话的错误答案原样进入评分。

### 步骤 3：Runtime 与 Permissions 首跳

11. Runtime 首跳区分取消、恢复及持久化等任务，指向实际入口和现行生命周期契约。说明 Run、Thread、流式事件、工具执行及状态恢复的相关不变量。保留 Extension、Adapter、登记最小运行时补丁的选择顺序，以及定制关闭和开启时的验证义务。
12. Permissions 首跳连接权限模型、角色与动作矩阵、授权检查、资源可见性和资源服务入口。区分应用侧治理真源与 Provider 基础设施职责。仅在涉及本地执行时展开本地执行否决约束。不得因此更改现行权限语义。
13. 每个首跳提供可操作的代码入口与验证入口，并明确条件触发点。维护者核对源码与当前权威后再编写摘要，不能根据旧评分反推一份迎合题目的答案。

### 步骤 4：减少无关阅读

14. 优先使用稳定章节链接、简短适用范围和条件展开。Chat 聚焦提交去重、流式状态与前后端责任边界；Permissions 聚焦授权与可见性；Upstream 聚焦路径归属、逐冲突行为判断、补丁登记和兼容验证。
15. 摘要说明必须遵守的约束并指向唯一权威，不复制完整契约，不删除历史决策证据，不修改受保护正文。历史文档明确当时的候选与当前状态入口。所有任务仍能追溯决策理由。
16. 成本分析分别展示根指引、任务路由、当前契约、源码和历史资料的读取成本，并单列受保护资料读取及重复读取。正式指标仍使用去重后的 UTF-8 字节，不能通过漏计搜索结果、隐藏强制阅读或删减必要约束降低成本。

### 步骤 5：试验、冻结与正式验收

17. 非计分试验至少覆盖 Runtime、Permissions、Chat、Upstream 和 History，各一次独立会话。另用通用样例检查工具调用和提交说明。试验用于发现问题，允许改文档和工具，所有结果均标为非正式，不能填入正式样本。
18. 进入正式阶段前，试验任务均须正确且没有严重错误或历史误用，工具审计通过，评分规则能裁决校准分歧，文档卫生检查通过。未满足时继续诊断；不得仅因字节下降就开始宣称改进有效。
19. 正式阶段冻结基线与 after 候选、任务提示、工具及配置摘要、评分规则、会话顺序和重试政策。保留原基线源码版本，但重新运行全部基线会话。基线与 after 使用同一可识别的模型版本和运行配置；若无法确定，报告可比性限制，不能宣称完成严格对照验收。
20. 正式运行八类任务、每类每候选两次，共 32 个独立会话。预先交错安排基线与 after。每个会话从干净上下文开始，只能访问对应候选，不得看到评分规则、另一候选、旧答案或其他会话。候选访问隔离需有工具限制和审计证据，不能仅依赖读者承诺。
21. 所有会话先完整读取候选根指引，再经收集器读取内容。统一提供完整 CLI 用法和回答格式。计时从第一次成功内容读取到答案提交，使用单调时钟。记录读取、搜索返回范围和提交事件；按文件内字节区间并集统计 UTF-8 阅读量。
22. 会话的墙钟超时值及中断判定须在正式运行前固定，对双方相同。基础设施或协议中断最多重试一次，并保留原尝试、原因和替代关联。错误答案与任务超时不能重抽。正式阶段需要额外人工提示或协议修正时保留污染标记，不能作为有效通过证据。
23. 最终通过同时要求：16 个 after 答案全部正确；严重错误为零；历史权威误用为零；常规五类任务的 10 个 after 会话耗时中位数不超过 300 秒；其去重阅读字节中位数相对基线对应 10 个会话下降至少 30%。下降率为一减 after 中位数除以 baseline 中位数。禁止改用各任务中位数的中位数，或只挑正确会话计算。
24. UI、Chat、Knowledge、Permissions、Tests 是常规五类。30% 是其合并样本门槛，不是每一类的单独门槛。仍需报告全部八类的正确性、耗时、字节数、分歧和失败原因，避免总体指标掩盖局部退步。
25. 每类两次只能支持本次固定条件下的验收，不足以证明跨模型的稳定提升。若增加重复次数，事先登记为补充实验，不替换正式样本。历史轮次保留原身份，新实验使用新编号。
26. 交付可跟踪的结论摘要、候选与工具摘要、逐项裁决及复算说明。原始记录保存在约定的会话产物位置，报告明确其访问位置和保留状态。若原始记录没有持久归档，必须说明其他干净检出无法单凭仓库复算原始读数，不能把哈希当成完整复现证据。
27. 正式失败时，报告哪些门槛失败并形成待办；不自动无限重跑，不降低门槛，不宣布总体改造完成。通过后更新项目状态，区分工程完成、阅读验收通过与尚存的外推限制。

## Testing Decisions

1. 沿用此前确认的测试边界：主要测试现有 collector CLI 到提交、审计、评分的外部行为，辅以独立语义评分及文档卫生检查。文档阅读质量不能由链接检查或单元测试代替。
2. 以已有收集器契约测试和自检为先例。工具行为变更按 TDD 逐项执行：先写一个失败的公开 CLI 回归场景，再做最小修复，运行该场景和最窄静态检查；不测试私有函数的组织方式。
3. 按实际变更覆盖 UTF-8 多字节、重叠读取去重、搜索返回内容计量、越界或跨候选读取拒绝、候选摘要变化、格式错误、提交未落盘、中断与重试关联。断言真实日志、退出状态和最终统计，不能只断言 mock 调用。
4. 评分测试覆盖必答遗漏、条件未触发、条件触发但遗漏、同义正确表述、历史误用和严重错误。加入逐项记录与总分不一致的拒绝场景。语义裁决由独立评审完成，自动校验只验证格式、计数与门槛计算。
5. 用固定合成记录验证 30% 和 300 秒的边界、偶数样本中位数、常规五类筛选及失败样本处理。工具不得把缺失正式会话解释为通过，正式分母固定为 16 个 after 答案。
6. 每个文档候选运行统一文档卫生门禁，包含元数据、链接、任务路由、指引镜像和受保护指纹。改根指引时先同步其镜像再检查；新增治理文件登记为基线之后的增补，不改变原基线清单和保护指纹。
7. 冻结后正式运行 32 个会话及独立评分、审计。报告既列出初评分歧，也列出最终裁决；完整性、正确性、耗时、字节门槛分别给结论。
8. 本次规格落地仅运行文档卫生门禁和差异检查。后续工具变更运行相关 CLI 契约测试；准备 PR 时遵循仓库适用 lane 合同，不能用阅读评估取代必要 PR 门禁。纯文档阅读验收不额外要求产品全量测试或交付级 lane。

## Out of Scope

- 修改产品功能、权限策略、API、Run 或 Thread 生命周期及现行兼容契约。
- 改写受保护正文，复制一套新的契约权威，或删除历史证据以减少读数。
- 降低原验收阈值、修改旧正式记录、用非计分样本替换失败样本。
- 本次直接实现五项改进、拆分实施票据或发布外部 tracker 内容。
- 在本规格中承诺跨模型、跨任务规模的统计稳定性。

## Further Notes

- 最新背景证据见[修复与阅读验收报告](../governance/disclosure-review-fixes-2026-10-06.md)。其中主评分 13/16 与阅读字节下降 23.55% 用于说明问题，不能充当新候选的成绩。评分分歧需按本规格逐项复核。
- 总体治理背景见[双轨治理规格](2026-10-04-doc-governance-dual-track-spec.md)，现行工作入口见[任务路由](../agents/task-routing.md)，状态见[项目现状](../project-state.md)。
- 正式基线源码为 `867f6709642854721f209a15e362d79a96b3b489`。新的 after 候选在实施与试验结束后冻结，本文件引用的当前 worktree 不是未来正式候选。
- 发布遵循[本地规格与工单约定](../agents/issue-tracker.md)及[triage 词汇](../agents/triage-labels.md)。后续使用 `to-tickets` 按上述依赖拆票，执行方式沿用用户确认的线性实现。
- 原始协议在本地 `.scratch/doc-reading-acceptance/spec.md`，总括待办在 `.scratch/doc-reading-acceptance/issues/04-followup-task-route-readability.md`，旧实验记录在 `dev-log/doc-reading-acceptance/`。这些目录被 Git 忽略；本规格自身包含开展新一轮工作的必要范围和门槛，不依赖这些私有文件才能理解。
