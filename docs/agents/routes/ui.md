---
id: task-route-ui
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: frontend UI-only changes
---

# 普通前端组件

**适用范围：** 不涉及提交、流状态、授权或持久化的界面组合与展示变更。

**当前契约：** [前端模块约定](../../../frontend/AGENTS.md)；[工程术语](../../../CONTEXT.md)，仅在显示术语有歧义时读。

**条件决策：** 上游能力进入前端时读[ADR 0005](../../adr/0005-preserve-workbench-experience-when-adopting-deerflow-features.md)；调整能力导航时读[ADR 0001](../../adr/0001-workbench-capability-navigation.md)。

**代码入口：** `frontend/src/components/`、`frontend/src/core/`、`frontend/src/app/`；工作台组合在 `components/workspace/`。

**首验证：** 先跑 [`terminal.test.tsx`](../../../frontend/tests/unit/components/ui/terminal.test.tsx)（`cd frontend && pnpm vitest run tests/unit/components/ui/terminal.test.tsx`）；实现后 frontend standard lane、`pr-standard`。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
