---
id: docs-decisions-2026-10-13-backend-test-dedup
kind: decision
status: current
owner: test maintainers
scope: backend/tests 双目录同名测试副本的去重决策与执行口径——迁移收尾(选项 a)被采纳,根副本为合并基、子目录为规范位置;不改变任何产品代码与测试语义归属
last-verified: 2026-10-13
verified-against: worktree fix/cr-batch6-test-dedup @ 45e61766a
---

# backend/tests 双目录同名副本去重:采纳迁移收尾(选项 a)

> audience: test maintainers, developers, reviewers
> status: accepted
> owner: test maintainers
> last-verified: 2026-10-13
> canonical-path: `docs/decisions/2026-10-13-backend-test-dedup.md`

## 决策摘要

对 `backend/tests` 根目录与 `{unit,integration,contracts}` 子目录之间的 148 对同名测试文件(票据 #66 / 审查发现 09-H1),采纳**选项 (a) 迁移收尾**:删除根目录副本,把根副本内容按"根为合并基、子目录为规范位置"合并进子目录 keeper;拒绝选项 (b)(把双跑登记为已知状态)。`tests/blocking_io/` 与其余根目录独有(无同名孪生)文件不在本次去重范围,见下文范围裁定。

## 背景与备选

2026-07-09 账本批次"Backend Root Test Domain Move"确曾把根目录测试整体 `git mv` 进子目录(commit 60f0ef382 中 `test_channels.py` 为 R100 纯重命名);随后 2026-07-09~09-06 间的批次提交(如 `4feb26e0f` "B4b 权限/隔离 + B4c 杂项"、9 月初 legacy-harness 重构)在**未登记账本**的情况下重建了根目录副本。此后两条副本并行演化:根副本普遍吸收了更新的产品契约断言(如 channels 的 `owner_user_id`/`connection_id`/thread metadata,及批次 5 对 `test_extension_registry/loader`、`test_agentplatform_extension_boundary`、`tests/conftest.py` 的新增),子目录副本也有独立演化。结果是 backend-standard 车道对每个同名用例执行两遍(两份都绿),每轮车道时长翻倍浪费、结果计数不可信。

处置备选:

- **选项 (a) 迁移收尾**:删除根副本,内容保全后合并进子目录 keeper,账本逐批登记。与根 [AGENTS.md](../../AGENTS.md) 目录契约(`Backend test_*.py files go in backend/tests/{unit,integration,contracts}`)、账本既有方向、审查报告建议一致。
- **选项 (b) 恢复登记**:把"双目录双跑"改口登记为已知状态。被否决:每轮 backend-standard 多跑约一半重复用例(基线 1128s 中相当比例是重复执行),且"账本记载与 collect-only 事实一致"的验收无法与 [test-migration-ledger](../testing/test-migration-ledger.md) 的删除门语义自洽——账本将不得不同时声称"迁移完成"与"双跑是常态"。

## 决策

1. **范围**:148 对根 ↔ `{unit,integration,contracts}` 同名文件(全树 collect-only 实测这些对产生 2607 个同名测试键被双收集;全树 30239 个收集项)。以下**不在**范围:
   - `tests/blocking_io/` 的 14 对同名文件:标准车道显式 `--ignore=tests/blocking_io`,blocking-io 车道只跑 `tests/blocking_io`,两套副本从不在同一车道共跑,不构成双跑;该目录是 Blockbuster 严格门的专属执行域(自带 conftest 与 `allow_blocking_io` 逃生标记),按"合法特殊位置"保留,账本登记。
   - 根目录独有(无同名孪生)的 541 个测试文件:不产生双收集,本次保留在根位置并在账本登记保留理由;其层位归置(unit/integration/contracts 分桶)是与 #69 相关的后续机械迁移,不在本票据内冒进。
2. **合并基与冲突规则**:对每一对,以**根副本为合并基**整体落位到子目录 keeper 路径(规范化 `__file__` 路径深度),并保全子目录独有内容——子目录独有类方法拼接进同名类,子目录独有模块级定义/常量/导入追加。同名测试冲突取根副本变体:两份变体在当前候选上都被标准车道跑绿,取根不弱于现状,且根副本承载批次 5 的最新断言血缘。`pytestmark`/`pytest_plugins` 等模块级全局指令不从子副本带入。每个合并文件的冲突清单由工具输出并归档(dev-log/batch6)。
3. **守卫**:新增 `scripts/check_test_collection_duplicates.py`,以 pytest collect-only 为真值断言"标准车道收集范围内无同名测试键被两个文件收集"。引入时在现状上报红(2607 个重复键,148 对),去重完成后转绿,防复发。
4. **账本**:逐批在 [test-migration-ledger](../testing/test-migration-ledger.md) 登记 removed/kept 路径、断言映射(同根变体胜出、子目录独有保全、冲突清单位置)与验证命令;对 2026-07-09 批次补注事实更正(迁移当时为真,后被未登记的重建打断)。

## 影响

- **车道时长**:backend-standard 去重后重复执行消除,预期相对基线(d8f1418d2,29629 passed/236 skipped,1128s)显著缩短;实际数字见执行摘要与账本批次记录。
- **覆盖率守恒**:合并按"根内容全量 + 子目录独有全量"保全两侧断言;同名漂移取根变体,子变体在账本登记为"同候选双绿、根变体胜出"的取代关系。纯删除仅限两侧逐字相同的 7 对及无独有内容的 sub_superset 对。
- **后续依赖**:#69(根目录独有文件层位归置)以本决策的范围裁定为前提;`scripts/check_test_collection_duplicates.py` 为后续迁移的常驻回归门。

## 执行摘要

2026-10-13 当日完成,提交序:

- 决策与守卫:`756531bfa`(本决策)、`c4cde8630`(2026-07-09 账本批次事实更正)、`c28a24dd8`(守卫 `scripts/check_test_collection_duplicates.py`,引入时对现状报红:2607 个同名测试键/148 对被双收集)。
- 去重 8 批(每批焦点绿+账本登记):`ea95eeaec`(channels/memory/workflows)、`bbbb9d050`(gateway)、`518aed0ce`(runtime)、`a2a4f23ad`(models/persistence)、`21c1a9cb1`(tools)、`01edba683`(sandbox)、`47a1cb6bb`(skills/scripts)、`8122daac6`(integration/api+contracts)。
- 执行后修复(运行时引用不被 import/AST 清查覆盖):`4c07acbc0`(三处跨测试 import 与一处 `Path` 源码读改指 keeper;收口车道首轮 8 failed 即此)、`529d0e87d`(sandbox-image-smoke workflow 与 scripts 指南改指 keeper 路径)。
- collect-only:执行前全树 30239 收集项、2607 个同名键双收集 → 执行后标准车道范围 27385 项、守卫报零重复。
- 车道时长:基线(去重前,d8f1418d2)backend-standard 29629 passed/236 skipped、1128s;去重后(4c07acbc0,后继仅配置/文档提交)26836 passed/235 skipped、926s(产物 `logs/test-lanes/backend-standard-20261013T123933Z-2950947/run.log`)——用例数 −2793(即被去重的同名副本执行),时长 −202s(−17.9%)。
- 遗留:541 个根目录独有测试文件的层位归置归 #69;`tests/blocking_io/` 14 对同名文件按执行域分离保留(见范围裁定)。

## 复议条件

- blocking_io 车道与标准车道的执行域合并(如 Blockbuster 门改为全局可选),同名文件重新共跑时需重开裁定。
- #69 完成层位归置后,若出现新的同名副本或收集异常,以守卫脚本报红为准重开处理。
