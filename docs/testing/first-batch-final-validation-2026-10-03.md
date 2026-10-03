# 首批测试体系改进：最终候选验证记录

**状态：incomplete。** T7 的收集、PR 标准 lane 与 Mock 全量均已执行并记录；首批不能宣告完成，因为 T3 仍 blocked。Mock lane 中目标删除重试用例再次失败，而原诊断没有稳定复现及因果证据。本记录将这个结果与其余 Mock 失败分开，不推断根因。

## 候选与工作树

- 仓库：`/home/neowyh/code/AgentPlatform/.worktrees/test-system-first-batch`
- 分支：`fix/test-system-first-batch`
- 本票固定审查基准 / 被验证候选：`a4d564ae5e3adf1118feabc7a5e25ec00084d2f5`
- 最终候选测试之前的六个批次提交（由旧至新）：
  `a1bb73af` 规格；`0f509e95` runner 结果记录；`4a2b2c2` Mock 诊断记录；`83eaecb` T3 blocked 记录；`1750fe5` 后端序列化删重；`df669c6` 线程初始化删重；`a4d564a` 消息合并删重。此处列出七个 SHA：第一个是规格基点，后六个是后续批次提交；T7 的报告提交另计。
- 当前计划状态：01/04/05/06 complete，02 incomplete，03 blocked，07 incomplete。01 的收尾阶段聚焦 runner 4 passed / 20.74s、证据 writer 4 passed / 6.26s；早期 T1 记录中的 19.56s / 5.58s 是另一阶段运行，不与此合并。04/05/06 的聚焦证据分别见迁移台账及相应票据；其成功历史结果不替代本候选 PR 与 Mock 运行。
- `backend/uv.lock` SHA-256 `c4f73e16090624966e694447a5bb916658c1bb2986e886d0326eeee950a11d3c`；`frontend/pnpm-lock.yaml` `849a445b1984f4eea0a68ca3ce210885f595ed36c8892447d001d5a4bb42a866`；runner `f94e6449f559736ae3c423946f670a003fd7c99c36947035eaa039ccd24e59cb`；Playwright 配置 `ac28d626b212577e6f674ca7d5c67a14ddfe531c07f60c4575363d809dc3a182`。
- 运行环境为 Python 3.13.2、uv 0.12.9、Node v22.23.2、pnpm 10.26.2 与缓存中的 Playwright Chromium。后端依赖由 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache uv sync --locked` 安装，前端由 `pnpm install --frozen-lockfile` 安装，虚拟环境与 node_modules 均独立。配置从示例生成，仅添加指向 `127.0.0.1:9/v1` 的离线模型占位，无真实凭据；config.yaml SHA-256 为 `89516072f7ee914e7caafcf50fe96e41c128d1f1d7f6d1664288248721dc2098`，frontend/.env 为 `b0dae7d39a2134a6459986bbadb9801b3d307fe354547a58577457e67fb36184`。Doctor 退出 0，Ready，3 warnings。受限沙箱第一次启动在浏览器和本地 socket 预检处被拒；按手册在允许 Chromium 与 loopback socket 的执行环境以相同命令重跑。测试期间记录到代理尝试连接 `127.0.0.1:8001` 被拒；此日志不等同于 lane 环境阻断，具体测试退出结果见下文。

## 清单

命令：`python3 scripts/test_inventory.py --collect --json`（JSON 写至会话临时文件）。退出码 0；清单命令的独立墙钟耗时未保存，明确记为 unavailable；1,900 条目，1,235 已由框架收集，655 static-only，0 collection-error。Lane 归属：backend-blocking-io 47、backend-standard 1,186、backend-llm 4、backend-serial 9、backend-live 5、backend-external 1、frontend-a11y 1、frontend-mock-e2e 68、frontend-auth 4、frontend-real 14、frontend-stagehand 3、frontend-visual 6、frontend-record 1、frontend-standard 538、local-runtime 20。收集是静态/框架发现，不代表全部执行。

## PR 标准 lane

受限执行环境首次尝试的完整命令为 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard`。预检因 Chromium `Target page, context or browser has been closed` 和 socket `[Errno 1] Operation not permitted` 退出 1，耗时约 2 秒；测试未启动，归类为环境受限尝试。

