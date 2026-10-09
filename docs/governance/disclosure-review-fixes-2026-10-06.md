---
id: disclosure-review-fixes-2026-10-06
kind: evidence
status: current
owner: repository maintainers
scope: progressive disclosure review remediation on develop
---

# 渐进式文档披露审查修复记录

修复起点为 `develop @ 002b29878` 加本次未提交修复。期间 develop 更新至 `42ad60e64`，只新增独立的 upstream-merge 技能文件；本轮相关代码与测试未被该提交修改。本文记录本轮检查，不替代其他产品域验收。原始 59 票交付与后续补强均已合入 develop。

## 检查器修复

补充文档与基线文档执行相同的分类检查，包括元数据、正文链接、ID 唯一性、证据与 supersession。基线 inventory 及保护指纹仍单独核验，补充登记的快照哈希不转换为冻结约束。

`task_domains` 与 `task_routes` 登记九类任务的契约、代码和验证入口。检查器拒绝缺失配置、缺失或重复的域、空目标和空验证入口，并核对目标路径存在。`--revision` 只读取候选中的策略和文档。

TDD 记录：补充文档错误、缺失路由配置、缺域与缺指针三项 CLI 回归均先失败后通过。最终复核又补充 supplements 为 null 的兼容回归与重复任务域声明回归，同样先失败后通过。原有测试断言保留；当前聚焦测试为 53 passed。正文检查扩大后发现并补齐两个入口的元数据，修复配置文档指向 provisioner 配置节的坏锚点。对照 frontend/AGENTS.md 和源码后，聊天路由指针进一步区分页面接线、turn-submit 提交链与 hooks 流式状态，避免把页面接线当作提交生命周期入口。

## 状态说明与阅读评估

项目状态页原第 7 节的 299 findings 是改造中途结果。主交付和后续补强已完成，当前治理状态见本记录；第 1–6 节仍是原候选快照，未在本轮重新验证。

原阅读评估记录保留。其例行阅读量下降 52.7%，定位时间中位数从 91.5 秒增至 150 秒；不能将其描述为定位提速。原 `after-history-b` 误读了基线根指引，不能算作有效的隔离候选样本。

历史任务复测已完成，实际结果见下节。本记录不把旧候选的通过结果计入本轮验收。

## 首次 PR 检查

