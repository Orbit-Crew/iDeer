---
id: task-route-tests
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: test placement, ownership, migration, lane selection, and PR handoff
---

# 测试新增与迁移

**适用范围：** 新增、移动、删除测试或选择验证 lane。

**当前契约：** [测试入口](../../testing/README.md)定分层；[Lane 手册](../../testing/test-lane-runbook.md)定选择与复用；[覆盖矩阵](../../testing/coverage-matrix.md)映射行为。移动或删除测试时先按[迁移方法](../../testing/test-migration-ledger.md#迁移方法)逐项核对，再按批次日期查该账本中的历史记录。

**条件决策：** 移动/删除时将 keeper、等强或更强替代断言及该批验证写入迁移账本；仅在相似历史迁移能帮助判断时展开对应批次。lane 结果复用条件以 runbook 为准。

**代码入口：** `backend/tests/{unit,integration,contracts}/`、`frontend/tests/{unit,e2e}/`、`scripts/run-test-lane.sh`、`scripts/test_preflight.py`、`scripts/test_inventory.py`。

**首验证：** 先跑聚焦用例；新增/移动后跑 `python3 scripts/test_inventory.py`；lane 前 preflight（runner 自动执行）；PR gate `pr-standard`。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
