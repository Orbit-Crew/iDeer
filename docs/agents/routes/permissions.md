---
id: task-route-permissions
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: RBAC, resource visibility, permission applications, and authorization decisions
---

# 资源授权

**适用范围：** 角色权限、资源可见性、审批或资源授权实现。

**当前契约：** 先读[授权原则](../../permission-model-redesign.md#2-设计原则)、[角色与权限](../../permission-model-redesign.md#3-角色与权限)及[可见性规则](../../permission-model-redesign.md#4-浏览权限visibility-控制)；按角色操作查[核心操作权限表](../../permission-matrix.md#核心操作权限表)，按可见范围查[Visibility 规则](../../permission-matrix.md#visibility-规则)，申请流程查[审批流程](../../permission-model-redesign.md#6-审批流程)。KB 身份边界读[双层真源决策](../../decisions/2026-09-08-knowledge-dual-source-of-truth.md)。

**条件决策：** 资源发布、可见性、归档或依赖生命周期读[Resource Governance V2](../../decisions/2026-08-14-resource-governance-v2.md)；设备本地执行才读[本地否决决策](../../decisions/2026-09-08-local-authorization-veto.md)及[安全模型](../../local-runtime/SECURITY_MODEL.md)。权限模型重构文档的第二至五章及权限矩阵中的 API、数据库、前端、迁移章节是 2026-07 设计基线，仅在追溯历史方案时查阅，不作为现行接口依据。

**代码入口：** `backend/app/gateway/authz.py`、`backend/app/agentplatform/rbac_models.py`、`backend/app/gateway/routers/visibility_applications.py`、`backend/app/gateway/routers/resources.py`、`backend/app/agentplatform/resource_service.py`。

**首验证：** 先看 `backend/tests/contracts/test_rbac_matrix.py` 和 `backend/tests/unit/resources/test_resource_service_access.py`；审批加 `test_visibility_applications.py`。跑相关 contract/integration、backend standard lane 与 `pr-standard`；本地运行时还需 `local-runtime` lane。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
