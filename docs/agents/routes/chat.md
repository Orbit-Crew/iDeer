---
id: task-route-chat
kind: reference
status: current
last-verified: 2026-10-09
verified-against: 73a2a168fa08cf1854d60d1ceff41c4b572f63a6
owner: repository maintainers
scope: chat submission, SDK messages, Gateway events, embedded streams, and Run/Thread lifecycle
---

# 对话提交与流式状态

**适用范围：** 按实际改变的行为选择下列分支。一个任务涉及多个行为时，合并其资料、owner 和首验证。

| 改变行为 | 触发时读什么、保留什么 | 源码起点与首验证 |
| --- | --- | --- |
| 提交栅栏 | 改用户提交、pending/重复提交拒绝或后续 turn 何时可提交时，读 [Frontend Ownership](../../../frontend/AGENTS.md#ownership) 和 [前端数据流](../../../frontend/src/AGENTS.md)。`turn-submit.ts` 负责提交状态；pending turn 期间拒绝重复提交，结算后允许下一次提交。Run/Thread 生命周期只在改到这些状态时展开。 | `frontend/src/core/threads/turn-submit.ts`；先跑 `frontend/tests/unit/core/threads/turn-submit.test.ts`。 |
| SDK chunk 组装 | 改 SDK/in-process message chunks 或其到 thread message 的映射时，读 [消费语义](../../../backend/docs/STREAMING.md#消费语义delta-vs-cumulative)。`DeerFlowClient` 按 message ID 组装增量；同一 ID 保留全部 delta，不同 ID 保持分开。这与 embedded 跨模式去重分支独立。 | `backend/packages/harness/deerflow/client.py` 的 `DeerFlowClient`；先跑 `backend/tests/test_client.py`。仅显示顺序/身份归并变化时，再读前端 `message-order.ts` 并检查 `message-order.test.ts`。 |
| Gateway 事件与恢复 | 改事件投影、SSE、重连、恢复或 regeneration 时，读 [Gateway 流路径](../../../backend/docs/STREAMING.md#gateway-路径async--http-sse)、[Run event stream](../../../backend/docs/RUN_EVENT_STREAM.md#record-envelope) 和 [Thread lifecycle 的 regenerate/edit-replay 章节](../../../backend/docs/THREAD_LIFECYCLE.md#regenerate-and-edit-replay-preparation)。保留公开事件语义与 Run/Thread 生命周期。 | `backend/app/gateway/routers/thread_runs.py`、`backend/app/gateway/services.py`、`backend/packages/harness/deerflow/runtime/stream_bridge/`；先跑 `backend/tests/unit/runtime/test_stream_bridge.py`。改 service projection 时加看 `backend/tests/unit/gateway/test_services_behavior.py`。 |
| Embedded 跨模式去重 | 改 `DeerFlowClient.stream()` 对 embedded messages/values 跨 stream mode 的处理时，读 [三个 ID set 不变量](../../../backend/docs/STREAMING.md#三个-id-set-为什么不能合并)。三个 set 各有用途，保持分开；不要把此规则与 SDK 的同 ID chunk 组装合并。 | `backend/packages/harness/deerflow/client.py::DeerFlowClient.stream`；先跑 `backend/tests/test_client.py`。 |

**条件决策：** PAT 授权变化才读 [PAT constraints](../../../backend/docs/API.md#pat-constraints)；本地执行参与时按 [local-runtime 路由](local-runtime.md)；改 harness runtime 时按根规则判断 Extension、Adapter 或登记补丁。恢复、再生成或 edit-replay 变化时读 Thread lifecycle 中对应章节。只读 harness 入口不代表要改 harness。

**边界不明：** “streaming” 需先区分提交准入、SDK 消费、Gateway 事件和 embedded 去重；“duplicate” 需先区分 pending turn 拒绝、同 ID chunk 组装和跨模式去重。沿窄调用路径确认 owner；范围仍不清时记录未知并请求澄清，不推断其它分支不适用。

**停止条件：** 按[索引的五项停止条件](../task-routing.md#停止条件)核实后转入源码检查；这只是开发起点，不代表实现已正确。