执行 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard`。受限环境预检的本地 socket 和 Chromium 启动失败；在允许这些操作的环境中完整执行，结果如下。

| 通道 | 实际结果 | TEST_LANE_DURATION |
| --- | --- | --- |
| local-runtime | 192 passed, 4 skipped | seconds=15 status=0 |
| backend-standard | 29395 passed, 236 skipped, 1 failed | seconds=1110 status=1 |
| frontend-standard | 373 files, 10778 tests passed | seconds=443 status=0 |
| frontend-smoke | 34 passed | seconds=89 status=0 |
| pr-standard | 父通道失败 | seconds=1666 status=1 |

后端唯一失败为 `tests/test_tool_error_handling_middleware.py::test_build_subagent_runtime_middlewares_threads_app_config_to_llm_middleware`，测试中复用的 FakeMiddleware 与既有 ToolReceiptMiddleware 顺序校验冲突。单独运行同一用例仍失败，耗时 3.81 秒；相关测试和中间件均无本次改动。该问题属于本次文档修复之外的后端缺陷，未改变断言或跳过用例。PR gate 尚未通过。

本地原始产物位于 `logs/test-lanes/pr-standard-20261006T104747Z-2475929/`，session 记录在 gitignored `dev-log/disclosure-review-fixes/`。本节的候选、命令和结果摘要保留在此跟踪文档中，原始日志用于复核。

## 历史任务隔离复测

串行执行同一任务的四次独立会话，基线与修复后各两次。任务原文为“追溯 Agent 命名及知识治理历史决策，判断哪些约束仍适用。”基线为 `867f67096` 的 git archive；修复后为 `002b29878` 的 archive 加本轮修复快照。评估者从各自候选的根 AGENTS.md 开始，不能读取评分规则、规格或其他会话。

读取器自动记录文件路径、行区间、UTF-8 字节数、完整文件 SHA-256 和实际用时。评分时逐条核对读取哈希与候选清单，并重算总字节和去重字节。四份记录均通过隔离和统计核对。两个候选完整清单的 SHA-256：

- 基线：`980e125108dcceb8625af3620e0c61514f6efa8d57400ccf9d31e52b17312848`
- 修复后：`164e1c662c9019f4ef075920bcc53a1ae0776003904247b64f9c40d5fa902c24`

| 会话 | 定位用时，秒 | 去重阅读字节 | 结果 |
| --- | --- | --- | --- |
| baseline-retry-1 | 115.734 | 88,508 | 当前约束与历史范围识别正确；未列后续开发测试入口 |
| baseline-2 | 134.044 | 85,136 | 当前约束与历史范围识别正确；未列后续开发测试入口 |
| after-1 | 143.500 | 142,983 | 当前约束、历史边界、标准 lane/PR 验证入口均正确 |
| after-2 | 64.684 | 114,215 | 当前约束、历史边界、标准 lane/PR 验证入口均正确 |

修复后关键答案错误为 0，误用历史记录作为当前权威为 0；两次定位均在 300 秒内。中位用时 124.889 → 104.092 秒；中位去重字节 86,822 → 128,599，增加约 48.1%。本轮历史任务没有证明阅读量下降；它不属于例行任务的 30% 减量阈值范围。样本每侧仅两次，不将时间差推广为整体提速。

原首个基线会话因额度限制中断，没有完成答案或计量，保留 incomplete 记录并以新的独立会话替代。after-1 的原答案文件末尾包含字面 `\n`；仅在标准化副本中移除该格式错误，原文件与哈希保留，答案内容未改。

原评估报告仍保留作历史记录，但其“32 份会话完整通过”的结论受候选污染影响，不作为完整验收证据。本轮四次复测不拼入旧模型/环境的整体统计。旧例行阅读量下降 52.7% 仍是原记录口径下的历史结果，其中估算和汇总不一致的局限保留；本轮不重新宣称该数值已被实测验证。

标准化记录、原始答案、读取事件、候选清单、评分结果与读取器保存在 gitignored `dev-log/disclosure-review-fixes/reading-evaluation/`。本页保存候选、协议、数值和判定摘要；原始产物用于逐项复核。

## 文档修复候选验收

第二次 PR 通道执行因规格复核补入重复域守卫而主动中止，不计入验收。第三次执行基于 `develop @ 42ad60e64` 加最终修复；执行期间八个改动文件的哈希与冻结清单一致。结束后仅更新本文结果与本文首次补充登记的哈希、行数，并重新执行文档检查。

执行命令仍为 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard`，实际结果如下。

| 通道 | 实际结果 | TEST_LANE_DURATION |
| --- | --- | --- |
| local-runtime | 192 passed, 4 skipped | seconds=19 status=0 |
| backend-standard | 29397 passed, 236 skipped, 1 failed | seconds=1137 status=1 |
| frontend-standard | 373 files, 10778 tests passed | seconds=480 status=0 |
| frontend-smoke | 34 passed | seconds=70 status=0 |
| pr-standard | 父通道失败 | seconds=1715 status=1 |

后端唯一失败为 `tests/unit/channels/test_feishu_channel.py::TestRunWs::test_run_ws_exception`。单独执行同一用例为 1 passed，耗时 6.23 秒，未复现整套运行的失败；相关代码和测试均无本次改动，根因尚未确定。首次运行的中间件失败用例在这次整套运行中通过。聚焦通过不替代失败的标准通道，PR gate 仍未通过；未修改断言、添加跳过或扩大本次修复范围。

最终通道产物位于 `logs/test-lanes/pr-standard-20261006T131422Z-2616722/`，原始日志为 gitignored `dev-log/disclosure-review-fixes/pr-standard-frozen.log`。53 个检查器测试在聚焦运行及最终后端通道中全部通过；聚焦运行耗时 4.33 秒。Ruff lint、format 检查通过。文档卫生三项检查通过：文档 findings 为 0、28 对指引镜像一致、67 项保护指纹无差异。`make doctor` 使用临时 UV 缓存后返回 Ready；未据此改变环境配置。

审查发现的四项文档问题及最终复核发现的 null 配置兼容、重复域声明问题均已修复。规格与工程规范复核未留下其他本次范围内的必要修复项。改动尚未提交；本记录不表示完整 PR 门禁通过，也不表示项目状态页第 1–6 节已重新验收。

## 飞书测试失败诊断与 TDD 修复

