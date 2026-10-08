---
id: task-route-capabilities
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: Agent, Skill, Workflow and Resource catalog behavior
---

# Agent / Skill / Workflow

**适用范围：** 能力资源目录、发布流程、技能加载或术语变更。

**当前契约：** [Resource Governance V2](../../decisions/2026-08-14-resource-governance-v2.md) 约束 draft/publish/visibility/fork/archive；[CONTEXT.md](../../../CONTEXT.md) 定义领域术语。

**条件决策：** 追溯 Agent 命名历史，或改 Agent/Skill 命名与显示词，读[ADR 0007](../../adr/0007-agent-terminology-unification.md)；资源包内容按技能自身维护规约处理。

**代码入口：** `backend/app/gateway/routers/resources.py`、`backend/app/agentplatform/resource_service.py`、`backend/app/agentplatform/skills/`、`backend/app/agentplatform/workflows/`、`backend/packages/harness/deerflow/skills/`。

**首验证：** 先跑 [`test_resource_service_governance.py`](../../../backend/tests/unit/resources/test_resource_service_governance.py)；实现后匹配 backend standard lane 与 `pr-standard`。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
