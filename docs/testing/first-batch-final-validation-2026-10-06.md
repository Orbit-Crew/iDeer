# 首批测试体系改进（Mock E2E 恢复批）：最终候选验证记录（2026-10-06）

**状态：incomplete（扩展验收未全部通过）。** Mock E2E 恢复目标本身已达成：55 项原失败在生产模式、单 worker、零重试、repeat-each=5 下 275/275 全部通过，Mock 全量 413/413 通过，pnpm check 通过。但正式 pr-standard lane 失败：frontend-standard 子 lane 中 3 个页面单测文件共 93 项失败，全部可溯源至 03-D 产品改动与未同步更新的页面单测之间的冲突。按规格"不完整不得宣告完成"，本批整体判定为 incomplete。原始 03（顺序依赖根因修复）仍然合法地保持 blocked：不存在稳定的顺序依赖复现（T2 结论为未完成），本记录不推翻该状态。

配套复盘见 [首批复盘 2026-10-06](first-batch-retrospective-2026-10-06.md)；上一轮历史记录（不覆盖、不替代本记录）见 [最终验证 2026-10-03](first-batch-final-validation-2026-10-03.md)。

## 候选与工作树

- 仓库：`/home/neowyh/code/AgentPlatform/.worktrees/test-system-first-batch`；分支 `fix/test-system-first-batch`。
- 被验证候选（冻结 HEAD）：`d29911db4eff13f119f7af38009a162f02e418b3`（`d29911db4 docs(testing): resolve independent review notes on recovery evidence`）。所有验证运行期间未修改任何产品、测试或配置文件。
- 配置/依赖指纹（SHA-256，与 2026-10-03 记录一致，未变化）：`backend/uv.lock` `c4f73e16090624966e694447a5bb916658c1bb2986e886d0326eeee950a11d3c`；`frontend/pnpm-lock.yaml` `849a445b1984f4eea0a68ca3ce210885f595ed36c8892447d001d5a4bb42a866`；`frontend/playwright.config.ts` `ac28d626b212577e6f674ca7d5c67a14ddfe531c07f60c4575363d809dc3a182`；`scripts/run-test-lane.sh` `f94e6449f559736ae3c423946f670a003fd7c99c36947035eaa039ccd24e59cb`；`config.yaml` `89516072f7ee914e7caafcf50fe96e41c128d1f1d7f6d1664288248721dc2098`；`frontend/.env` `b0dae7d39a2134a6459986bbadb9801b3d307fe354547a58577457e67fb36184`。
- 运行环境：Python 3.13.2、uv 0.12.9、Node v22.23.2、pnpm 10.26.2、缓存内 Playwright Chromium。后端依赖由 `UV_CACHE_DIR=/tmp/deer-flow-uv-cache` 的独立 venv 提供，前端使用独立 node_modules。
- 生产服务器：root 所有，`http://127.0.0.1:3001`，BUILD_ID `3NEsFTLYAVrmRiBU9_CuV`（与 `frontend/.next/BUILD_ID` 一致），主页 HTTP 200；启动日志 `dev-log/root-production-server-07.log`。复现验收运行以 `PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001` 复用该服务器（A 组历史命令写的是 3000，本次按票据指示统一改指 3001 上运行的同一候选构建，选择器未变）。lane 各自启动自己的 production webServer（8001 Gateway 离线导致的代理 `ECONNREFUSED` 日志为预期现象，不作失败归因）。
- 沙箱处理：本会话所有需要浏览器/本地 socket 的命令（复现验收、lane、pnpm check）均在允许 Chromium 与 loopback socket 的执行环境中原样运行；未修改任何产品代码、测试或配置来绕过限制。

## 独立复审记录

由编排会话完成的两轴独立复审（以各票起始 HEAD 为固定基准），结果如下；无 BLOCKER/MAJOR 发现：

| 票 | 结论 |
| --- | --- |
| 03-A | PASS-WITH-NOTES |
| 03-B | PASS-WITH-NOTES |
| 03-C | PASS-WITH-NOTES（接受一项 MINOR：作为 C2 后果，对非本票分配的 `agent-management.spec.ts` 只读名称用例做了已披露的断言强化改写） |
| 03-E | PASS-WITH-NOTES |
| 03-F | PASS-WITH-NOTES |

文档层面的复审意见已在提交 `d29911db4` 中解决。

## GitNexus 门禁记录

由编排会话记录：

