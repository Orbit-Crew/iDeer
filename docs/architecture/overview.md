---
id: docs-architecture-overview
kind: reference
status: current
owner: repository maintainers
scope: iDeer architecture baseline: gateway/frontend/nginx topology, harness/app layering, runtime subsystems (agents, middleware, sandbox, tools, MCP, skills, models, channels, memory), and local run/test commands
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 0e9cd4562
---

# iDeer 架构概览

> audience: developers, architects<br>
> status: current<br>
> owner: engineering maintainers<br>
> last-verified: 2026-10-04<br>
> canonical-path: `docs/architecture/overview.md`

本文件描述 iDeer 当前的系统边界与执行关系，是[架构索引](README.md)下的架构基线参考之一。工程术语以根目录 [CONTEXT.md](../../CONTEXT.md) 为权威；[UI 术语对照表](../plans/2026-08-26-term-glossary.md) 仅覆盖界面显示语言（i18n 文案），不构成工程术语定义。按任务进入文档见[工程文档入口](../README.md)与[任务路由](../agents/task-routing.md)。

## 项目概览

iDeer 是一个基于 LangGraph 的 AI 超级智能体系统，采用全栈架构。后端提供“超级智能体”能力，包含沙箱执行、持久化记忆、子智能体委托以及可扩展工具集成，且所有能力都运行在线程级隔离环境中。

## 当前集成进展（2026-09-21）

本节是 2026-09-21 的时点集成状态快照，属于历史时点记录，不是当前架构边界或当前验收状态；历史测试结果不作为当前候选的验证依据。

| 工作包 | 代码状态 | 验收状态 |
| --- | --- | --- |
| M5 检索证据闭环 | 已整合到当前本机候选 | RAGFlow provider probe 已通过；真实 Agent 来源链、16 项矩阵和浏览器链路待外部环境 |
| M6 检索测试与发布门禁 | 已整合到当前本机候选 | 单案例评估与 Profile A/B 已通过；完整 Gate 8 artifact、发布拒绝场景和浏览器链路待外部环境 |
| M9 本地 MCP、Secrets、Tray | 已整合到当前本机候选 | 本机测试通过；Windows 7 原生验收待测试机 |
| 多附件 TTFT 诊断 | 上传 trace_id 关联能力已保留；诊断边界测试通过 | 真实业务 Agent 0/1/5/10/20 文件配对实验待外部环境；行为优化延期 |

本机候选的标准测试入口是 `scripts/run-test-lane.sh`；后端本地测试使用 `cd backend && make test`，前端使用 `cd frontend && pnpm test`。正式收口仍要求 Gate 7、Gate 8、Windows 7 及真实业务链路的独立证据。

**架构**：

- **Gateway API**（端口 8001）：REST API 加嵌入式 LangGraph 兼容智能体运行时
- **Frontend**（端口 3000）：Next.js Web 界面
- **Nginx**（端口 2026）：统一反向代理入口
- **Provisioner**（端口 8002，Docker 开发模式下可选）：仅在沙箱配置为 provisioner/Kubernetes 模式时启动

**运行时**：

- `make dev`、Docker 开发环境和生产环境都会通过 Gateway 中的 `RunManager` + `run_agent()` + `StreamBridge`（`backend/packages/harness/deerflow/runtime/`）运行智能体运行时。Nginx 将该运行时暴露在 `/api/langgraph/*`，并重写到 Gateway 原生的 `/api/*` 路由。

**项目结构**：

```text
ideer/
├── Makefile                    # 根目录命令（check、install、dev、stop）
├── config.yaml                 # 主应用配置
├── extensions_config.json      # MCP 服务器和技能配置
├── backend/                    # 后端应用（当前目录）
│   ├── Makefile               # 仅后端命令（dev、gateway、lint）
│   ├── langgraph.json         # LangGraph Studio 图配置
│   ├── packages/
│   │   └── harness/           # deerflow-harness 包（导入：deerflow.*）
│   │       ├── pyproject.toml
│   │       └── deerflow/
│   │           ├── agents/            # LangGraph 智能体系统
│   │           │   ├── lead_agent/    # 主智能体（工厂 + 系统提示词）
│   │           │   ├── middlewares/   # 中间件组件（见 backend/docs/middleware-execution-flow.md）
│   │           │   ├── memory/        # 记忆管理（可插拔 backend）
│   │           │   └── thread_state.py # ThreadState 模式
│   │           ├── runtime/           # Gateway 嵌入式运行时（runs、stream_bridge、user_context 等）
│   │           ├── sandbox/           # 沙箱执行系统
│   │           │   ├── local/         # 本地文件系统 provider
│   │           │   ├── sandbox.py     # 抽象 Sandbox 接口
│   │           │   ├── tools.py       # bash、ls、glob、grep、read/write/str_replace
│   │           │   └── middleware.py  # 沙箱生命周期管理
│   │           ├── subagents/         # 子智能体委托系统
│   │           │   ├── builtins/      # general-purpose、bash 智能体
│   │           │   ├── executor.py    # 后台执行引擎
│   │           │   └── registry.py    # 智能体注册表
│   │           ├── tools/builtins/    # 内置工具（present_files、ask_clarification、view_image 等）
│   │           ├── mcp/               # MCP 集成（工具、缓存、客户端）
│   │           ├── models/            # 支持 thinking/vision 的模型工厂
│   │           ├── skills/            # 技能发现、加载、解析
│   │           ├── config/            # 配置系统（app、model、sandbox、tool 等）
│   │           ├── community/         # 社区工具（tavily、jina_ai、firecrawl、image_search、aio_sandbox 等）
│   │           ├── reflection/        # 动态模块加载（resolve_variable、resolve_class）
│   │           ├── utils/             # 工具函数（network、readability）
│   │           └── client.py          # 嵌入式 Python 客户端（DeerFlowClient）
│   ├── app/                   # 应用层（导入：app.*）
│   │   ├── gateway/           # FastAPI Gateway API
│   │   │   ├── app.py         # FastAPI 应用
│   │   │   └── routers/       # FastAPI 路由模块（models、mcp、memory、resources、uploads、threads、thread_runs、runs、artifacts、admin、auth、projects、skills、agents、channels 等，完整清单见该目录）
│   │   └── channels/          # IM 平台集成
│   ├── tests/                 # 测试套件
│   └── docs/                  # 文档
├── frontend/                   # Next.js 前端应用
└── skills/                     # 智能体技能目录（默认位置，可经 skills.path 配置）
    ├── public/                # 公共技能（提交到仓库）
    └── custom/                # 自定义技能（按需创建）
```