随后在允许浏览器子进程及本地 socket 的执行环境，以同一命令完成一次全 lane。真实 shell exit 0，墙钟 4,031 秒，父项 `TEST_LANE_DURATION lane=pr-standard seconds=4031 status=0`。

| 子 lane | 最终结果 | Lane 计时 |
| --- | --- | --- |
| local-runtime | exit 0 | `seconds=10 status=0` |
| backend-standard | 29,240 passed，236 skipped，1,254 warnings | `seconds=2939 status=0` |
| frontend-standard / Rstest | 168 files，1,282 passed，0 failed | 包含于 frontend-standard |
| frontend-standard / Vitest | 370 files，10,697 passed | `seconds=775 status=0` |
| frontend-smoke | 34 passed | `seconds=303 status=0` |

Frontend-standard 子汇总由组合 lane 输出：Vitest 耗时 588.86s；Rstest JSON summary 为 168 files / 1,282 tests passed，框架总计 129.375s。smoke 与 Mock 运行期间均有代理 `ECONNREFUSED 127.0.0.1:8001` 日志；PR 的所有子 lane 与父 lane 仍以 status 0 完成。此 lane 未包含 backend-serial、auth/real/visual/a11y/stagehand、blocking-io、backend-live/llm/external 等专项通道，本票未单独运行它们，也未运行 `core-full`。

Playwright 命令没有显式设置 `CI` 或 retry 参数；本次完整输出没有可确认的重试记录，因此不报告重试次数，也不从配置默认值推断本次实际重试。原始会话日志位于本机 `/tmp/t07-pr-standard-allowed.log`，不随版本控制交付。

## Mock 全量

命令：`bash scripts/run-test-lane.sh frontend-mock-e2e`，在允许浏览器及本地 socket 的执行环境运行；preflight ready，Chromium launch ready，local socket bind ready。实际输出 `Running 413 tests using 1 worker`，收集并运行 413 项；最终 358 passed、55 failed。框架显示约 25.6 分钟；真实 shell exit 1，父项 `TEST_LANE_DURATION lane=frontend-mock-e2e seconds=1683 status=1`。因此该 lane **failed**，不是 incomplete。测试超时案例有明确最终失败摘要，也按 failed 记录，不按 lane 不完整处理。未设置 `CI` / retry 参数，本次输出未证明发生重试。

运行期间代理日志多次出现 `ECONNREFUSED 127.0.0.1:8001`。本记录只登记观察，不把它推断为 55 项失败的共同原因。完整会话日志曾保存在本机 `/tmp/t07-frontend-mock-e2e-allowed.log`；逐项失败身份如下：

