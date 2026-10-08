---
id: task-route-chat
kind: reference
status: current
last-verified: 2026-10-08
verified-against: 7659c03ea47eb4da50eeddba836c094d743f0f2b
owner: repository maintainers
scope: chat submission, streaming, shared chat pages, and Run/Thread lifecycle changes
---

# 对话提交与流式状态

**适用范围：** 提交栅栏、消息顺序、流状态、Gateway/SSE、嵌入式流，或 Run/Thread 取消、恢复与持久化。

**当前契约：** 提交/共享页面读[frontend Ownership](../../../frontend/AGENTS.md#ownership)，改 thread 状态再读[前端数据流](../../../frontend/src/AGENTS.md)；Gateway 事件路径读[STREAMING Gateway 路径](../../../backend/docs/STREAMING.md#gateway-路径async--http-sse)。前端展示身份与顺序归并由 `message-order.ts::mergeMessages` 负责。SDK/in-process `DeerFlowClient` 的 message chunk 增量及按 message ID 组装读[消费语义](../../../backend/docs/STREAMING.md#消费语义delta-vs-cumulative)；该处的 chunk 装配与[三个 ID set 不变量](../../../backend/docs/STREAMING.md#三个-id-set-为什么不能合并)所述 embedded messages/values 跨模式去重是两条独立规则，后者由 `DeerFlowClient.stream()` 维护三个用途不同的 ID set。改 harness runtime 读其[模块指南](../../../backend/packages/harness/deerflow/runtime/AGENTS.md)。Run 恢复读[delivery/recovery mechanics](../../../backend/docs/development-reference.md#run-delivery-and-stream-recovery-mechanics)。

**条件决策：** 仅改 PAT 授权/观察者断开时读[API PAT Constraints](../../../backend/docs/API.md#pat-constraints)；事件投影读[Run event stream](../../../backend/docs/RUN_EVENT_STREAM.md)；恢复、再生成或 edit-replay 读[Thread lifecycle](../../../backend/docs/THREAD_LIFECYCLE.md)。本地执行联动按 local-runtime 页；改 harness runtime 依根规则选择 Extension → Adapter → 登记补丁。

**代码入口：** 前端 `frontend/src/core/threads/{turn-submit.ts,hooks.ts,use-thread-page.ts,message-order.ts}`；Gateway `backend/app/gateway/routers/thread_runs.py`、`services.py`、`backend/packages/harness/deerflow/runtime/stream_bridge/`；嵌入式流 `backend/packages/harness/deerflow/client.py::DeerFlowClient.stream`；Run 持久化见 `runtime/runs/`。

**首验证：** 前端先看 `frontend/tests/unit/core/threads/turn-submit.test.ts`、`message-order.test.ts`、`hooks.test.ts`；Gateway 看 `backend/tests/unit/gateway/test_services_behavior.py` 与 `backend/tests/unit/runtime/test_stream_bridge.py`；嵌入式流看 `backend/tests/test_client.py`。按改变的栈跑对应 standard lane 与 `pr-standard`。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)逐项核实。