## 重要开发指南

### 文档更新策略

文档随行为、接口、配置、架构或工作流的变更而更新；入口见 [docs/README.md](../README.md)。规则与代理指南的维护遵循根 `AGENTS.md` 的 Guidance maintenance 约定：`AGENTS.md` 是唯一来源，`CLAUDE.md` 由同步脚本生成，不手工编辑。

## 命令

**根目录**（完整应用）：

```bash
make check      # 检查系统要求
make install    # 安装所有依赖（前端 + 后端）
make dev        # 启动所有服务（Gateway + Frontend + Nginx），并预检查 config.yaml
make start      # 在本地启动生产模式服务
make stop       # 停止所有服务
```

**后端目录**（仅后端开发）：

```bash
make install    # 安装后端依赖
make dev        # 以 reload 模式运行 Gateway API（端口 8001）
make gateway    # 仅运行 Gateway API（端口 8001）
make test       # 运行全部后端测试
make lint       # 使用 ruff 检查
make format     # 使用 ruff 格式化代码
```

与 Docker/provisioner 行为相关的回归测试：

- `tests/test_docker_sandbox_mode_detection.py`（从 `config.yaml` 识别模式）
- `tests/unit/sandbox/test_provisioner_kubeconfig.py`（kubeconfig 文件/目录处理）

边界检查（harness 到 app 的导入防火墙）：

- `tests/test_harness_boundary.py`：确保 `packages/harness/deerflow/` 永远不会从 `app.*` 导入

CI 会通过 [.github/workflows/backend-unit-tests.yml](../../.github/workflows/backend-unit-tests.yml) 在每个 Pull Request 上运行这些回归测试。

## 架构

### Harness / App 分层

后端被拆分为两层，并具有严格的依赖方向：

- **Harness**（`packages/harness/deerflow/`）：可发布的智能体框架包（`deerflow-harness`）。导入前缀为 `deerflow.*`。包含智能体编排、工具、沙箱、模型、MCP、技能、配置等构建和运行智能体所需的一切。
- **App**（`app/`）：不发布的应用代码。导入前缀为 `app.*`。包含 FastAPI Gateway API 和 IM 渠道集成（飞书、Slack、Telegram、钉钉、Discord、微信、企业微信、GitHub、Buzz/Nostr）。

**依赖规则**：App 可以导入 deerflow，但 deerflow 绝不能导入 app。该边界由 `tests/test_harness_boundary.py` 强制执行，并在 CI 中运行。

**导入约定**：

```python
# Harness 内部
from deerflow.agents import make_lead_agent
from deerflow.models import create_chat_model

# App 内部
from app.gateway.app import app
from app.channels.service import start_channel_service

# App → Harness（允许）
from deerflow.config import get_app_config

# Harness → App（禁止，由 test_harness_boundary.py 强制）
# from app.gateway.routers.uploads import ...  # ← 会导致 CI 失败
```

### 智能体系统

**Lead Agent**（`packages/harness/deerflow/agents/lead_agent/agent.py`）：

- 入口：`make_lead_agent(config: RunnableConfig)`，注册在 `langgraph.json`
- 通过 `create_chat_model()` 动态选择模型，支持 thinking/vision
- 通过 `get_available_tools()` 加载工具，组合沙箱、内置、MCP、社区和子智能体工具
- 通过 `apply_prompt_template()` 生成系统提示词，包含技能、记忆和子智能体说明

**ThreadState**（`packages/harness/deerflow/agents/thread_state.py`）：

- 在 `AgentState` 基础上扩展：`sandbox`（`SandboxState`）、`thread_data`、`title`、`artifacts`、`todos`、`goal`、`uploaded_files`、`viewed_images`、`promoted`、`delegations`、`skill_context`、`task_notes` 等
- 使用自定义 reducer：`merge_artifacts`（去重）、`merge_viewed_images`（合并/清空）、`merge_sandbox`（幂等写入）等

**运行时配置**（通过 `config.configurable`）：

- `thinking_enabled`：启用模型扩展思考
- `model_name`：选择指定 LLM 模型
- `is_plan_mode`：启用 TodoList 中间件
- `subagent_enabled`：启用任务委托工具

### 中间件链

Lead-agent 中间件在 `packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`（`build_lead_runtime_middlewares`）和 `packages/harness/deerflow/agents/lead_agent/agent.py`（`_build_middlewares`）中按严格追加顺序组装。当前链条约 38 个条目（含自定义与扩展注入槽位），覆盖：输入与工具输出净化、线程数据目录、上传注入、沙箱生命周期、悬挂 tool-call 兜底、LLM 错误规范化、授权/guardrail 前置检查、沙箱审计、写前读取、工具进度与错误转换、动态上下文与技能激活、持久上下文、上下文摘要（可选）、Plan 模式 Todo（可选）、token 用量与预算、标题生成、记忆（可选）、图片注入（vision 模型）、MCP 路由与 deferred 工具过滤、系统消息合并、子智能体并发上限、循环检测（可选）、终止响应规范化，最后由 `ClarificationMiddleware` 拦截 `ask_clarification`（永远最后）。

