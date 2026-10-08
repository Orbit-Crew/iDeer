---
id: task-route-knowledge
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: KnowledgeBase and Knowledge Center list/create, visibility, identity, and provider integration
---

# KnowledgeBase

**适用范围：** 知识库列表/创建、治理身份、可见性或检索数据流。

**当前契约：** 根 [Enterprise interfaces](../../../AGENTS.md#compatibility) 规定列表/创建经 `/api/resources` 与治理可见性过滤、provider 绑定留服务端；数据流读[知识双层真源决策](../../decisions/2026-09-08-knowledge-dual-source-of-truth.md)。

**条件决策：** 发布、可见性或 fork 涉及资源生命周期时读[Resource Governance V2](../../decisions/2026-08-14-resource-governance-v2.md)；`docs/testing/` 的验收报告仅供追溯历史。

**代码入口：** `backend/app/gateway/routers/resources.py::list_resources` 调用 `ResourceService.list_visible`；Gateway seam 为 `backend/app/agentplatform/resource_service.py`，可见性过滤实现在 `backend/app/agentplatform/resources/service.py::ResourceService._visible_query/list_visible`。管理检查入口为 `backend/app/gateway/routers/admin_knowledge.py`。

**首验证：** 先跑 [`test_resources_api.py`](../../../backend/tests/unit/gateway/test_resources_api.py) 核验 `/api/resources`；之后匹配 backend standard lane 与 `pr-standard`。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