1. `tests/e2e/agent-chat.spec.ts:53:3` — mobile agent welcome keeps the sidebar trigger clickable
2. `tests/e2e/agent-chat.spec.ts:101:3` — keeps new-chat drafts isolated between agents
3. `tests/e2e/agent-chat.spec.ts:518:3` — display name length counts emoji as code points
4. `tests/e2e/agent-chat.spec.ts:556:3` — Unicode display names keep the stable agent route and run context
5. `tests/e2e/agent-chat.spec.ts:613:5` — expert tab shows skill badges with empty tool groups
6. `tests/e2e/agent-chat.spec.ts:613:5` — expert tab shows skill badges with unrestricted tool groups
7. `tests/e2e/artifact-batched-stream.spec.ts:150:1` — assembles streamed write-file argument deltas in the artifact preview
8. `tests/e2e/artifact-preview.spec.ts:389:3` — restores the artifact panel and selected file after a page refresh
9. `tests/e2e/artifact-table-preview.spec.ts:192:1` — previews an unsaved draft and preserves it after a save conflict
10. `tests/e2e/capability-center.spec.ts:101:1` — catalog navigation, search, details, and migrated settings
11. `tests/e2e/capability-center.spec.ts:159:1` — the skills catalog fits a mobile viewport
12. `tests/e2e/capability-center.spec.ts:178:1` — MCP access errors preserve the independently available Lark integration
13. `tests/e2e/capability-center.spec.ts:197:1` — Community search gives feedback and clearing it restores import guidance
14. `tests/e2e/capability-center.spec.ts:227:1` — plugin filters remain usable after an MCP refetch fails
15. `tests/e2e/chat.spec.ts:47:3` — switching conversations during goal preparation drops the stale continuation
16. `tests/e2e/chat.spec.ts:99:3` — dropping the project scope mid-submission resets the thread identity
17. `tests/e2e/chat.spec.ts:158:3` — edits and reruns only the latest question in a regular chat
18. `tests/e2e/chat.spec.ts:1179:3` — goal command assigns the project before saving the goal
19. `tests/e2e/chat.spec.ts:1386:3` — blocks suggestion template placeholders until replaced
20. `tests/e2e/integrations.spec.ts:39:3` — opens the Lark plugin from a capability deep link
21. `tests/e2e/integrations.spec.ts:51:3` — hides the integrations entry in a deployment without the Lark CLI
22. `tests/e2e/integrations.spec.ts:84:3` — falls back when copying a Lark authorization link without the Clipboard API
23. `tests/e2e/integrations.spec.ts:177:3` — closes the plugin dialog before opening general settings
24. `tests/e2e/integrations.spec.ts:213:3` — can install the Lark integration skill pack from the capability center
25. `tests/e2e/integrations.spec.ts:333:3` — can switch the Lark app by entering new credentials
26. `tests/e2e/integrations.spec.ts:446:3` — keeps selected permissions when re-registering the Lark app
27. `tests/e2e/model-favorites.spec.ts:144:1` — favorites a model without selecting it and persists the choice after refresh
28. `tests/e2e/model-favorites.spec.ts:210:1` — synchronizes favorite additions and removals across real tabs
29. `tests/e2e/model-favorites.spec.ts:237:1` — shows main-chat favorites in the side chat without changing its current model
30. `tests/e2e/model-favorites.spec.ts:283:1` — restores a temporarily unavailable favorite and keeps the narrow picker usable
31. `tests/e2e/settings-model-sync.spec.ts:7:5` — normal thread effort selection preserves the account model
32. `tests/e2e/settings-model-sync.spec.ts:7:5` — normal thread mode selection preserves the account model
33. `tests/e2e/settings-model-sync.spec.ts:7:5` — agent thread effort selection preserves the account model
34. `tests/e2e/settings-model-sync.spec.ts:7:5` — agent thread mode selection preserves the account model
35. `tests/e2e/settings-model-sync.spec.ts:131:1` — custom agent automatic default does not become an account preference
36. `tests/e2e/settings-model-sync.spec.ts:229:1` — automatic model fallback cannot overwrite a slowly loaded account preference
37. `tests/e2e/settings-sync.spec.ts:5:1` — account notification setting survives clearing browser storage
38. `tests/e2e/sidebar.spec.ts:109:3` — mobile welcome layout stays within viewport and desktop sidebar shows the entries
39. `tests/e2e/sidecar-chat.spec.ts:1141:3` — opens restored side chat history without animated scroll
40. `tests/e2e/skill-export.spec.ts:22:1` — custom export previews, handles stale content and downloads only after refresh
41. `tests/e2e/skill-export.spec.ts:111:1` — mobile manifest blockers are readable and cannot download
42. `tests/e2e/thread-archive.spec.ts:8:1` — archive keeps the open conversation, supports undo and restores from the archive
43. `tests/e2e/thread-archive.spec.ts:108:1` — active list includes legacy chats beyond a full page of archived chats
44. `tests/e2e/thread-archive.spec.ts:142:3` — archived default chat can be restored from its mobile header
45. `tests/e2e/thread-archive.spec.ts:142:3` — archived custom agent chat can be restored from its mobile header
46. `tests/e2e/thread-delete-confirm.spec.ts:121:3` — cleanup failure keeps active chat deletion retryable after the row disappears
47. `tests/e2e/thread-history.spec.ts:222:3` — keeps rendered messages ordered when the latest history page advances
48. `tests/e2e/thread-history.spec.ts:715:3` — retrying deletion of the active newly created chat returns to the new chat screen
49. `tests/e2e/thread-ordering.spec.ts:279:3` — a live compaction during submit keeps history order and appends the new turn
50. `tests/e2e/workflows/agent-management.spec.ts:34:5` — gallery page loads and shows agent cards
51. `tests/e2e/workflows/agent-management.spec.ts:44:5` — gallery shows New Agent and Import buttons
52. `tests/e2e/workflows/artifact-visualization.spec.ts:76:3` — renders fault_tree.json as a graph preview with code fallback
53. `tests/e2e/workflows/cross-feature-contracts.spec.ts:49:1` — shared mock fixture preserves agent workflow memory and skill contracts
54. `tests/e2e/workflows/sandbox-management.spec.ts:49:3` — agent chat page renders without sandbox errors
55. `tests/e2e/workflows/workflow-management.spec.ts:57:5` — existing workflow can be opened, edited, saved, and run (test's explicit 120-second timeout)

第 47 项 history 排序目标在 T2 的 dev-server 单跑及缩减前序下曾通过，而本次全量失败于 `getByText(followUpPrompt)` 命中两个元素的 strict mode violation。本次正式 lane 使用 production webServer，T2 探针显式使用 `CI=1 PLAYWRIGHT_DEV_SERVER=1`；前序范围和服务模式均不同，尚未分离这两个变量，因此该差异只能登记为后续诊断线索。下一步应在相同服务模式、配置和环境下先核对单跑，再以本次实际前序缩减，不能直接称为已确认顺序依赖。

第 46 项就是 T3 初始探针目标；其在此完整 lane 失败进一步说明 T3 仍未完成。没有据此猜测修复原因，也没有修改测试、配置、并发度、重试数或 lane 范围。没有 `core-full` 运行。

收尾静态检查：`python3 scripts/sync_agent_guidance.py --check` 退出 0，28 对指导文件一致；`git diff --check a1bb73afe..HEAD` 退出 0。Next dev 自动追加的指导片段已恢复，最终未提交指导文件改动。

## 审查及图谱记录

双轴审查以 `a4d564ae5e3adf1118feabc7a5e25ec00084d2f5` 为固定基准，覆盖本报告和本票状态变更。审查结果见下方。主会话在暂存两个新文档后两次执行 `node .gitnexus/run.cjs detect-changes --scope all --repo /home/neowyh/code/AgentPlatform/.worktrees/test-system-first-batch`，均退出 0、输出 `No changes detected`，没有 partial/truncated 标记。但实际 staged diff 明确为两个新增文档，因此这表示新文档未映射，不能解释成无变化或图谱完整覆盖。独立检查确认只含最终报告与主会话复盘，没有函数、类或方法变更；`git diff --cached --check` 通过。已知此工作树的图谱提交点落后固定基准一个提交；此前 `detect_changes` 若显示删除映射 `UNKNOWN`、partial 或 truncated，必须原样保留该边界，不能将零调用方解释为无影响。T7 只增加验证文档和票据状态，不修改实现符号。

### 双轴审查

- **Standards：** 无发现。审查确认报告记录了候选、准确 lane 结果、子 lane 汇总、受限环境尝试、未运行的专项通道和完整 Mock 失败列表，并区分 failed、incomplete 与环境阻断。
- **Spec：** 原审阅受使用额度限制中断，主会话补做的独立规格审阅无发现。逐项核对原始日志与报告的 55 项失败清单，确认首批保持 incomplete、T3 blocked、history 环境差异仅作线索，复盘仅为建议。
- 主会话另起独立 Standards 审阅，覆盖补充后的最终报告与复盘，无发现。两轴均未重跑 lane。

## 最终判定

PR 标准候选通过，Mock 全量失败，T3 目标失败；首批状态保持 incomplete，待 T3 获得可重复诊断及根因修复证据后重新评估。此结论不覆盖未执行的专项 lane，也不将历史聚焦结果替代当前候选验证。

## 主会话复盘

见 [本次复盘](first-batch-retrospective-2026-10-03.md)。建议仅作为后续环境与工作流改进输入，本批没有实现新的产品接口、Mock 重置 API 或通道策略。
