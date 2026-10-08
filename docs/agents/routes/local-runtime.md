---
id: task-route-local-runtime
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: local device execution, consent, policy, and registered runtime patches
---

# 本地运行时与设备执行

**适用范围：** 设备控制、本地执行授权、同意分级、路径限制或补丁登记。

**当前契约：** 改补丁前读[补丁账本](../../local-runtime/PATCH_LEDGER.md)；改执行语义读[安全模型](../../local-runtime/SECURITY_MODEL.md)；术语见[CONTEXT](../../../CONTEXT.md)。

**条件决策：** ExecutionTarget 语义读[一等运行维度决策](../../decisions/2026-09-08-execution-target-first-class-dimension.md)；本地否决读[双层授权决策](../../decisions/2026-09-08-local-authorization-veto.md)；harness 补丁登记根账本。

**代码入口：** `backend/app/device_control/`、`backend/app/gateway/routers/devices.py`；harness 扩展位于 `backend/packages/harness/deerflow/`。

**首验证：** 按账本先跑 patch-specific 检查；核对 `local-runtime/tests/test_policy_denial.py`、`test_file_service.py`，再跑 `local-runtime` lane 与匹配 standard lane、`pr-standard`。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
