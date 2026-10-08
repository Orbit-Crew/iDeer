---
id: task-routing
kind: index
status: current
owner: repository maintainers
scope: nine engineering task domains
---

# Task Routing

按域进入[短路由页](routes/)；根 [AGENTS.md](../../AGENTS.md) 保留全局义务。短页给出适用范围、当前契约章节、条件决策、代码入口和首验证。配套索引：[工程文档](../README.md)、[技能路由](skill-routing.md)、[spec/工单约定](issue-tracker.md)、[领域建模](domain.md)、[决策索引](../decisions/README.md)。

| 领域 | 短页 |
| --- | --- |
| 普通前端组件 | [ui](routes/ui.md) |
| 对话提交与流式状态 | [chat](routes/chat.md) |
| 资源授权 | [permissions](routes/permissions.md) |
| KnowledgeBase | [knowledge](routes/knowledge.md) |
| Agent / Skill / Workflow | [capabilities](routes/capabilities.md) |
| 本地运行时与设备执行 | [local-runtime](routes/local-runtime.md) |
| 配置与部署 | [deployment](routes/deployment.md) |
| 测试新增与迁移 | [tests](routes/tests.md) |
| 上游同步 | [upstream](routes/upstream.md) |

历史追溯按主题进入对应页：Agent 命名见 [capabilities](routes/capabilities.md)，知识治理见 [knowledge](routes/knowledge.md)；历史结论再对照当前契约与代码。历史是评估任务类别，不增加工程任务域。

## 停止条件

五项均能从短页及已触发资料指出后，停止扩展文档阅读并开始源码核验；这只建立开发起点，不证明实现正确。每页链接本定义，不重复其规则。

1. **代码入口**：指出具体文件、目录或公开 seam；目录起点须在源码中定位实现。
2. **当前契约**：指出适用的现行文档及章节；历史记录仅用于追溯或兼容判断。
3. **条件决策**：说明触发的 decision/ledger；未触发则记不适用，不展开。
4. **验证路径**：指出聚焦检查、匹配 standard lane 与 `pr-standard`；按风险补充 contract、integration 或专用 lane。命令不代表已通过。
5. **未决状态**：核对 issue/spec 与短页指向的待办/限制并记录来源。未查标“未核实”；仍无法确定时说明已查材料和未知点，不推断为“没有”。

从入口检查调用、实现和不变量，再决定是否扩大搜索。历史测试结果不满足当前候选验证。