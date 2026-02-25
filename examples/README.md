# Omni Agent 示例

本目录包含框架各功能的使用示例。

## 运行要求

```bash
# 安装依赖
cd /path/to/skill-agents
uv sync

# 设置环境变量
export LLM_API_KEY=your_api_key
export LLM_MODEL=anthropic/claude-3-5-sonnet-20241022
```

## 示例列表

### 基础示例

| 示例 | 描述 | 需要 API |
|------|------|----------|
| [01_basic_agent.py](01_basic_agent.py) | 基础 Agent 使用 | 是 |

### Graph 执行引擎

| 示例 | 描述 | 需要 API |
|------|------|----------|
| [02_graph_basic.py](02_graph_basic.py) | StateGraph 基础用法 | 否 |
| [03_graph_conditional.py](03_graph_conditional.py) | 条件路由 | 否 |
| [04_graph_parallel.py](04_graph_parallel.py) | 并行执行与状态 Reducer | 否 |
| [05_graph_agent_node.py](05_graph_agent_node.py) | AgentNode 封装 | 是 |
| [06_graph_stream.py](06_graph_stream.py) | 流式执行监控 | 否 |

### 多 Agent 协作

| 示例 | 描述 | 需要 API |
|------|------|----------|
| [07_team_collaboration.py](07_team_collaboration.py) | Team Leader-Member 协作 | 是 |

### 沙箱隔离

| 示例 | 描述 | 需要 API |
|------|------|----------|
| [08_sandbox_execution.py](08_sandbox_execution.py) | Sandbox 隔离执行 | 是 |

### Ralph 迭代模式

| 示例 | 描述 | 需要 API |
|------|------|----------|
| [09_ralph_iteration.py](09_ralph_iteration.py) | Ralph 基础用法 | 是 |
| [10_ralph_advanced.py](10_ralph_advanced.py) | Ralph 高级特性 | 是 |

## 快速运行

```bash
# 不需要 API 的示例（可直接运行）
uv run python examples/02_graph_basic.py
uv run python examples/03_graph_conditional.py
uv run python examples/04_graph_parallel.py
uv run python examples/06_graph_stream.py

# 需要 API 的示例（需设置 LLM_API_KEY）
uv run python examples/01_basic_agent.py
uv run python examples/05_graph_agent_node.py
uv run python examples/07_team_collaboration.py

# 需要 Sandbox 容器的示例
docker run -d --security-opt seccomp=unconfined -p 8080:8080 ghcr.io/agents-infra/sandbox:latest
uv run python examples/08_sandbox_execution.py

# Ralph 迭代模式示例
uv run python examples/09_ralph_iteration.py
uv run python examples/10_ralph_advanced.py
```

## Graph 执行引擎核心概念

### StateGraph

声明式图构建器，用于定义工作流：

```python
from omni_agent.core import StateGraph, START, END

graph = StateGraph(MyState)
graph.add_node("step1", step1_func)
graph.add_node("step2", step2_func)
graph.add_edge(START, "step1")
graph.add_edge("step1", "step2")
graph.add_edge("step2", END)
app = graph.compile()
result = await app.invoke(initial_state)
```

### 条件路由

基于状态动态选择下一个节点：

```python
from omni_agent.core import create_router

router = create_router("status", {"high": "urgent", "low": "normal"})
graph.add_conditional_edges("analyzer", router)
```

### 并行执行

从 START 添加多条边实现并行：

```python
graph.add_edge(START, "worker_a")
graph.add_edge(START, "worker_b")
# worker_a 和 worker_b 将并行执行
```

### 状态 Reducer

使用 `Annotated` 合并并行结果：

```python
from typing import Annotated
import operator

class State(TypedDict):
    results: Annotated[list, operator.add]  # 自动合并列表
```

### AgentNode

将 Agent 封装为图节点：

```python
from omni_agent.core import AgentNode

node = AgentNode(
    name="researcher",
    llm_client=client,
    system_prompt="...",
    input_key="query",
    output_key="result",
)
graph.add_node("research", node)
```

## 目录结构

```
examples/
├── README.md                    # 本文件
├── 01_basic_agent.py            # 基础 Agent
├── 02_graph_basic.py            # Graph 基础
├── 03_graph_conditional.py      # 条件路由
├── 04_graph_parallel.py         # 并行执行
├── 05_graph_agent_node.py       # AgentNode
├── 06_graph_stream.py           # 流式执行
├── 07_team_collaboration.py     # Team 协作
├── 08_sandbox_execution.py      # Sandbox 隔离
├── 09_ralph_iteration.py        # Ralph 基础用法
├── 10_ralph_advanced.py         # Ralph 高级特性
└── acp/                         # ACP 协议示例
```