用户随后授权诊断并修复上述飞书失败。整套日志中的直接症状是 pytest 处理对象回收异常时抛出 `Failed to process unraisable exception`，其异常格式化过程中的模块导入被替换成 `RuntimeError: ws fail`。

根因是两个 WebSocket 异常测试用 `patch("builtins.__import__", side_effect=RuntimeError("ws fail"))` 模拟 SDK 失败，影响了同进程所有 Python 导入。当其他对象恰好在此期间被回收时，pytest 的异常处理也会失败。单独运行不触发相同时机，因此之前的聚焦通过未排除该问题。

诊断脚本在原失败用例的故障模拟生效期间强制回收一个会抛异常的对象，连续三次复现原症状，最后一次用时 6.01 秒。唯一改变为将模拟限制在 SDK 导入时，同一触发转为通过。正式回归通过 pytest 子进程执行原用例，并断言回收确实发生、pytest 返回成功；它覆盖实际的异常处理冲突，而不是依赖随机回收时机。

两次 TDD 切片分别针对运行中和已停止的用例：新增回归先失败，耗时分别为 11.01、9.12 秒；之后将故障模拟移到 SDK 的 `Client.start()`，不再替换全局导入。原用例增加运行中记录错误并停止、已停止时不误报错误的断言。产品代码未修改，原有覆盖未删除或跳过。

两项正式回归通过，耗时 15.53 秒；完整飞书文件 179 passed，耗时 19.61 秒。原诊断脚本再次执行为 1 passed，耗时 3.89 秒，回收触发仍为 True。相关 Ruff lint、format 检查通过；新增两个参数化节点已被测试 inventory 收集并归属 backend-standard。原始诊断、TDD 与验证日志保存于 gitignored `dev-log/feishu-diagnosis/`。

修复后的 backend-standard 已通过：29400 passed、236 skipped、1252 warnings，pytest 耗时 989.74 秒，`TEST_LANE_DURATION lane=backend-standard seconds=1047 status=0`。原失败用例和新增两个回归均在该通道中通过，两个测试文件在执行期间的哈希与冻结清单一致。命令为 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh backend-standard`。

上述 TDD 修复验收阶段只重跑了受影响的后端标准通道，当时尚未重新执行完整 pr-standard。用户随后要求完整复验，结果见下节。此前候选的失败记录保留，不改写为成功。

## 修复后的完整 PR 门禁复验

根据用户要求，对 `develop @ 42ad60e64` 加全部未提交修复执行 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard`。执行前保存十个改动文件的 SHA-256，结束时逐项核对，无差异。预检在允许本地 socket 和 Chromium 的环境中通过。

| 通道 | 实际结果 | TEST_LANE_DURATION |
| --- | --- | --- |
| local-runtime | 192 passed, 4 skipped | seconds=22 status=0 |
| backend-standard | 29400 passed, 236 skipped | seconds=1090 status=0 |
| frontend-standard | 373 files, 10778 tests passed | seconds=475 status=0 |
| frontend-smoke | 34 passed | seconds=69 status=0 |
| pr-standard | 完整门禁通过 | seconds=1664 status=0 |

后端 pytest 耗时 1021.47 秒，1256 warnings；原失败用例与新增两个回收冲突回归均通过。前端浏览器冒烟测试实际执行耗时 53.8 秒。上述表格记录 runner 的通道耗时，父通道耗时包含通道切换与证据收尾。

完整门禁原始日志为 gitignored `dev-log/feishu-diagnosis/pr-standard.log`，候选指纹为同目录的 `pr-candidate.json`，通道产物为 `logs/test-lanes/pr-standard-20261006T142803Z-2733767/`。结束后仅更新本文结果及本文首次补充登记的哈希、行数，并重新执行文档检查。当前候选的 PR 门禁已通过，修复与验收记录尚未提交。

## 渐进式披露阅读效果验收（2026-10-07）

按维护者批准的 8 类任务 × baseline/after × 每类 2 次执行了新一轮隔离阅读。第一轮完成 32 份正式会话；协议污染和未落盘尝试均保存在 `dev-log/doc-reading-acceptance/attempts/`，不计入正式样本。评分后触发唯一允许的定向文档修复：ADR-0007 的实现状态改为明确指向历史工作树，并把当前候选状态交给项目状态页；任务路由补充上游冲突偏好只是逐项行为/契约裁定的起点。随后冻结第二轮 after，并重跑全部 16 个 after 会话及 history/upstream 的 4 个 baseline 对照；其余 12 个未受影响 baseline 会话按原计划复用。两轮 rubric、prompt、模型和 collector 配置保持不变。

