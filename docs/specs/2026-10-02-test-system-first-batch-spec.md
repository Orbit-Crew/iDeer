---
triage: ready-for-agent
---

# 测试体系首批改进

## Problem Statement

维护者目前无法仅凭 Test Lane 的结果记录可靠判断一次运行是否完成。Stagehand 缺少凭据时，控制台报告未执行，但证据 JSON 报告通过；证据收尾失败时，进程失败，耗时日志与元信息却仍报告成功。

Mock E2E 的历史运行存在疑似顺序依赖。相邻失败日志不足以确定污染来源，当前环境也尚未完成复现。直接修改测试或产品代码，可能掩盖实际缺陷。

三组测试重复执行相同断言，增加维护和运行成本。维护者需要删除明确冗余，同时保留行为覆盖、上游同步兼容性和可审计的替代关系。

## Solution

本批完成三类工作：修复两处结果记录错误；稳定复现并修复一项确认的 Mock E2E 顺序依赖根因；验证并清理三组明确冗余。

结果记录沿用现有 Test Lane 契约。诊断以当前候选的可重复失败为依据。删重保留上游原路径，并在迁移台账记录每项删除断言的保留位置。最终报告分别说明聚焦修复是否通过、标准通道是否通过，以及 Mock 全量是否仍有其他失败。

## User Stories

1. 作为维护者，我希望缺少可选凭据时显示未执行，以便不会将没有运行的测试当成通过。
2. 作为 CI 使用者，我希望缺少 Stagehand 凭据时保留现有退出码约定，以便这次修复不改变可选测试的流水线行为。
3. 作为维护者，我希望证据收尾失败使原本成功的运行返回失败，以便发现不完整的验证证据。
4. 作为排障人员，我希望测试本身的失败退出码不被证据错误覆盖，以便保留原失败原因。
5. 作为审阅者，我希望最终退出码、耗时日志、元信息和摘要一致，以便无需猜测哪份记录可信。
6. 作为审阅者，我希望未完成的证据明确保持未完成状态，以便不会得到伪造的成功结果。
7. 作为测试维护者，我希望拥有一条稳定触发顺序依赖的命令，以便修复有可靠的反馈循环。
8. 作为测试维护者，我希望区分单跑失败与前序污染，以便将问题归入正确类别。
9. 作为排障人员，我希望记录实际测试顺序和必要的请求轨迹，以便追踪污染如何进入目标测试。
10. 作为测试维护者，我希望 Mock 的注册、初始化和清理按确认的根因修复，以便测试保持相互独立。
11. 作为维护者，我希望修复后使用正常并发配置运行相关测试，以便诊断时的单 worker 设置不会成为永久绕过措施。
12. 作为审阅者，我希望其他 Mock 失败仍完整显示，以便首批修复不会掩盖后续工作。
13. 作为后端维护者，我希望只保留一份序列化断言，以便减少重复执行和双份维护。
14. 作为前端维护者，我希望线程初始化顺序只由一份等价测试验证，以便保留请求顺序覆盖并减少重复执行。
15. 作为前端维护者，我希望消息合并的重复断言由上游 Rstest 测试保留，以便减少本地副本。
16. 作为上游同步维护者，我希望优先保留上游原路径，以便后续合并不反复引入相同测试。
17. 作为审阅者，我希望每项删除都有等价或更强的保留断言，以便确认覆盖没有下降。
18. 作为实施者，我希望任务写明前置条件和验收标准，以便不会在基线失败或根因未明时执行删除和修复。
19. 作为维护者，我希望清单、覆盖矩阵和迁移记录与最终候选一致，以便后续验证能找到实际保留的测试。
20. 作为交付审阅者，我希望环境阻断、未执行和不完整运行单独报告，以便历史结果或局部通过不会替代当前验收。

## Implementation Decisions

- 修改现有 Test Lane runner 的最终结果处理，复用现有证据写入器，不增加公共字段或改变产品 API。
- 缺少 Stagehand 凭据时明确记录 `unexecuted`，保留退出码 0。先完成证据收尾并确定最终状态，再输出最终耗时、元信息和摘要。
- 测试成功但证据收尾失败时，最终退出码为 1；测试已失败时，保留原非零退出码，并额外报告证据错误。证据收尾失败不能产生已完成且通过的记录。
- 不要求写入器失败时仍生成一份完整 JSON。没有最终字段的证据属于不完整证据，其他最终输出必须反映真实退出状态。
- Mock 工作包含诊断和同一根因的修复，不承担全部历史失败。优先核查线程删除重试测试及其历史前序；探针不成立时再检查已登记的顺序依赖候选。
- 通过实际执行顺序、最小前序集合和状态或请求证据确认因果。目标单跑也失败时重新分类，不把它作为顺序依赖修复。
- 修复范围限于已确认的 Mock 注册、状态初始化或清理问题。若诊断指向产品行为，保留复现并单列产品修复方案，不在本批直接扩大实施范围。
- 保留序列化测试与线程初始化顺序测试的上游原路径，删除分类目录内的重复副本。消息合并保留上游 Rstest 文件，删除重复的本地 Vitest 文件；项目继续保留两个框架。
- 删除前逐项核对断言、夹具、标记、导入解析和执行环境。发现独有覆盖时保留该断言，本组删除暂缓，不能以静态相似度代替行为等价。
- 同步覆盖矩阵、迁移台账和测试清单。消息合并相关冲突台账追加删重说明，保留原合并历史。结果契约修复写入运行手册。
- 实施前按仓库规则刷新必要的 GitNexus 索引并执行影响分析；高风险影响需先报告。每个修复切片使用聚焦回归和最窄静态检查。

