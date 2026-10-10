---
id: task-route-tests
kind: reference
status: current
last-verified: 2026-10-09
verified-against: 73a2a168fa08cf1854d60d1ceff41c4b572f63a6
owner: repository maintainers
scope: test addition, migration, deletion, ownership, lane selection, and PR handoff
---

# 测试新增与迁移

**适用范围：** 按新增、移动/改名或删除测试选择分支。一个任务同时替换并删除旧节点时，合并适用要求。

| 改变行为 | 当前契约与不变量 | 首验证 |
| --- | --- | --- |
| 新增测试 | 按[测试入口](../../testing/README.md)选目录，按[覆盖矩阵](../../testing/coverage-matrix.md)确定行为 owner 和层级，按[Lane 手册](../../testing/test-lane-runbook.md)选验证。保留断言强度与执行归属。无需阅读历史迁移批次。 | 先跑新测试的聚焦命令，再跑 `python3 scripts/test_inventory.py`。 |
| 移动或改名测试 | 按[迁移方法](../../testing/test-migration-ledger.md#迁移方法)核对行为 owner、目标层、配置/fixture/path 依赖和 collected node identity。保留所有断言；在迁移账本记录旧/新路径、断言映射、keeper/replacement、配置和实际验证。仅当相似历史批次有助于判断时才读该批次。 | 先跑新路径的聚焦测试，比较旧/新收集节点，再跑 `python3 scripts/test_inventory.py` 并更新迁移账本。 |
| 删除测试或节点 | 按覆盖矩阵与迁移账本证明 keeper/replacement 保留等强或更强行为断言、覆盖责任和执行归属；记录删除路径、替代关系与验证。没有等强替代证据时，报告覆盖缺口。历史批次仅作相似案例参考。 | 跑 keeper/replacement 的聚焦测试，再跑 inventory，确认被删节点不再收集并更新迁移账本。 |

**代码入口：** `backend/tests/{unit,integration,contracts}/`、`frontend/tests/{unit,e2e}/`；runner 为 `scripts/run-test-lane.sh`，清单为 `scripts/test_inventory.py`。

**条件决策：** 新增/移动后运行 inventory；PR 候选按 [Lane 手册](../../testing/test-lane-runbook.md#选择与运行)运行 `pr-standard`。仅在受保护高风险路径由 CI 选择时记录 Real E2E。迁移历史不是每项测试任务的前置阅读；lane 结果复用须满足候选、依赖、配置和环境相同。

**边界不明：** 若任务声称“替换”但未说明旧节点去留，查 diff 和收集结果确认是否同时属于迁移/删除；不得默认等价。若无 keeper、owner 或 lane 归属，记录缺口并先核实覆盖矩阵/清单。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)核实后开始源码与测试核验。