各中间件的钩子、生效条件与完整顺序以 [middleware 执行流程](../../backend/docs/middleware-execution-flow.md)为权威；本节不复制该清单。

### 配置系统

**主配置**（`config.yaml`）：

设置：将 `config.example.yaml` 复制为项目根目录下的 `config.yaml`。

**配置版本管理**：`config.example.yaml` 包含 `config_version` 字段。启动时，`AppConfig.from_file()` 会比较用户版本和示例版本，若用户配置过旧则发出警告。缺失 `config_version` 表示版本 0。运行 `make config-upgrade` 可自动合并缺失字段。变更配置 schema 时，需要提升 `config.example.yaml` 中的 `config_version`。

**配置缓存**：`get_app_config()` 会缓存解析后的配置，但当解析出的配置路径变化或文件 mtime 增大时会自动重新加载。这样 Gateway 和 LangGraph 对 `config.yaml` 的读取可与配置编辑保持一致，无需手动重启进程。

配置优先级：

1. 显式 `config_path` 参数
2. `DEER_FLOW_CONFIG_PATH` 环境变量
3. 调用方项目根目录中的 `config.yaml`
4. 兼容 monorepo 的 legacy backend/仓库根目录位置（项目根目录为**推荐位置**）

以 `$` 开头的配置值会被解析为环境变量（例如 `$OPENAI_API_KEY`）。`ModelConfig` 还声明了 `use_responses_api` 和 `output_version`，因此在继续使用 `langchain_openai:ChatOpenAI` 的同时，也可以显式启用 OpenAI `/v1/responses`。

**扩展配置**（`extensions_config.json`）：

MCP 服务器和技能在项目根目录的 `extensions_config.json` 中共同配置：

配置优先级：

