---
id: task-route-permissions
kind: reference
status: current
last-verified: 2026-10-09
verified-against: 73a2a168fa08cf1854d60d1ceff41c4b572f63a6
owner: repository maintainers
scope: resource list visibility, role-operation authorization, and visibility applications
---

# 资源授权

**适用范围：** 按改变的授权行为选择分支。所有分支都以 [权限原则](../../permission-model-redesign.md#2-设计原则)所在的第一章“权限模型与规则”为现行语义，并按需对照 [权限矩阵](../../permission-matrix.md)。

| 改变行为 | 当前契约与不变量 owner | 源码起点与首验证 |
| --- | --- | --- |
| 列表可见性、计数或分页 | 读第一章 [可见性规则](../../permission-model-redesign.md#4-浏览权限visibility-控制)及矩阵 [Visibility 规则](../../permission-matrix.md#visibility-规则)。`ResourceService`/资源列表负责可见范围；先过滤再分页，行与 count 使用相同谓词。`/api/resources` 还受[资源治理 V2](../../decisions/2026-08-14-resource-governance-v2.md#授权模型)及根 [KnowledgeBase 接口规则](../../../AGENTS.md#compatibility)约束。 | `backend/app/gateway/routers/resources.py`、`backend/app/agentplatform/resources/service.py`；先跑 `backend/tests/unit/gateway/test_resources_api.py`。 |
| 角色操作授权 | 改创建、编辑、删除、使用或其它按角色/owner 判定的操作时，读第一章 [角色与权限](../../permission-model-redesign.md#3-角色与权限)及矩阵 [核心操作权限表](../../permission-matrix.md#核心操作权限表)。`authz.py` 决定授权；从目标 route/service 核对实际调用。 | `backend/app/gateway/authz.py` 和对应资源 route/service；先跑 `backend/tests/contracts/test_rbac_matrix.py`。 |
| 可见性申请与审批 | 改申请、审批/驳回、撤回、审批人或申请状态时，读第一章 [审批流程](../../permission-model-redesign.md#6-审批流程)及矩阵 [审批流程](../../permission-matrix.md#审批流程)。当前申请路由/service 拥有 endpoint 行为；只在涉及的接口查第三章 §3.7 的实现匹配部分。 | `backend/app/gateway/routers/visibility_applications.py`、`backend/app/gateway/routers/resources.py`；先跑 `backend/tests/contracts/test_visibility_applications.py`。 |

**章节状态：** `permission-model-redesign.md` 第一章 §§2 至 4 的原则、角色和可见性规则是当前契约，§6 的审批语义也适用于审批分支。第二至五章分别是 2026-07 数据库、API、前端和迁移设计基线；第三章 §3.7（审批）与 §3.8（审计）仅在对应路由与现行实现匹配时作参考，不能推及整章。第四章未逐页复验，第五章记录已执行迁移。`permission-matrix.md` 的角色操作与可见性语义当前有效，其 API、数据库、前端和迁移章节是设计基线。实现细节以当前 route/service/model 为准。

**条件决策：** 改资源发布、可见性变更、归档、fork 或依赖时读[资源治理 V2](../../decisions/2026-08-14-resource-governance-v2.md#生命周期转移和-fork)；本地设备执行才读[本地授权否决决策](../../decisions/2026-09-08-local-authorization-veto.md)和[安全模型](../../local-runtime/SECURITY_MODEL.md)。列表任务不自动触发申请/审批资料；审批任务也不自动触发一般列表要求，除非该调用路径同时改变列表可见性。

**边界不明：** 先从 endpoint 确认是列表、角色操作还是申请流程，注明未解决的角色/操作；直接改 visibility 与申请审批是不同路径。若 task 未给足信息，窄读 route/service 后记录未知，不把设计基线当成当前实现。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)核实后转入源码检查。