### 任务依赖与完成条件

| 任务 | 前置条件 | 完成条件 |
| --- | --- | --- |
| T1：结果记录修复 | 无 | 两处旧错误由回归测试证明；修复后结果契约通过 |
| T2：顺序依赖诊断 | 同一环境的浏览器预检通过 | 单跑通过、指定前序后失败；保存稳定命令、实际顺序与根因证据 |
| T3：同一根因修复 | T1、T2 | 原复现连续 5 次通过；相关测试使用正常配置通过 |
| T4：序列化删重 | T1、成对基线通过 | 保留 13 项测试通过；删除的全部断言有对应项 |
| T5：初始化顺序删重 | T1、浏览器预检、成对基线通过 | 保留测试通过；请求顺序断言完整保留 |
| T6：消息合并删重 | T1、两个框架的聚焦基线通过 | 保留 Rstest 文件全部测试；删除的 9 项断言均有对应项 |
| T7：记录和整体验证 | T3、T4、T5、T6 | 清单与记录更新；最终候选的标准和 Mock 全量结果完整报告 |

T2 的探索可以与 T1 并行，T4、T6 不等待 Mock 根因定位。若 T5 基线受同一根因影响，T5 也依赖 T3。T2 没有取得稳定复现时记录未完成，T3 保持阻塞；不得将诊断不成立当作修复完成。

## Testing Decisions

### 测试边界与先例

沿用前序计划确定的现有测试边界：runner 子进程、Playwright 浏览器测试、序列化与消息合并的公开函数。不存在一个能同时覆盖这三类行为的有效边界，本批不增加产品重置 API 或新的公共测试接口。

- runner 以外部可见行为为断言：进程退出码、标准输出、元信息、证据 JSON 和 CI 摘要。沿用现有 lane 分片测试的子进程装配及证据写入器测试先例，不直接断言 shell 内部变量。
- Mock E2E 通过页面行为和必要的 HTTP 请求验证隔离与重试。复用现有 Mock 工具和 Playwright 上下文，不能仅凭内部缓存清空就宣告成功。
- 删重以同样的输入、断言及执行语义为依据。保留完整断言，不增加 skip、放宽预期、缩小正式 lane 范围或通过重试消除失败。

### T1：结果记录复现与验收

在 `backend/` 新增 runner 子进程回归测试，聚焦命令为：

```bash
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests \
uv run --no-sync pytest tests/unit/scripts/test_run_test_lane.py -q
```

回归覆盖四种场景：缺少 Stagehand 凭据、测试成功但证据收尾失败、测试失败且证据收尾失败、正常成功。故障注入只在测试子进程内模拟证据完成命令失败和基础测试命令结果，保留真实证据初始化过程。

每个缺陷先验证旧实现失败，再做最小修复并验证通过。缺少凭据的验收为退出码 0 且 JSON 的 `outcome=unexecuted`。证据错误的验收为最终状态一致且没有完成的成功证据。

### T2、T3：Mock E2E 诊断命令

首先在仓库根目录通过预检：

```bash
python3 scripts/test_preflight.py frontend-mock-e2e
```

以下探针在 `frontend/` 执行，使用锁定的 pnpm 版本、干净的新服务和一致的依赖环境：

```bash
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test \
tests/e2e/thread-delete-confirm.spec.ts \
-g 'cleanup failure keeps active chat deletion retryable after the row disappears' \
--workers=1 --retries=0 --repeat-each=5 --trace=retain-on-failure
```

```bash
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test \
tests/e2e/thread-delete-confirm.spec.ts \
-g 'confirmation waits for deletion, prevents dismissal, and permits retry after failure|cleanup failure keeps active chat deletion retryable after the row disappears' \
--workers=1 --retries=0 --repeat-each=5 --trace=retain-on-failure
```

这两个命令是初始探针，不是已确认的复现。必须核对实际顺序；`--repeat-each` 不能保证前序与目标逐对交替执行。必要时使用仅供诊断的固定顺序装配，并将最终稳定失败命令记录为修复的回归入口。

首个探针不成立时，依据历史日志检查 settings model sync、thread archive/history/delete、skill export、settings sync、sidebar 的已登记候选，保持原顺序并缩减前序集合。记录每个探针结果，不循环运行完整套件来代替定位。