1. 显式 `config_path` 参数
2. `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 环境变量
3. 调用方项目根目录中的 `extensions_config.json`
4. 兼容 monorepo 的 legacy 位置（项目根目录为**推荐位置**）

### Gateway API（`backend/app/gateway/`）

FastAPI 应用运行在端口 8001，健康检查为 `GET /health`。生产环境可设置 `GATEWAY_ENABLE_DOCS=false` 禁用 `/docs`、`/redoc` 和 `/openapi.json`（默认启用）。

当请求通过端口 2026 的 nginx 进入时，CORS 默认为同源。拆分源或端口转发的浏览器客户端必须通过 `GATEWAY_CORS_ORIGINS`（逗号分隔的精确 origin）显式允许；Gateway 的 `CORSMiddleware` 和 `CSRFMiddleware` 都读取该变量，因此浏览器 CORS 与认证 origin 检查会保持一致。

**路由**：

| Router                                                | Endpoints                                                                                                                                                                                                                                                                                 |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Models**（`/api/models`）                             | `GET /`：列出模型；`GET /{name}`：模型详情                                                                                                                                                                                                                                                           |
| **MCP**（`/api/mcp`）                                   | `GET /config`：获取配置；`PUT /config`：更新配置（保存到 extensions_config.json）                                                                                                                                                                                                                         |
| **Resources**（`/api/resources`）                       | Skill、Agent、Workflow 统一资源目录（canonical）：`GET /` 列表；`POST /` 创建（agent-draft/publish）；`GET /{id}/published`、`GET /{id}/export`；`PUT /{id}/agent-draft`、`PUT /{id}/workflow-draft`、`PUT /{id}/archive-draft`；`POST /{id}/publish`、`/fork`、`/archive`、`/suspend`、`/restore`、`/transfer`、`/visibility-applications`、`/favorite`（DELETE 取消）；`PUT /{id}/visibility`、`PUT /{id}/dependencies`；`GET /aliases/{type}/{slug}` 旧名称解析；`GET /notifications`；`POST /import/agent`。`/api/workflows` 旧路由已删除；`/api/agents`（自定义 Agent 管理）与 `/api/skills/custom*` 管理路由仍以 legacy 形式存在（`backend/app/gateway/routers/agents.py`、`skills.py`）                                                                                                                                                 |
| **Memory**（`/api/memory`）                             | `GET /`：记忆数据；`POST /reload`：强制重新加载；`GET /config`：配置；`GET /status`：配置 + 数据                                                                                                                                                                                                                 |
| **Uploads**（`/api/threads/{id}/uploads`）              | `POST /`：上传文件（自动转换 PDF/PPT/Excel/Word）；`GET /list`：列表；`DELETE /{filename}`：删除                                                                                                                                                                                                             |
| **Threads**（`/api/threads/{id}`）                      | `DELETE /`：在 LangGraph 删除线程后移除 iDeer 管理的本地线程数据；意外失败会在服务端记录日志，并返回通用 500 detail                                                                                                                                                                                                          |
| **Artifacts**（`/api/threads/{id}/artifacts`）          | `GET /{path}`：提供 artifact；活跃内容类型（`text/html`、`application/xhtml+xml`、`image/svg+xml`）始终强制作为下载附件，以降低 XSS 风险；`?download=true` 对其他文件类型仍会强制下载                                                                                                                                                 |
| **Suggestions**（`/api/threads/{id}/suggestions`）      | `POST /`：生成后续问题；富列表/块模型内容会在 JSON 解析前规范化                                                                                                                                                                                                                                                   |
| **Thread Runs**（`/api/threads/{id}/runs`）             | `POST /`：创建后台 run；`POST /stream`：创建 + SSE 流；`POST /wait`：创建 + 阻塞等待；`GET /`：列出 run；`GET /{rid}`：run 详情；`POST /{rid}/cancel`：取消；`GET /{rid}/join`：加入 SSE；`GET /{rid}/messages`：分页消息 `{data, has_more}`；`GET /{rid}/events`：完整事件流；`GET /../messages`：带反馈的线程消息；`GET /../token-usage`：聚合 token |
| **Feedback**（`/api/threads/{id}/runs/{rid}/feedback`） | `PUT /`：upsert 反馈；`DELETE /`：删除用户反馈；`POST /`：创建反馈；`GET /`：列出反馈；`GET /stats`：聚合统计；`DELETE /{fid}`：删除指定反馈                                                                                                                                                                                   |
| **Runs**（`/api/runs`）                                 | `POST /stream`：无状态 run + SSE；`POST /wait`：无状态 run + 阻塞等待；`GET /{rid}/messages`：按 run_id 获取分页消息 `{data, has_more}`（游标：`after_seq`/`before_seq`）；`GET /{rid}/feedback`：按 run_id 列出反馈                                                                                                        |

**RunManager / RunStore 契约**：
- `RunManager.get()` 是异步方法；直接调用方必须使用 `await`。
- 配置持久化 `RunStore` 时，`get()` 和 `list_by_thread()` 会从 store 补水历史 run。对于相同 `run_id`，内存记录优先，因此任务、abort 和流控制状态会继续绑定到活跃的本地 run。
- `cancel()` 和 `create_or_reject(..., multitask_strategy="interrupt"|"rollback")` 会通过 `RunStore.update_status()` 持久化 interrupted 状态，与普通 `set_status()` 状态迁移保持一致。
- 仅从 store 补水出来的 run 是可读历史。如果当前 worker 没有该 run 的内存任务/控制状态，取消 API 可能返回 409，因为这个 worker 无法停止该任务。

经 nginx 代理：`/api/langgraph/*` → Gateway LangGraph 兼容运行时，其他 `/api/*` → Gateway REST API。

### 沙箱系统（`packages/harness/deerflow/sandbox/`）

**接口**：抽象 `Sandbox`，包含 `execute_command`、`read_file`、`write_file`、`list_dir`

**Provider 模式**：`SandboxProvider`，包含 `acquire`、`get`、`release` 生命周期

**实现**：

- `LocalSandboxProvider`（`sandbox/local/local_sandbox_provider.py`）：本地文件系统执行。`acquire(thread_id, *, user_id)` 返回线程级 `LocalSandbox`（id 为 `local:{user_id}:{thread_id}`），其 `path_mappings` 将 `/mnt/user-data/{workspace,uploads,outputs}` 和 `/mnt/acp-workspace` 解析到该线程的宿主机目录，因此公共 `Sandbox` API 与 AIO 一样统一遵守 `/mnt/user-data` 契约。`acquire()` / `acquire(None)` 保留旧的通用单例（id 为 `local`），用于没有线程上下文的调用方。线程级沙箱保存在一个由 `threading.Lock` 保护的 LRU 缓存中（默认 256 项）。
- `AioSandboxProvider`（`packages/harness/deerflow/community/`）：基于 Docker 的隔离

**虚拟路径系统**：

- 智能体看到：`/mnt/user-data/{workspace,uploads,outputs}`、`/mnt/skills`
- 物理路径：`{base_dir}/users/{user_id}/threads/{thread_id}/user-data/...`（未提供 `user_id` 时为 legacy `{base_dir}/threads/{thread_id}/...`；`base_dir` 默认 `backend/.deer-flow`，可用 `DEER_FLOW_HOME` 覆盖）、项目根目录 `skills/`
- 翻译：`LocalSandboxProvider` 在 acquire 时为 user-data 前缀构建线程级 `PathMapping`；`tools.py` 保留 `replace_virtual_path()` / `replace_virtual_paths_in_command()` 作为纵深防御层（也用于路径校验）。AIO 在容器内部将目录挂载到相同虚拟路径，因此两种实现都可以原生接受 `/mnt/user-data/...`。
- 检测：`is_local_sandbox()` 同时接受 `sandbox_id == "local"`（旧模式/无线程）和 `sandbox_id.startswith("local:")`（线程级）

**沙箱工具**（位于 `packages/harness/deerflow/sandbox/tools.py`）：

- `bash`：执行命令，并进行路径翻译和错误处理
- `ls`：目录列表（树形格式，最多 2 层）
- `glob` / `grep`：按模式搜索文件 / 按关键词搜索文件内容
- `read_file`：读取文件内容，支持可选行范围
- `write_file`：写入/追加文件，创建目录；默认覆盖，并在面向模型的 schema 中暴露 `append` 参数以支持文件末尾写入
- `str_replace`：子串替换（单次或全部出现）；同一路径串行化的作用域为 `(sandbox.id, path)`，因此隔离沙箱在同一进程内即便虚拟路径相同也不会相互竞争

### 子智能体系统（`packages/harness/deerflow/subagents/`）

**内置智能体**：`general-purpose`（除 `task` 外的所有工具）和 `bash`（命令专家），经 `registry.py` 的 `BUILTIN_SUBAGENTS` 注册，并支持 custom/managed subagent

**并发**：`MAX_CONCURRENT_SUBAGENTS = 3`，由 `SubagentLimitMiddleware` 强制执行（截断过量工具调用）；另有每次 run 的总委托数上限（`subagents.max_total_per_run`，默认范围内可配）与默认超时 `subagents.timeout_seconds`（1800 秒 = 30 分钟，可按 agent 覆盖）

**流程**：`task()` 工具 → `SubagentExecutor` 后台异步执行 → 进度事件 → SSE 事件 → 结果

**事件**：`task_started`、`task_running`、`task_completed`/`task_failed`/`task_timed_out`

### 工具系统（`packages/harness/deerflow/tools/`）

`get_available_tools(groups, include_mcp, model_name, subagent_enabled, ...)` 会组装：

1. **配置定义的工具**：通过 `resolve_variable()` 从 `config.yaml` 解析
2. **MCP 工具**：来自启用的 MCP 服务器（懒初始化，并通过内容签名失效缓存）
3. **内置工具**：
   - `present_files`：让输出文件对用户可见（仅限 `/mnt/user-data/outputs`）
   - `ask_clarification`：请求澄清（由 ClarificationMiddleware 拦截并中断）
   - `view_image`：将图片读取为 base64（仅在模型支持 vision 时添加）
   - `setup_agent`：仅引导阶段使用，通过 canonical 资源目录创建全新自定义智能体。仅在 `is_bootstrap=True` 时绑定。
   - `update_agent`：仅自定义智能体使用，在普通聊天中把当前智能体对自身 `SOUL.md` / `config.yaml` 的更新写入 canonical 资源（draft + publish，按 `agent_name` 解析资源 UUID）。当设置了 `agent_name` 且 `is_bootstrap=False` 时绑定。
   - 另有 `list_uploaded_files`、`list_background_tasks` / `cancel_background_task`、`batch_task` 等批量/后台工具，以及工具搜索（`build_tool_search_tool`，见 `tools/builtins/`）
4. **子智能体工具**（启用时）：
   - `task`：委托给子智能体（description、prompt、subagent_type）

**社区工具**（`packages/harness/deerflow/community/`，当前目录还包括 ragflow、ddg_search、searxng、brave、exa、serper、e2b_sandbox、opensandbox 等）：

- `tavily/`：Web 搜索（默认 5 条结果）和网页抓取（4KB 限制）
- `jina_ai/`：通过 Jina reader API 抓取网页，并做 readability 提取
- `firecrawl/`：通过 Firecrawl API 抓取网页

**ACP 智能体工具**：

- `invoke_acp_agent`：调用 `config.yaml` 中配置的外部 ACP 兼容智能体
- ACP launcher 必须是真正的 ACP adapter。标准 `codex` CLI 本身不兼容 ACP；需要配置 wrapper，例如 `npx -y @zed-industries/codex-acp` 或已安装的 `codex-acp` 二进制
- 缺失 ACP 可执行文件时，现在会返回可操作的错误信息，而不是原始 `[Errno 2]`
- 每个 ACP 智能体使用线程级工作区 `{base_dir}/users/{user_id}/threads/{thread_id}/acp-workspace/`（未提供 `user_id` 时为 legacy `{base_dir}/threads/{thread_id}/acp-workspace/`；更早的全局 `{base_dir}/acp-workspace/` 仅作回退）。主智能体可通过虚拟路径 `/mnt/acp-workspace/` 以只读方式访问该工作区。在 docker 沙箱模式下，该目录会以只读方式挂载到容器的 `/mnt/acp-workspace`；在本地沙箱模式下，路径翻译由 `tools.py` 处理
- `image_search/`：通过 DuckDuckGo 进行图片搜索

### MCP 系统（`packages/harness/deerflow/mcp/`）

- 使用 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 管理多服务器
- **懒初始化**：首次使用时通过 `get_cached_mcp_tools()` 加载工具
- **缓存失效**：通过配置文件的内容签名（`(mtime, size, sha256)`）检测变更，避免同秒编辑或 mtime 回退导致漏检
- **传输方式**：stdio（基于命令）、SSE、HTTP
- **OAuth（HTTP/SSE）**：支持 token endpoint 流程（`client_credentials`、`refresh_token`），带自动 token 刷新和 Authorization header 注入
- **运行时更新**：Gateway API 保存到 extensions_config.json；LangGraph 通过内容签名检测

### 技能系统（`packages/harness/deerflow/skills/`）

- **位置**：项目根目录 `skills/`（默认；可经 `skills.path` 配置，容器路径经 `skills.container_path`）。技能经可配置的 `SkillStorage`（默认 `LocalSkillStorage`）与 canonical 资源目录管理，见 `resources/` 模块
- **格式**：包含 `SKILL.md` 的目录（YAML frontmatter：name、description、license、allowed-tools）
- **加载**：`SkillStorage.load_skills()` 发现并解析技能元数据，读取启用状态后注入智能体系统提示词（含容器路径）
- **管理**：Skill 的创建、发布、可见性、归档、下架、Fork 走 `/api/resources`（`/api/skills/custom*` 管理路由以 legacy 形式保留）

### 模型工厂（`packages/harness/deerflow/models/factory.py`）

- `create_chat_model(name, thinking_enabled)` 通过反射从配置实例化 LLM
- 支持 `thinking_enabled` 标志和按模型设置的 `when_thinking_enabled` 覆盖
- 支持 vLLM 风格 thinking 开关：通过 `when_thinking_enabled.extra_body.chat_template_kwargs.enable_thinking` 启用 Qwen 推理模型；同时会规范化旧版 `thinking` 配置以保持向后兼容
- 支持 `supports_vision` 标志，用于图片理解模型
- 以 `$` 开头的配置值会被解析为环境变量
- 缺失 provider 模块时，reflection resolver 会给出可操作的安装提示（例如 `uv add langchain-google-genai`）

### vLLM Provider（`packages/harness/deerflow/models/vllm_provider.py`）

- `VllmChatModel` 继承 `langchain_openai:ChatOpenAI`，用于 vLLM 0.19.0 OpenAI 兼容端点
- 在完整响应、流式 delta 和后续工具调用轮次中保留 vLLM 非标准的 assistant `reasoning` 字段
- 面向在 vLLM 0.19.0 Qwen 推理模型上通过 `extra_body.chat_template_kwargs.enable_thinking` 启用 thinking 的配置设计，同时也接受旧版 `thinking` 别名

### IM 渠道系统（`app/channels/`）

该系统将外部消息平台（飞书、Slack、Telegram、钉钉、Discord、微信、企业微信/WeCom、GitHub、Buzz/Nostr）通过 Gateway 的 LangGraph 兼容 API 连接到 iDeer 智能体。

**架构**：渠道通过 `langgraph-sdk` HTTP 客户端（与前端相同）与 Gateway 通信，确保线程在服务端创建和管理。内部 SDK 客户端会注入进程本地内部认证，以及匹配的 CSRF cookie/header 对，使 Gateway 可以接受来自渠道 worker 的状态变更线程/run 请求，而不依赖浏览器 session cookie。

**组件**：

- `message_bus.py`：异步发布/订阅 hub（`InboundMessage` → queue → dispatcher；`OutboundMessage` → callbacks → channels）
- `store.py`：JSON 文件持久化，将 `channel_name:chat_id[:topic_id]` 映射到 `thread_id`（根会话键为 `channel:chat`，线程会话键为 `channel:chat:topic`）
- `manager.py`：核心 dispatcher：通过 `client.threads.create()` 创建线程，路由命令，使 Slack/Telegram 使用 `client.runs.wait()`，并让飞书通过 `client.runs.stream(["messages-tuple", "values"])` 做增量外发更新
- `base.py`：抽象 `Channel` 基类（start/stop/send 生命周期）
- `service.py`：从 `config.yaml` 管理所有已配置渠道的生命周期
- `slack.py` / `feishu.py` / `telegram.py` / `dingtalk.py` / `discord.py` / `wechat.py` / `wecom.py` / `github.py` / `buzz.py`：平台专用实现（`feishu.py` 在内存中跟踪运行中的卡片 `message_id`，并原地 patch 同一张卡片；配置 `card_template_id` 时，`dingtalk.py` 可选使用 AI Card streaming 进行原地更新；另有 `run_policy.py`、`dedupe_store.py`、`connection_identity.py` 等共享策略组件）

**消息流程**：

1. 外部平台 → Channel 实现 → `MessageBus.publish_inbound()`
2. `ChannelManager._dispatch_loop()` 从队列消费
3. 对于聊天：通过 Gateway 的 LangGraph 兼容 API 查找/创建线程
4. 飞书聊天：`runs.stream()` → 累积 AI 文本 → 发布多次外发更新（`is_final=False`）→ 发布最终外发（`is_final=True`）
5. Slack/Telegram 聊天：`runs.wait()` → 提取最终响应 → 发布外发
6. 飞书渠道先发送一张运行中回复卡片，然后对每次外发更新 patch 同一张卡片（卡片 JSON 设置 `config.update_multi=true` 以满足飞书 patch API 要求）
7. 钉钉 AI Card 模式（配置了 `card_template_id` 时）：`runs.stream()` → 使用初始文本创建卡片 → 通过 `PUT /v1.0/card/streaming` 流式更新 → 在 `is_final=True` 时结束。若创建卡片或 streaming 失败，则回退到 `sampleMarkdown`
8. 对命令（`/new`、`/status`、`/models`、`/memory`、`/help`）：本地处理或查询 Gateway API
9. 外发 → channel callbacks → 平台回复

**配置**（`config.yaml` → `channels`）：

- `langgraph_url`：LangGraph 兼容 Gateway API 基础 URL（默认：`http://localhost:8001/api`）
- `gateway_url`：用于辅助命令的 Gateway API URL（默认：`http://localhost:8001`）
- 在 Docker Compose 中，IM 渠道运行在 `gateway` 容器内，因此 `localhost` 指回该容器。`langgraph_url` 使用 `http://gateway:8001/api`，`gateway_url` 使用 `http://gateway:8001`，或设置 `DEER_FLOW_CHANNELS_LANGGRAPH_URL` / `DEER_FLOW_CHANNELS_GATEWAY_URL`
- 各渠道配置：`feishu`（app_id、app_secret）、`slack`（bot_token、app_token）、`telegram`（bot_token）、`dingtalk`（client_id、client_secret，可选 `card_template_id` 用于 AI Card streaming）

### 记忆系统（`packages/harness/deerflow/agents/memory/`）

**架构**：backend 中立的记忆管理器 `MemoryManager`（`manager.py`）+ 可插拔存储 backend（`backends/`：`deermem`、`honcho`、`mem0`、`openviking`、`noop`），由 `memory.manager_class` 配置选择；backend 私有参数集中在 `memory.backend_config`。记忆按 `(agent_name, user_id)` 分桶，`thread_id` 对齐会话线程；契约只约定 `add` / `add_nowait` / `get_context` 等分层方法，不假设具体数据模型（backend 可以完全不存"事实"）。

**接入点**：

- 写入：`MemoryMiddleware`（`after_agent`）把对话交给 manager（`memory.enabled` 时挂载，`agent_name` 显式传入）
- 注入：`DynamicContextMiddleware` 在 `memory.injection_enabled` 时把 `<memory>` 上下文作为 system-reminder 注入；提示词组装亦会调用 `get_memory_manager().get_context(...)`

DeerMem backend 的聚焦回归覆盖位于 `backend/tests/test_memory_updater.py`。

**用户隔离**：

- `user_id` 通过 `deerflow.runtime.user_context` 的 `get_effective_user_id()` 解析；无认证模式下默认 `"default"`（`DEFAULT_USER_ID`）
- `memory.mode` 选择运行方式：`middleware`（每轮后被动 LLM 总结，当前默认行为）或 `tool`（模型直接调用 memory_search/memory_add 等记忆工具，二者互斥）；backend 内部按 `(agent_name, user_id)` 分桶持久化

**配置**（`config.yaml` → `memory`）：

- `enabled` / `injection_enabled`：写入与注入主开关
- `manager_class`：backend 选择器（注册 backend 名如 `deermem` / `noop`，或 `MemoryManager` 子类的点分导入路径；默认 `deermem`）
- `backend_config`：backend 私有配置（DeerMem 的字段见 `backends/deermem/config.py`）
- 旧版字段（`debounce_seconds`、`model_name`、`max_facts`、`max_injection_tokens`、`storage_path` 等）不再直接生效，升级时会被映射进 `backend_config` 以免静默丢失自定义设置

**迁移**：旧的非隔离布局（`{base_dir}/memory.json`、`{base_dir}/threads/`、`{base_dir}/agents/`）仅作为读侧回退保留；一次性迁移脚本 `backend/scripts/migrate_user_isolation.py`（支持 `--dry-run` 与 `--user-id`）将其迁入按用户隔离布局 `{base_dir}/users/{user_id}/...`。

### 反射系统（`packages/harness/deerflow/reflection/`）

- `resolve_variable(path)`：导入模块并返回变量（例如 `module.path:variable_name`）
- `resolve_class(path, base_class)`：导入并按基类校验类

### 配置 Schema

**`config.yaml`** 关键部分：

- `models[]`：LLM 配置，包含 `use` 类路径、`supports_thinking`、`supports_vision`、provider 专用字段
- vLLM 推理模型应使用 `deerflow.models.vllm_provider:VllmChatModel`；对于 Qwen 风格 parser，优先使用 `when_thinking_enabled.extra_body.chat_template_kwargs.enable_thinking`，iDeer 也会规范化旧版 `thinking` 别名
- `tools[]`：工具配置，包含 `use` 变量路径和 `group`
- `tool_groups[]`：工具逻辑分组
- `sandbox.use`：沙箱 provider 类路径
- `skills.path` / `skills.container_path`：技能目录的宿主机路径和容器路径
- `title`：自动标题生成（enabled、max_words、max_chars、prompt_template）
- `summarization`：上下文摘要（enabled、触发条件、保留策略）
- `subagents.enabled`：子智能体委托主开关
- `memory`：记忆系统（enabled、mode、injection_enabled、manager_class、backend_config；旧版字段升级时映射进 backend_config）

**`extensions_config.json`**：

- `mcpServers`：服务器名称到配置的映射（enabled、type、command、args、env、url、headers、oauth、description）
- `skills`：技能名称到状态（enabled）的映射

两者都可通过 Gateway API 端点或 `DeerFlowClient` 方法在运行时修改。

### 嵌入式客户端（`packages/harness/deerflow/client.py`）

`DeerFlowClient` 提供不经过 HTTP 服务、在进程内直接访问全部 iDeer 能力的方式。所有返回类型都与 Gateway API 响应 schema 对齐，因此消费代码在 HTTP 和嵌入模式下可以保持一致。

**架构**：导入与 Gateway API 相同的 `deerflow` 模块。共享同一套配置文件和数据目录。没有 FastAPI 依赖。

**智能体对话**：

- `chat(message, *, thread_id)`：同步方法，按 message-id 累积流式 delta，并返回最终 AI 文本
- `stream(message, thread_id)`：订阅 LangGraph `stream_mode=["values", "messages", "custom"]` 并产出 `StreamEvent`：
  - `"values"`：完整状态快照（title、messages、artifacts）；通过 `messages` 模式已经交付的 AI 文本不会在这里重新合成，以避免重复交付
  - `"messages-tuple"`：逐 chunk 更新；对 AI 文本而言这是 **delta**（按 `id` 拼接可重建完整消息）；工具调用和工具结果各发出一次
  - `"custom"`：从 `StreamWriter` 转发
  - `"end"`：流结束（携带按 message id 去重统计的累计 `usage`）
- 智能体通过 `create_agent()` + `_build_middlewares()` 懒创建，与 `make_lead_agent` 相同
- 支持 `checkpointer` 参数，用于跨轮次持久化状态
- `reset_agent()` 强制重建智能体（例如记忆或技能变更后）
- 完整设计见 [docs/STREAMING.md](../../backend/docs/STREAMING.md)：说明 Gateway 和 DeerFlowClient 为什么是并行路径、LangGraph 的 `stream_mode` 语义、按 id 去重的不变量以及回归测试策略

**Gateway 等价方法**（替代 Gateway API）：

| Category  | Methods                                                                                         | Return format                                                      |
| --------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Models    | `list_models()`、`get_model(name)`                                                               | `{"models": [...]}`、`{name, display_name, ...}`                    |
| MCP       | `get_mcp_config()`、`update_mcp_config(servers)`                                                 | `{"mcp_servers": {...}}`                                           |
| Skills    | `list_skills()`、`get_skill(name)`、`update_skill(name, enabled)`、`install_skill(path)`           | `{"skills": [...]}`                                                |
| Memory    | `get_memory()`、`reload_memory()`、`get_memory_config()`、`get_memory_status()`                    | dict                                                               |
| Uploads   | `upload_files(thread_id, files)`、`list_uploads(thread_id)`、`delete_upload(thread_id, filename)` | `{"success": true, "files": [...]}`、`{"files": [...], "count": N}` |
| Artifacts | `get_artifact(thread_id, path)` → `(bytes, mime_type)`                                          | tuple                                                              |

**与 Gateway 的关键区别**：Upload 接受本地 `Path` 对象而不是 HTTP `UploadFile`，在复制前拒绝目录路径，并且当文档转换必须在活动事件循环中运行时复用单个 worker。Artifact 返回 `(bytes, mime_type)` 而不是 HTTP Response。Gateway-only 线程清理路由会在 LangGraph 删除线程后删除本地线程目录（`{base_dir}/users/{user_id}/threads/{thread_id}/`）；目前还没有对应的 `DeerFlowClient` 方法。`update_mcp_config()` 和 `update_skill()` 会自动使缓存的智能体失效。

**测试**：`tests/test_client.py`（单元测试，包含 `TestGatewayConformance`）、`tests/test_client_live.py`（实时集成测试，需要 config.yaml）

**Gateway 一致性测试**（`TestGatewayConformance`）：验证每个返回 dict 的客户端方法都符合对应的 Gateway Pydantic 响应模型。每个测试都会用 Gateway 模型解析客户端输出。如果 Gateway 新增了客户端未提供的必填字段，Pydantic 会抛出 `ValidationError`，CI 会捕获漂移。覆盖：`ModelsListResponse`、`ModelResponse`、`SkillsListResponse`、`SkillResponse`、`SkillInstallResponse`、`McpConfigResponse`、`UploadResponse`、`MemoryConfigResponse`、`MemoryStatusResponse`。

## 开发工作流

### 测试驱动开发（TDD）——强制

**每个新功能或 bug 修复都必须附带单元测试。没有例外。**

- 按现有命名约定 `test_<feature>.py` 在 `backend/tests/` 中编写测试
- 每个 TDD 切片只运行聚焦回归测试和最窄相关的静态检查；标准 lane 在实现完成时运行一次（lane 选择与交接见 [测试 Lane 运行手册](../testing/test-lane-runbook.md)）
- 测试必须通过，功能才算完成
- 对轻量级配置/工具模块，优先使用无外部依赖的纯单元测试
- 如果某个模块在测试中导致循环导入问题，在 `tests/conftest.py` 中添加 `sys.modules` mock（参考 `deerflow.subagents.executor` 的现有示例）

```bash
# 运行全部测试
make test

# 运行指定测试文件
PYTHONPATH=. uv run pytest tests/test_<feature>.py -v
```

### 运行完整应用

从**项目根目录**执行：

```bash
make dev
```

这会启动所有服务，并在 `http://localhost:2026` 提供应用访问。

**所有启动模式：**

|          | **本地前台**                                     | **本地守护进程**                                                   | **Docker Dev**                                      | **Docker Prod**                     |
| -------- | -------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------- | ----------------------------------- |
| **Dev**  | `./scripts/serve.sh --dev`<br/>`make dev`    | `./scripts/serve.sh --dev --daemon`<br/>`make dev-daemon`    | `./scripts/docker.sh start`<br/>`make docker-start` | —                                   |
| **Prod** | `./scripts/serve.sh --prod`<br/>`make start` | `./scripts/serve.sh --prod --daemon`<br/>`make start-daemon` | —                                                   | `./scripts/deploy.sh`<br/>`make up` |

| Action      | Local                                       | Docker Dev                                        | Docker Prod                                |
| ----------- | ------------------------------------------- | ------------------------------------------------- | ------------------------------------------ |
| **Stop**    | `./scripts/serve.sh --stop`<br/>`make stop` | `./scripts/docker.sh stop`<br/>`make docker-stop` | `./scripts/deploy.sh down`<br/>`make down` |
| **Restart** | `./scripts/serve.sh --restart [flags]`      | `./scripts/docker.sh restart`                     | —                                          |

**Nginx 路由**：

- `/api/langgraph/*` → Gateway 嵌入式运行时（8001），重写到 `/api/*`
- `/api/*`（其他）→ Gateway API（8001）
- `/`（非 API）→ Frontend（3000）

### 单独运行后端服务

从 **backend** 目录执行：

```bash
# Gateway API
make gateway
```

直接访问（不经过 nginx）：

- Gateway：`http://localhost:8001`

### 前端配置

前端使用环境变量连接后端服务：

- `NEXT_PUBLIC_LANGGRAPH_BASE_URL`：默认 `/api/langgraph`（经 nginx）
- `NEXT_PUBLIC_BACKEND_BASE_URL`：默认空字符串（经 nginx）

从根目录使用 `make dev` 时，前端会自动通过 nginx 连接。

## 关键功能

### 文件上传

支持多文件上传和自动文档转换：

- 端点：`POST /api/threads/{thread_id}/uploads`
- 支持：PDF、PPT、Excel、Word 文档（通过 `markitdown` 转换）
- 复制前拒绝目录输入，因此上传保持全有或全无
- 从活动事件循环调用时，每个请求复用一个转换 worker
- 文件存储在线程隔离目录中
- 单个上传请求中的重复文件名会自动追加 `_N` 后缀重命名，避免后面的文件截断前面的文件
- 智能体通过 `UploadsMiddleware` 接收上传文件列表

详情见 [docs/FILE_UPLOAD.md](../../backend/docs/FILE_UPLOAD.md)。

### Plan Mode

用于复杂多步骤任务的 TodoList 中间件：

- 通过运行时配置控制：`config.configurable.is_plan_mode = True`
- 提供 `write_todos` 工具用于任务跟踪
- 同一时间只有一个任务处于 in_progress，并实时更新

详情见 [docs/plan_mode_usage.md](../../backend/docs/plan_mode_usage.md)。

### 上下文摘要

接近 token 限制时自动进行对话摘要：

- 在 `config.yaml` 的 `summarization` key 下配置
- 触发类型：tokens、messages 或最大输入比例
- 摘要较早消息，同时保留最近消息

详情见 [docs/summarization.md](../../backend/docs/summarization.md)。

### 视觉支持

对于 `supports_vision: true` 的模型：

- `ViewImageMiddleware` 处理对话中的图片
- 将 `view_image_tool` 添加到智能体工具集
- 图片自动转换为 base64 并注入状态

## 代码风格

- 使用 `ruff` 进行 lint 和格式化
- 行长度：240 字符
- Python 3.12+，使用类型标注
- 双引号、空格缩进

## 文档

详细文档见 `docs/` 目录：

- [CONFIGURATION.md](../../backend/docs/CONFIGURATION.md)：配置选项
- [ARCHITECTURE.md](../../backend/docs/ARCHITECTURE.md)：架构详情
- [API.md](../../backend/docs/API.md)：API 参考
- [SETUP.md](../../backend/docs/SETUP.md)：安装指南
- [FILE_UPLOAD.md](../../backend/docs/FILE_UPLOAD.md)：文件上传功能
- [PATH_EXAMPLES.md](../../backend/docs/PATH_EXAMPLES.md)：路径类型和用法
- [summarization.md](../../backend/docs/summarization.md)：上下文摘要
- [plan_mode_usage.md](../../backend/docs/plan_mode_usage.md)：带 TodoList 的 Plan 模式