- 暂存文档修复门禁：3 files / 5 symbols / 0 processes / risk low。
- 全批 `detect-changes --scope compare --base-ref a1bb73afee6a0e3b1683deb1b326276fe3dda37f`：56 files / 151 symbols / 27 processes / risk critical，无 partial / truncated；变更集中于已做过影响分析的实施缝隙（ChatPage/AgentChatPage 线程 ID 解析、ResourceGallery、fromResource、AgentCard、ArtifactFileDetail）。

## 清单

命令：`python3 scripts/test_inventory.py --collect --json`（JSON：`dev-log/07-inventory.json`）。退出码 0；1,900 条目，1,235 已由框架收集，655 static-only，10 collection-skipped（均为可选依赖/凭据缺失，如 live、LLM key、coincurve），0 collection-error。frontend-mock-e2e lane 文件集 68 个；正式 lane 自身 Playwright 收集为 413 项（恢复批的 55 项为原位修复，未新增 E2E 文件；新增回归为单测层级，在 frontend-standard 中执行）。清单为静态/框架发现，不代表全部执行。

## pnpm check

命令：`pnpm check`（frontend/）。退出码 0；ESLint 0 errors、1,325 warnings（既有警告）；墙钟 77.24 秒（`dev-log/07-pnpm-check.log`）。

## 55 项原失败复现验收（生产模式）

每组使用其证据文档（docs/testing/mock-e2e-recovery-{A..F}.md）中的最终五次重复验收命令，统一前置 `CI=1 PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001`，从 frontend/ 运行；`--workers=1 --retries=0 --repeat-each=5` 保持不变。原始输出与退出码：`dev-log/07-repro-{A..F}.log` 与相邻 `.exit`。

| 组 | 命令摘要（组证据文档最终命令） | 选择数 | 结果 | 退出码 | 墙钟 |
| --- | --- | ---: | --- | ---: | ---: |
| A | capability-center + integrations + skill-export 三 spec，`--grep` 14 个精确标题，`--reporter=line --trace=retain-on-failure` | 70 | 70 passed，0 failed，0 flaky | 0 | 136.37s |
| B | model-favorites + settings-model-sync + settings-sync 三 spec，`--repeat-each=5 --reporter=line,json` | 55 | expected 55，unexpected 0，flaky 0，skipped 0（Playwright 123,864 ms） | 0 | 127.18s |
| C | agent-chat + 四个 workflows spec，`-g` 9 个标题，`--reporter=json` | 50 | expected 50，unexpected 0，flaky 0，skipped 0（Playwright 72,950 ms） | 0 | 74.86s |
| D | chat + sidecar-chat + thread-history/archive/delete-confirm/ordering 六 spec，`--grep` 13 个标题模式，`--reporter=line` | 70 | 70 passed，0 failed，0 flaky | 0 | 163.46s |
| E | artifact-batched-stream:150 + artifact-preview:389 + artifact-table-preview:192 + workflows/artifact-visualization:76，`--repeat-each=5` | 20 | 20 passed，0 failed | 0 | 63.40s |
| F | agent-chat + sidebar，`-g` 2 个标题，`--reporter=line` | 10 | 10 passed，0 failed | 0 | 22.31s |

合计：275 次选择执行（55 案例 × 5），全部通过，零重试、零 flaky、零 skip。

如实记录两项边界：

- #39、#47（03-D 组）没有已复现的根因。它们的原位用例未改动，其五次重复执行包含在 D 组 70/70 通过之内；处置按 docs/testing/mock-e2e-recovery-D.md 保持"当前候选未复现、不作因果断言、断言完整保留"。
- 03（顺序依赖根因修复）保持 blocked：T2 未取得稳定复现，本批全部证据均不支持任何顺序依赖断言，也未据此宣称修复。

## PR 标准 lane（正式，一次）

命令：仓库根目录 `CI=1 UV_CACHE_DIR=/tmp/deer-flow-uv-cache bash scripts/run-test-lane.sh pr-standard`（`dev-log/07-pr-standard.log`，退出码 `dev-log/07-pr-standard.exit`）。真实 shell 退出码 1，墙钟 3,402.83 秒；父项 `TEST_LANE_DURATION lane=pr-standard seconds=3403 status=1`。按指示未重跑任何子 lane。

| 子 lane | 最终结果 | Lane 计时 |
| --- | --- | --- |
| local-runtime | exit 0 | `seconds=8 status=0` |
| backend-standard | 29,240 passed，236 skipped，1,250 warnings（2,484.08s） | `seconds=2552 status=0` |
| frontend-standard / Rstest | 168 files passed，1,283 tests passed | 包含于 frontend-standard |
| frontend-standard / Vitest | **370 files：3 failed / 367 passed；10,700 tests：93 failed / 10,607 passed** | `seconds=696 status=1` |
| frontend-smoke | 34 passed | `seconds=144 status=0` |