候选与工具指纹：第一轮 baseline `880de4d5491738a9f4eb676fa0959388f1cb3617b94bfdcbfe9ad7e05c19197d`、after `1abe035fc5a8ff27d1363d6565942d40ba7c2fb6bba0278cb418b78a39f80461`；修复轮 baseline 保持相同、after `25f6048d06ea0661237c2603e262bd8165e444e26f18efe9bf2d48ebe8cac1a2`。两轮 collector SHA-256 均为 `5fad20fff1556d8b9447349d4259b26ca043a679dc6b1a3014e7a80194311b4b`，tool-config SHA-256 均为 `c529f96f896e5397b12c2583f6c441b5fad9134fffbad7eccc6a74f3a1775160`。精确模型 ID 不可从编排接口读取，按 parent-inherited 记录。

| 轮次 | 正式会话 | after 答案正确 | after 严重错误 / 历史权威误用 | 常规任务时间中位数 | 常规任务唯一字节减少 | 判定 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 第一轮 | 32/32 | 14/16 | 2 / 1 | 35.10 秒 | 31.65% | 未通过 |
| 定向修复轮 | 32 个评分记录（16 个新 after、4 个新 baseline、12 个复用 baseline） | 13/16 | 0 / 0 | 33.42 秒 | 23.55% | 未通过 |

Baseline 控制组也暴露评分波动：第一轮主评分为 15/16 正确、0 严重错误、0 历史误用；修复轮主评分为 13/16、1、2。修复轮 12 条复用答案与第一轮字节完全相同，但重新评分后有差异。因此正确率数值存在评审一致性限制；无论采用哪份评分，after 全对门槛和修复轮字节削减门槛均未满足。

修复轮按任务的唯一读取字节、after 阅读时间、after 不正确答案数和受保护文件读取字节如下。median 取两次样本；protected 列顺序为 baseline/after。

| 任务 | baseline 字节中位数 | after 字节中位数 | after 秒中位数 | after 错答数 | protected 字节中位数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| UI | 45,028 | 31,166 | 21.05 | 0 | 0 / 0 |
| Chat | 51,152 | 81,169 | 44.32 | 0 | 3,621 / 21,135 |
| Knowledge | 64,046 | 31,710 | 41.38 | 0 | 1,109 / 0 |
| Permissions | 68,728 | 146,939 | 45.51 | 1 | 2,782 / 17,307 |
| Tests | 114,769 | 91,453 | 29.92 | 0 | 0 / 0 |
| Runtime | 296,310 | 16,183 | 33.88 | 2 | 62,845 / 0 |
| Upstream | 61,074 | 156,261 | 37.56 | 0 | 199 / 30,934 |
| History | 59,008 | 66,525 | 49.76 | 0 | 0 / 91 |

修复轮独立评分将两条 Runtime 和一条 Permissions after 答案判为不正确：它们没有充分利用已提供的任务路由来给出代码入口、授权责任边界和条件约束。第一轮的 history 与 upstream 误读在修复轮评分中通过。另有第二名盲评者对 after-only 会话给出 9/16 正确的结果，较主评分的 13/16 更严格，分歧集中在 knowledge、tests 和条件化约束是否足以开始工作；两份评分都低于全对门槛。该差异作为评分一致性限制保留，不把任一结果改写成通过。

因此本轮最终验收为**未通过**：修复轮的 routine 阅读时间达标，但唯一字节减少只有 23.55%，低于 30%；主评分也只有 13/16 after 答案正确。按已批准方案，本轮已用完唯一一次定向修复机会，不再扩大改造或降低阈值。若后续继续，应针对 task-routing 对 Runtime/Permissions 的触达与关键条件约束设计新规格和票据，再另行授权评估。

可复核产物均在 gitignored `dev-log/doc-reading-acceptance/`：第一轮 `queue.json`、`execution-order.json`、`sessions/`、`grades.json`、`audit-report.json`、`score-report.json`；修复轮对应文件位于 `round-2/`，其中还包括修复候选快照、manifest、复用 baseline 的旁注、主评分 `grades.json`、第二份独立 after-only 评分 `adjudication-after.json` 和无效尝试归档。首个未完成/污染的会话记录没有删除或计入成绩。
