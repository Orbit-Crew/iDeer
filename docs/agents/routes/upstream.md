---
id: task-route-upstream
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: upstream releases, conflict resolution, convergence rounds, and patch tracking
---

# 上游同步

**适用范围：** 合并、同步或吸收上游发布，或维护 harness 补丁。

**当前契约：** 根 [UPSTREAM_PATCH_LEDGER.md](../../../UPSTREAM_PATCH_LEDGER.md) 是有效锁定点与补丁登记权威；根 Enterprise compatibility 节规定扩展顺序与生命周期约束。

**条件决策：** 报告同步、集成、验证前核对最新锁定裁决及[项目状态](../../project-state.md)，仅候选 SHA 匹配才复用状态；分支规则读[产品线治理](../../offline-product-line-governance-plan.md)。冲突时按轮次打开路径政策、冲突台账、锁定记录，逐项按行为裁决。

**代码入口：** `backend/packages/harness/deerflow/`，按冲突涉及路径继续定位；补丁登记位于根账本。

**首验证：** 改补丁先更新账本，分别验证定制关闭和企业约束开启，再跑匹配 standard lane 与 `pr-standard`；仅追溯状态无需运行。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