验收要求修复前存在稳定失败，修复后同一复现连续 5 次通过，相关测试使用正式配置通过。诊断使用单 worker，正式配置保持不变。轨迹仅保存必要请求信息，不复制凭据或认证头。

### T4、T5、T6：删重基线与保留验证

| 任务 | 保留 | 删除 |
| --- | --- | --- |
| T4 | `backend/tests/test_serialize_message_content.py` | `backend/tests/unit/runtime/test_serialize_message_content.py` |
| T5 | `frontend/tests/e2e/chat-thread-init-ordering.spec.ts` | `frontend/tests/e2e/workflows/chat-thread-init-ordering.spec.ts` |
| T6 | `frontend/tests/unit/core/threads/message-merge.test.ts` | `frontend/tests/unit/core/threads/message-merge-local.test.ts` |

T4 在 `backend/` 合跑两份文件，删除后仅传入保留文件：

```bash
UV_CACHE_DIR=/tmp/deer-flow-uv-cache PYTHONPATH=.:tests \
uv run --no-sync pytest tests/test_serialize_message_content.py \
tests/unit/runtime/test_serialize_message_content.py -q
```

成对基线已取得 26 passed，保留验证预期 13 passed。候选或环境改变后重新取得受影响的基线。

T5 在 `frontend/` 先向以下命令追加 `--list` 核对收集，再实际运行；删除后仅传入保留文件：

```bash
CI=1 PLAYWRIGHT_DEV_SERVER=1 pnpm exec playwright test \
tests/e2e/chat-thread-init-ordering.spec.ts \
tests/e2e/workflows/chat-thread-init-ordering.spec.ts \
--project=chromium --retries=0
```

预期由两项等价测试减少为一项，请求顺序及延迟相关断言完整保留。

T6 在 `frontend/` 分别取得两个框架的聚焦基线：

```bash
pnpm exec rstest run tests/unit/core/threads/message-merge.test.ts
```

```bash
pnpm exec vitest run \
tests/unit/core/threads/message-merge-local.test.ts \
--pool=forks --no-file-parallelism --maxWorkers=2 \
--testTimeout=5000 --hookTimeout=5000
```

删除后再次运行保留的 Rstest 文件。保留文件全部测试及参数化案例，验收使用框架的实际收集结果，不以源码中的调用数量替代运行数量。

### T7：最终验证与报告

在最终候选上执行：

```bash
python3 scripts/test_inventory.py --collect --json
UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard
bash scripts/run-test-lane.sh frontend-mock-e2e
```

`pr-standard` 在准备交付本批变更时完整运行一次，替代其包含的基础 lane。Mock 全量单独运行一次，用于检查顺序依赖修复的范围和其他失败。本批没有完整交付验收请求，不运行 `core-full`。

报告区分聚焦、标准通道及 PR 通道结果。列出 `pr-standard` 各子 lane 最终摘要与父 lane 的 `TEST_LANE_DURATION` 状态。Mock 全量的其他失败逐项登记，不能将目标根因修复表述为全量通过。

挂起、超时或缺少最终摘要时记录 `incomplete`，附完整命令、耗时和最后观察到的测试。环境不允许 socket 或浏览器时记录环境阻断，并在允许的环境运行相同命令；不修改产品或测试来绕过限制。

## Out of Scope

- 全部历史 Mock E2E 失败的修复。
- 测试通道规则的全面整合、网关夹具的大规模重构。
- 其他同名或静态相似测试的批量删除。
- Vitest 与 Rstest 的整体迁移或统一。
- 未经诊断确认的产品行为修改、公共重置接口、新的证据字段及超时策略重设计。
- `core-full` 交付验收与 GitHub Issue 发布。

## Further Notes

- 本规格来自已确认的首批计划。用户选择修复已确认的同一根因，并优先保留上游原路径。
- 探索基准为 `develop@5c513ed0ac07438be6001b6bbf7233421c62254c`。两处结果错误已经复现；Mock 当前候选的复现和根因尚未确认。
- 当前受限环境的 Mock 预检未通过，允许 socket 的另一执行环境也未通过 Playwright 依赖检查。`UV_CACHE_DIR=/tmp/deer-flow-uv-cache make doctor` 已通过，但不能替代浏览器预检或测试验收。
- 术语沿用 `CONTEXT.md` 的 Test Lane；运行状态沿用测试通道运行手册。没有新增领域概念或需要单独 ADR 的产品接口决策。
- 测试政策见 `docs/testing/test-lane-runbook.md`，覆盖关系见 `docs/testing/coverage-matrix.md`，删除记录见 `docs/testing/test-migration-ledger.md`。任务拆分时读取这些当前文件，不使用历史运行作为当前候选的验收结果。
- 按 `docs/agents/issue-tracker.md`，本规格文件即本地发布物；后续任务由 `to-tickets` 拆分至本地工作票据。
