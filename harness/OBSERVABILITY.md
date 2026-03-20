# 可观测性规范

## 日志体系

项目有两套日志系统，面向不同场景：

| 系统 | 类 | 输出位置 | 粒度 | 用途 |
|------|------|----------|------|------|
| AgentLogger | `core/agent_logger.py` | `~/.omni-agent/log/` | 单 Agent 运行 | 调试单次执行 |
| TraceLogger | `core/trace_logger.py` | `~/.omni-agent/traces/` | 多 Agent 工作流 | 分析协作链路 |

## AgentLogger

### 日志事件类型

| 事件 | 记录内容 | 触发时机 |
|------|----------|----------|
| `STEP` | 步骤号、Token 用量统计、Token 使用百分比 | 每步开始 |
| `REQUEST` | 用户消息或工具调用请求 | LLM 调用前 |
| `RESPONSE` | LLM 响应内容、thinking 过程 | LLM 调用后 |
| `TOOL_EXECUTION` | 工具名、参数、结果、执行时间(ms) | 工具执行后 |
| `COMPLETION` | 最终回答、总步数、Token 总结 | 运行结束 |

### 文件命名

```
~/.omni-agent/log/agent_run_YYYYMMDD_HHMMSS.log
```

### 启用方式

默认启用。通过 Agent 构造参数控制：

```python
agent = Agent(
    llm_client=llm,
    tools=tools,
    enable_logging=True,   # 默认 True
)
```

### 查看日志

```bash
ls -lht ~/.omni-agent/log/ | head -5
cat ~/.omni-agent/log/agent_run_20260319_143022.log
```

## TraceLogger

### 追踪事件

| 事件 | 说明 |
|------|------|
| workflow_start | 工作流开始 |
| workflow_end | 工作流结束 |
| agent_spawn | Agent 创建（含嵌套深度） |
| agent_complete | Agent 执行完成 |
| delegation | Leader 向 Member 委派任务 |
| task_dependency | 任务依赖关系 |

### 文件格式

JSONL 格式，每行一个事件：

```
~/.omni-agent/traces/trace_team_YYYYMMDD_*.jsonl
```

### 查看追踪

使用 `trace_viewer` 工具：

```bash
uv run python -m omni_agent.utils.trace_viewer list
uv run python -m omni_agent.utils.trace_viewer view <trace_file>
uv run python -m omni_agent.utils.trace_viewer flow <trace_file>
```

## 事件系统 (EventEmitter)

Agent 执行过程中通过 EventEmitter 发出结构化事件：

| EventType | 触发时机 | data 字段 |
|-----------|----------|-----------|
| `STEP_START` | 每步开始 | step, token_usage |
| `STEP_END` | 每步结束 | step, duration |
| `LLM_REQUEST` | LLM 调用前 | messages_count |
| `LLM_RESPONSE` | LLM 响应后 | content, tool_calls, tokens |
| `TOOL_START` | 工具执行前 | tool_name, arguments |
| `TOOL_END` | 工具执行后 | tool_name, result, duration |
| `COMPLETION` | 运行结束 | message, total_steps |
| `CANCELLED` | 运行取消 | reason |
| `ERROR` | 运行出错 | error |
| `TOKEN_SUMMARY` | Token 压缩 | before, after, ratio |

### 订阅事件

```python
async def on_tool_end(event: AgentEvent):
    if event.data["duration"] > 10:
        logger.warning("Slow tool: %s took %.1fs", event.data["tool_name"], event.data["duration"])

agent.emitter.on(EventType.TOOL_END, on_tool_end)
```

## Langfuse 集成

可选的外部可观测性平台，通过 `LangfuseTracer` (`core/langfuse_tracing.py`) 集成：

- 自动上报 LLM 调用、工具执行、Token 用量
- 通过环境变量启用：`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

## 调试方法

### 定位 Agent 执行问题

1. 查看最近日志，找到对应运行

```bash
ls -lht ~/.omni-agent/log/ | head -3
```

2. 搜索关键事件

```bash
grep "TOOL_EXECUTION" ~/.omni-agent/log/agent_run_*.log | grep -i "error"
grep "TOKEN_SUMMARY" ~/.omni-agent/log/agent_run_*.log
```

3. 检查 Token 使用趋势

日志中 `STEP` 事件包含累计 Token 数和百分比，可判断是否接近压缩阈值。

### 定位多 Agent 协作问题

1. 找到对应 trace 文件

```bash
uv run python -m omni_agent.utils.trace_viewer list
```

2. 查看执行流

```bash
uv run python -m omni_agent.utils.trace_viewer flow <trace_file>
```

3. 关注委派链是否合理、是否有 Agent 执行超时

### 定位 MCP 工具问题

1. 检查启动时加载日志

```bash
grep "MCP" /tmp/mcp_init_debug.log
```

2. 检查工具列表

```bash
curl http://localhost:8000/api/v1/tools/
```

### 定位 Token 溢出

1. 查看 `TOKEN_SUMMARY` 事件，确认压缩是否触发
2. 检查 System Prompt 长度（过长会挤压对话空间）
3. 检查工具输出是否超过 `output_limit`

## 监控 API

### 活跃运行

```bash
curl http://localhost:8000/api/v1/agent/runs/active
```

### 取消运行

```bash
curl -X POST http://localhost:8000/api/v1/agent/cancel \
  -H "Content-Type: application/json" \
  -d '{"run_id": "<run_id>"}'
```

## 开发规范

### 新增组件的日志要求

- 使用标准 `logging` 模块，不使用 `print`
- Logger 命名跟随模块路径：`logger = logging.getLogger(__name__)`
- 关键操作记录 INFO 级别
- 错误记录 ERROR 级别，包含异常栈
- 调试信息记录 DEBUG 级别

### 新增 Agent 模式的追踪要求

- 必须在 TraceLogger 中记录 workflow_start/workflow_end
- Agent 创建/完成事件必须记录
- 委派/通信事件必须记录
- Token 用量必须可聚合