frontend-standard 的 93 项失败集中在 3 个页面单测文件，逐文件列出（文件:标题数量过多，按文件与错误汇总；完整输出见 `dev-log/07-pr-standard.log`）：

1. `tests/unit/app/workspace/chats/[thread_id]/page.test.tsx` — 46 failed。错误：`TypeError: Cannot read properties of undefined (reading 'projectUnavailable')`，位置 `src/app/workspace/chats/[thread_id]/page.tsx:291`（`t.projects.projectUnavailable`）。该读取由 03-D 项目作用域提交修复（D1）引入，页面单测的 i18n mock 未提供 `projects.projectUnavailable`。
2. `tests/unit/app/workspace/chats/thread-page.test.tsx` — 9 failed。同一错误、同一位置。
3. `tests/unit/app/workspace/agents/[agent_name]/chats/[thread_id]/page.test.tsx` — 38 failed。错误：`Error: No QueryClient set, use QueryClientProvider to set one`，经由 `useArchiveThread`（`src/core/threads/archive.ts`）→ `useThreadArchiveAction` → `ThreadArchiveStatus`。该挂载由 03-D 归档恢复头控件修复（#44–45）引入，AgentChatPage 页面单测未提供 QueryClientProvider。

两项原因均为 03-D 产品改动（新增 toast 文案读取、新增依赖 react-query 的头控件）与未同步更新的页面单测之间的冲突；Mock E2E 与 smoke 中同一页面在完整 Provider 树下正常。按本票边界未修改任何测试或产品代码，该失败如实保留为剩余失败，交由后续票据以最小改动对齐（为页面单测补 Provider/翻译 mock 或等价的最小测试侧调整）。

## Mock 全量（正式，一次）

命令：仓库根目录 `CI=1 bash scripts/run-test-lane.sh frontend-mock-e2e`（`dev-log/07-mock-e2e-lane.log`，退出码 `.exit`）。预检 ready（Chromium launch ready、local socket bind ready）。Playwright 收集并运行 413 项（1 worker，production webServer）：**413 passed，0 failed，0 flaky，0 skipped**，框架耗时 10.0 分钟；`TEST_LANE_DURATION lane=frontend-mock-e2e seconds=616 status=0`；真实 shell exit 0，墙钟 615.71 秒。

剩余失败：无。55 项原失败所在用例全部在正式全量中通过；未发现新失败。

## 环境阻断 / 未执行 / incomplete

- 环境阻断：无。本会话所有浏览器/socket 命令在允许环境原样运行；lane 预检全部 ready。
- 未执行：Real E2E（CI 对高风险路径的选择性通道；本批无真实凭据，按规格不运行）；`core-full`（无完整交付验收请求）；backend-serial、auth、real、visual、a11y、stagehand、backend-llm/live/external/blocking-io 等专项通道不属于 pr-standard，本票未单独运行。
- incomplete：无悬挂或超时的运行；所有已启动命令均有最终摘要与退出码。
- 代理 `ECONNREFUSED 127.0.0.1:8001` 日线多次出现（8001 Gateway 有意离线）；仅登记观察，不作任何失败的归因。

## 结论

按恢复规格（docs/specs/2026-10-03-mock-e2e-recovery-spec.md §07）的验收门逐项判定：

| 门 | 判定 |
| --- | --- |
| 清单收集（exit 0） | 通过 |
| frontend `pnpm check` | 通过（0 errors） |
| 55 项原失败五次重复生产验收 | 通过（275/275，零重试零 flaky） |
| Mock 全量无回归 | 通过（413/413，0 failed） |
| `pr-standard` 父 lane 通过 | **未通过**（frontend-standard 子 lane status 1，93 项页面单测失败；backend-standard/Rstest/smoke/local-runtime 均 status 0） |

整体判定：**incomplete**。恢复批的核心目标（55 项分类与修复、Mock 全量干净）已达成并有本候选上的完整证据；但 pr-standard 失败使整批不能宣告完成。剩余工作明确且有限：对齐 3 个页面单测文件（QueryClientProvider 包装与 `projects.projectUnavailable` 翻译 mock），随后在同一候选（或仅含该测试侧最小改动的候选）上重跑 frontend-standard 子 lane 与父 pr-standard。03 保持 blocked（无顺序依赖复现，T2 未完成）；#39/#47 保持"未复现、无因果断言、断言完整"的处置。
