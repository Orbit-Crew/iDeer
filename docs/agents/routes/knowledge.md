---
id: task-route-knowledge
kind: reference
status: current
last-verified: 2026-10-09
verified-against: 73a2a168fa08cf1854d60d1ceff41c4b572f63a6
owner: repository maintainers
scope: KnowledgeBase list/create, retrieval, and resource lifecycle behavior
---

# KnowledgeBase

**适用范围：** 按列表/创建、检索或资源生命周期选择分支；一个任务触发多项时合并其资料与验证。

| 改变行为 | 当前契约与不变量 owner | 源码起点与首验证 |
| --- | --- | --- |
| 列表、创建、身份或 provider 绑定 | 经 `/api/resources` 和 Resource Governance 过滤可见性；返回 canonical KB UUID 与 visibility，provider dataset 绑定留在服务端。身份分层见[知识双层真源决策](../../decisions/2026-09-08-knowledge-dual-source-of-truth.md#决策摘要)，列表/创建边界见根 [Enterprise interfaces](../../../AGENTS.md#compatibility) 和[架构第 2 节](../../knowledge/KNOWLEDGE_ARCHITECTURE.md#2-层-1agentplatform-治理)。列表在分页前应用可见性谓词。 | `backend/app/gateway/routers/resources.py::list_resources` 或 `create_resource` → `backend/app/agentplatform/resources/service.py::ResourceService`；先跑 `backend/tests/unit/gateway/test_resources_api.py`。 |
| 检索、scope、结果或 receipt | 读[双层真源决策](../../decisions/2026-09-08-knowledge-dual-source-of-truth.md#决策)、[架构第 3 节](../../knowledge/KNOWLEDGE_ARCHITECTURE.md#3-层-3扩展包agentplatform-runtime-适配)、[第 4 节](../../knowledge/KNOWLEDGE_ARCHITECTURE.md#4-层-2deerflow-运行时--knowledge-provider)及[第 5 节](../../knowledge/KNOWLEDGE_ARCHITECTURE.md#5-端到端数据流m2-完成后)。Provider 管索引/检索；治理层解析 KB UUID、visibility 和 scope，模型不能接触 dataset ID。只在检索行为变化时读此分支。 | 从实际调用层起查：`backend/app/agentplatform/knowledge/`、`backend/packages/agentplatform-extension/agentplatform_extension/knowledge/` 或 provider `backend/packages/harness/deerflow/community/ragflow/`；先跑 `backend/tests/unit/knowledge/test_retrieval_tests.py`，receipt 变化加跑 `test_retrieval_receipts.py`。 |
| 发布、visibility、版本、fork、归档或依赖 | 读[资源治理 V2 生命周期](../../decisions/2026-08-14-resource-governance-v2.md#生命周期转移和-fork)及[知识架构第 2、5 节](../../knowledge/KNOWLEDGE_ARCHITECTURE.md#2-层-1agentplatform-治理)。`ResourceService` 拥有资源治理；KB revision/publish 代码拥有知识版本与 Provider 一致性。具体行为仍以当前 route/service/persistence 为准。 | `backend/app/agentplatform/resources/service.py` 与 `backend/app/agentplatform/knowledge/revisions.py`；先跑 `backend/tests/unit/resources/test_resource_service_governance.py`。Revision/publish 变化加跑 `backend/tests/unit/knowledge/test_knowledge_revision_publish.py`。 |

**条件决策：** 只有资源发布、visibility 改变、fork、归档或依赖变更才展开资源生命周期决策；只有 query、scope、chunk、ranking、结果或 receipt 变化才展开 retrieval 合约。`docs/testing/` 验收记录用于历史追溯，不能代替当前候选验证。

**边界不明：** “KB 行为”需先从 endpoint/call path 分辨列表创建、检索或生命周期。记录尚未确认的层与操作，窄查对应源码；不因共用 visibility 就自动展开审批流程，也不把未知分支记作不适用。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)核实后转入源码检查。
