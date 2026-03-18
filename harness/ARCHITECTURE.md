# Omni Agent - 系统架构设计

## 系统分层

```text
+----------------------------------------------------------+
|                    API Layer (FastAPI)                     |
|  api/v1/endpoints/ - REST + SSE + ACP 协议端点             |
+----------------------------------------------------------+
|                    Core Layer                             |
|  Agent / Team / MsgHub / Ralph / Session / TokenManager   |
+----------------------------------------------------------+
|                    Tool Layer                             |
|  BaseTool / MCP Loader / Skills / SpawnAgent / RAG        |
+----------------------------------------------------------+
|                    Service Layer                          |
|  LLM Client (LiteLLM) / Embedding / Sandbox / Storage    |
+----------------------------------------------------------+
```

### 各层职责

| 层级 | 目录 | 职责 |
|------|------|------|
| API | `src/omni_agent/api/` | HTTP 路由、依赖注入、请求/响应序列化 |
| Core | `src/omni_agent/core/` | Agent 执行循环、多 Agent 协作、会话管理、Token 控制 |
| Tool | `src/omni_agent/tools/` | 工具基类、工具注册、MCP 加载、技能系统 |
| Service | `src/omni_agent/rag/`, `sandbox/`, `acp/` | 外部服务集成（RAG、沙箱、ACP） |

## 核心组件关系

```text
                    +---------+
                    |  Agent  |
                    +----+----+
                         |
          +--------------+--------------+
          |              |              |
     +----+----+   +-----+-----+  +----+----+
     |  Team   |   |  MsgHub   |  |  Ralph  |
     | (委派)  |   | (广播讨论) |  | (迭代)  |
     +----+----+   +-----+-----+  +----+----+
          |              |              |
          +--------------+--------------+
                         |
                  +------+------+
                  | ToolExecutor|
                  +------+------+
                         |
          +--------------+--------------+
          |              |              |
     +----+----+   +-----+-----+  +----+----+
     |BaseTool |   | MCP Tools |  | Skills  |
     +---------+   +-----------+  +---------+
```

### 组件说明

- **Agent**: 单 Agent 执行循环，管理 LLM 调用、工具执行、Token 控制
- **Team**: Leader-Member 模式，Leader 分析任务后委派给 Member 执行
- **MsgHub**: 事件驱动的多 Agent 广播讨论，支持动态加入/退出
- **Ralph**: 迭代式开发模式，同一 Prompt 反复执行直到任务完成

## 数据流

### 单次请求处理

```text
HTTP Request
  -> FastAPI Router
  -> Dependency Injection (LLM Client + Tools)
  -> Agent.run()
     -> TokenManager.check() / summarize()
     -> LLM.call() -> Response
     -> ToolExecutor.execute() -> Result
     -> Loop until complete or max_steps
  -> Return Response + Logs
```

### 多 Agent 协作 (Team)

```text
User Task
  -> Leader Agent 分析任务
  -> delegate_task_to_member(role, task)
  -> Member Agent 独立执行
  -> Member 返回结果
  -> Leader 综合所有结果
  -> 输出最终回答
```

### 流式响应

```text
Agent.run_stream()
  -> SSE EventSource
  -> agent_thought_chunk (思考过程)
  -> tool_call (工具调用开始)
  -> tool_call_update (工具结果)
  -> agent_message_chunk (回复内容)
  -> [complete] (结束)
```

## 模块职责矩阵

| 模块 | 核心类/函数 | 职责 | 依赖 |
|------|------------|------|------|
| `agent.py` | `Agent` | 执行循环、步骤控制 | LLMClient, ToolExecutor, TokenManager |
| `team.py` | `Team` | Leader-Member 委派 | Agent, TraceLogger |
| `msghub.py` | `MsgHub` | 多 Agent 消息广播 | Agent, EventEmitter |
| `ralph.py` | `RalphLoop` | 迭代式执行 | Agent, WorkingMemory, CompletionDetector |
| `token_manager.py` | `TokenManager` | Token 计数与压缩 | tiktoken |
| `llm_client.py` | `LLMClient` | 多 Provider LLM 调用 | LiteLLM |
| `session.py` | `Session` | 会话上下文管理 | SessionStorage |
| `tool_executor.py` | `ToolExecutor` | 工具调度与执行 | BaseTool |
| `agent_logger.py` | `AgentLogger` | 结构化运行日志 | - |
| `trace_logger.py` | `TraceLogger` | 多 Agent 工作流追踪 | - |

## 关键设计决策

### 1. LiteLLM 统一 LLM 接口

选择 LiteLLM 作为 LLM 调用层，支持 100+ Provider，通过 `provider/model` 格式统一模型标识。
自动适配各 Provider 的 `max_tokens` 限制。

### 2. MCP 启动时加载

MCP 工具在 FastAPI lifespan 启动阶段一次性加载，存储在全局变量中，避免每次请求重复初始化。

### 3. Token 管理自动化

TokenManager 在每次 LLM 调用前自动检测 Token 用量，超过阈值（120k）时自动压缩历史消息，
保留用户消息、压缩 Agent 执行轮次，可减少 50-70% Token 使用。

### 4. 工具系统分层加载

工具按优先级加载：BaseTool -> MCP Tools -> Skills，在 `deps.py` 中统一注册，
通过依赖注入传递给 Agent。

### 5. 多 Agent 模式并存

三种协作模式覆盖不同场景：
- Team: 任务分解与委派，适合结构化工作流
- MsgHub: 开放讨论，适合需要多视角的任务
- Ralph: 迭代改进，适合需要渐进完善的任务
