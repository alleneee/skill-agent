# Omni Agent

一个功能完整的 AI Agent 系统，基于 FastAPI 构建

## 核心特性

### 基础能力
- **FastAPI Web API**: 生产级 RESTful API，支持 OpenAPI 文档
- **工具执行**: 文件操作（读/写/编辑）、Bash 命令、Skills 调用
- **多模型支持**: 通过 LiteLLM 支持 100+ LLM 提供商，智能适配参数限制
  - Anthropic Claude, OpenAI GPT-4, xAI Grok, DeepSeek, Qwen
  - 自动模型名称标准化 (provider/model 格式)
  - 自动调整 max_tokens 到提供商限制
- **完整执行循环**: Agent 自动执行多步任务直到完成

### 高级功能
- **多模态消息**: 支持 Image/Audio/Video 内容块，自动转换为 OpenAI API 格式
- **Token 管理**: 使用 tiktoken 精确计算 token，防止上下文溢出
- **自动消息总结**: 超过 token 限制时自动压缩历史消息
- **AgentLogger 日志系统**: 结构化 JSON 日志，完整追踪执行过程
- **MCP 集成**: 支持 Model Context Protocol，扩展外部工具能力
- **Skills 系统**: 内置专业 Skills，提供领域专家级指导
- **流式输出**: 支持 Server-Sent Events (SSE) 实时流式响应
- **会话记忆**: 使用 NoteTool 自动管理长期记忆和会话上下文
- **多后端 Session 存储**: 支持 File/Redis/PostgreSQL 三种存储后端
- **Web 前端**: ChatGPT 风格的 React 前端界面
- **人工确认机制**: Agent 可主动请求用户补充信息或确认敏感操作
- **Ralph 迭代模式**: 支持 Ralph Loop 迭代开发方法论，智能上下文管理与自动完成检测

### 多 Agent 协作
- **SpawnAgentTool**: 动态创建子 Agent 执行委派任务（类似 Claude Code Task 工具）
- **Team 系统**: Leader-Member 多 Agent 协作，支持智能任务委派
- **MsgHub**: 事件驱动的多 Agent 通信，自动消息广播，支持动态参与者管理
- **Graph 执行引擎**: LangGraph 风格的声明式工作流定义，支持并行执行、条件路由、状态 Reducer
- **RAG 知识库**: 混合检索（语义+关键词），基于 PostgreSQL + pgvector
- **Sandbox 沙箱隔离**: 基于 agent-sandbox，每个 Session 独立沙箱，安全执行不受信任代码
- **ACP 协议支持**: 实现 Zed Agent Client Protocol，支持代码编辑器集成

### 场景路由
- **自动场景识别**: 根据用户输入自动识别任务类型（代码开发、旅行规划、信息检索等）
- **动态工具选择**: 按场景自动配置最优工具集，减少不必要的 token 消耗
- **工具预设系统**: 预定义工具集（minimal/coding/research/travel/full）
- **工具分组管理**: 按类别组织工具（file_ops/code_tools/search_tools/maps_tools等）
- **系统提示适配**: 根据场景注入专业化的系统提示前缀
- **执行模式选择**: 自动选择 SingleAgent 或 Team 模式

### 性能与监控
- **Langfuse 可观测性**: 生产级 LLM 追踪，支持 Agent 执行流程、工具调用、Token 成本统计
- **执行时间追踪**: 精确记录每个工具的执行时间（毫秒级）
- **Token 使用监控**: 实时追踪 token 使用情况和百分比
- **独立日志文件**: 每次运行生成时间戳日志，便于调试和审计
- **TraceLogger 追踪系统**: 多 Agent 工作流追踪，支持委派链路、依赖关系可视化

## 项目结构

```
skill-agent/
├── src/
│   └── omni_agent/          # 主要代码
│       ├── main.py             # FastAPI 应用入口
│       ├── api/                # API 路由层
│       │   ├── deps.py         # 依赖注入（MCP/Session/AgentFactory）
│       │   └── v1/
│       │       ├── endpoints/
│       │       │   ├── agent.py    # Agent 端点（含流式）
│       │       │   ├── team.py     # Team 多 Agent 协作端点
│       │       │   ├── knowledge.py # RAG 知识库端点
│       │       │   └── tools.py    # 工具列表端点
│       │       └── router.py   # 主路由
│       ├── core/               # 核心组件
│       │   ├── agent.py        # Agent 核心 (含 State/Event/Hook/Loop)
│       │   ├── team.py         # Team 多 Agent 协作
│       │   ├── graph.py        # Graph 执行引擎（LangGraph 风格）
│       │   ├── agent_node.py   # AgentNode/ToolNode 封装
│       │   ├── agent_logger.py # 结构化日志系统
│       │   ├── llm_client.py   # LLM 客户端（含流式）
│       │   ├── config.py       # 配置管理
│       │   ├── scene.py            # 场景类型和配置
│       │   ├── scene_registry.py   # 预定义场景配置
│       │   ├── scene_router.py     # 场景路由器
│       │   ├── tool_groups.py      # 工具分组与预设
│       │   ├── token_manager.py    # Token 管理与消息总结
│       │   ├── file_memory.py      # AGENTS.md 文件记忆系统
│       │   ├── session.py          # Session 数据模型
│       │   ├── session_storage.py  # 存储后端抽象层
│       │   ├── session_manager.py  # 统一 Session 管理器
│       │   ├── langfuse_tracing.py # Langfuse 可观测性集成
│       │   ├── prompt_builder.py   # 结构化 Prompt 构建
│       │   ├── checkpoint.py       # 执行状态检查点
│       │   └── trace_logger.py     # 多 Agent 工作流追踪
│       ├── tools/              # 工具实现
│       │   ├── base.py         # 工具基类
│       │   ├── file_tools.py   # 文件操作
│       │   ├── bash_tool.py    # Bash 执行
│       │   ├── note_tool.py    # 会话记忆管理
│       │   ├── spawn_agent_tool.py # 子 Agent 动态创建
│       │   └── rag_tool.py     # RAG 知识库搜索
│       ├── rag/                # RAG 知识库
│       │   ├── database.py     # PostgreSQL + pgvector
│       │   ├── embedding_service.py # 向量嵌入服务
│       │   ├── document_processor.py # 文档处理
│       │   └── rag_service.py  # RAG 服务层
│       ├── sandbox/            # 沙箱隔离执行
│       │   ├── manager.py      # 沙箱生命周期管理
│       │   ├── toolkit.py      # 沙箱工具集工厂
│       │   └── tools.py        # 沙箱版工具实现
│       ├── skills/             # Skills 系统
│       │   ├── skill_tool.py   # Skill 工具实现
│       │   └── ...             # 内置 Skills
│       ├── utils/              # 工具类
│       │   └── trace_viewer.py # 追踪日志查看器
│       └── schemas/            # Pydantic 数据模型
│           ├── message.py      # Agent 请求/响应（含多模态支持）
│           ├── content_block.py # 多模态内容块类型
│           └── team.py         # Team 请求/响应
├── frontend/                   # React Web 前端 (Vite + TailwindCSS)
├── tests/                      # 测试套件
├── skills/                     # 外部 Skills 定义
├── workspace/                  # Agent 工作目录
├── mcp.json.example            # MCP 服务器配置示例
├── docs/                       # 文档
│   └── TRACING_GUIDE.md        # 追踪系统使用指南
└── pyproject.toml              # 项目配置（uv）
```

## 快速开始

### 1. 安装 uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 安装项目依赖

```bash
uv sync
```

### 3. 配置环境变量

创建 `.env` 文件：

```bash
# LLM 配置 (支持 100+ 提供商)
LLM_API_KEY=your_api_key_here
LLM_API_BASE=  # 留空使用默认端点，或设置自定义/代理地址
LLM_MODEL=anthropic/claude-3-5-sonnet-20241022  # 格式: provider/model

# Agent 配置
AGENT_MAX_STEPS=50
AGENT_WORKSPACE_DIR=./workspace

# 功能开关
ENABLE_MCP=true              # MCP 集成
ENABLE_SKILLS=true           # Skills 系统
ENABLE_RAG=true              # RAG 知识库
ENABLE_SPAWN_AGENT=true      # 子 Agent 创建
MCP_CONFIG_PATH=mcp.json

# SpawnAgent 配置
SPAWN_AGENT_MAX_DEPTH=3      # 最大嵌套深度
SPAWN_AGENT_DEFAULT_MAX_STEPS=15
SPAWN_AGENT_TOKEN_LIMIT=50000

# ACP 协议（代码编辑器集成）
ENABLE_ACP=true              # 启用 ACP 端点

# 场景路由
ENABLE_SCENE_ROUTING=true    # 启用自动场景识别
SCENE_ROUTING_USE_LLM=false  # 使用 LLM 进行场景分类（更精确但更慢）

# Sandbox 沙箱隔离（可选）
ENABLE_SANDBOX=false         # 启用沙箱隔离执行
SANDBOX_URL=http://localhost:8080  # agents-sandbox 服务地址
SANDBOX_AUTO_START=false     # 自动启动 Docker 容器
SANDBOX_TTL_SECONDS=3600     # 沙箱实例存活时间

# Session 管理
ENABLE_SESSION=true
SESSION_BACKEND=file         # file, redis, postgres

# RAG 知识库（需要 PostgreSQL + pgvector）
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=knowledge_base
DASHSCOPE_API_KEY=your_dashscope_key  # 用于向量嵌入

# Langfuse 可观测性（可选）
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com  # 或自部署地址
```

### 4. 配置 MCP（可选）

复制示例配置并编辑：

```bash
cp mcp.json.example mcp.json
```

编辑 `mcp.json` 配置 MCP 服务器：

```json
{
  "$schema": "https://modelcontextprotocol.io/schema/mcp.json",
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y", "exa-mcp-server", "tools=web_search_exa"],
      "env": {
        "EXA_API_KEY": "your_exa_api_key"
      },
      "disabled": false
    }
  }
}
```

### 5. 启动服务

```bash
make dev
# 或
uv run uvicorn omni_agent.main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后，访问：
- API 文档: <http://localhost:8000/docs>
- 健康检查: <http://localhost:8000/health>
- 工具列表: <http://localhost:8000/api/v1/tools/>

### 6. 启动前端（可选）

```bash
cd frontend
cp .env.example .env  # 配置环境变量
pnpm install
pnpm dev
```

前端环境变量 (`frontend/.env`)：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VITE_API_URL` | 后端API地址 | `http://localhost:8000` |
| `VITE_LANGFUSE_URL` | Langfuse调试控制台地址 | `https://cloud.langfuse.com` |

前端访问: <http://localhost:3001>

## 多 LLM 提供商支持

系统通过 **LiteLLM** 统一接口支持 100+ LLM 提供商，并自动处理各提供商的差异。

### 支持的提供商

| 提供商 | 模型示例 | max_tokens 限制 |
|--------|----------|----------------|
| Anthropic | `anthropic/claude-3-5-sonnet-20241022` | 8192 |
| OpenAI | `openai/gpt-4o` | 16384 |
| xAI Grok | `xai/grok-4-fast-reasoning` | 16384 |
| DeepSeek | `deepseek/deepseek-chat` | 8192 |
| Qwen | `qwen/qwen-max` | 8192 |
| Google | `gemini/gemini-1.5-pro` | 8192 |
| OpenRouter | `openrouter/anthropic/claude-3.5-sonnet` | 依赖上游 |

### 自动适配特性

✅ **模型名称标准化**: 自动转换为 `provider/model` 格式
```bash
# 这些格式都会自动处理：
claude-3-5-sonnet-20241022  → anthropic/claude-3-5-sonnet-20241022
openai:gpt-4o               → openai/gpt-4o
gpt-4o                      → openai/gpt-4o
```

✅ **参数限制自动调整**: 自动检测并调整 `max_tokens` 到提供商限制
```
请求 16384 tokens → DeepSeek 限制 8192 → 自动调整为 8192
```

### 配置示例

详细配置查看：
- [模型配置指南](docs/MODEL_STANDARDIZATION.md)
- [OpenRouter 配置](docs/OPENROUTER.md)
- [Grok 验证报告](docs/GROK_VALIDATION_REPORT.md)
- [curl 示例](docs/CURL_EXAMPLES.md)

## 使用方法

### 通过 curl

```bash
# 单 Agent 请求
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "创建一个 Python 脚本，输出斐波那契数列", "max_steps": 10}'

# 流式请求
curl -N -X POST http://localhost:8000/api/v1/agent/run/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "介绍你自己", "max_steps": 10}'

# Team 多 Agent 协作
curl -X POST http://localhost:8000/api/v1/team/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "研究 Python 异步编程并撰写技术文章",
    "members": ["researcher", "writer", "reviewer"],
    "delegate_to_all": false
  }'
```

### 通过 Python 客户端

```python
import httpx
import asyncio

async def run_agent():
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "http://localhost:8000/api/v1/agent/run",
            json={"message": "搜索最新的 AI 新闻", "max_steps": 15}
        )
        result = response.json()
        print(f"响应: {result['message']}")
        print(f"步骤数: {result['steps']}")

asyncio.run(run_agent())
```

### 通过交互式文档

访问 <http://localhost:3001>/docs> 使用 Swagger UI 进行交互式测试。

## API 端点

### Agent 端点

#### `POST /api/v1/agent/run`

运行 Agent 执行任务。

```json
// 请求
{
  "message": "任务描述",
  "workspace_dir": "./workspace",
  "max_steps": 50,
  "session_id": "session-123"
}

// 响应
{
  "success": true,
  "message": "任务完成结果",
  "steps": 5,
  "logs": [...]
}
```

#### `POST /api/v1/agent/run/stream`

流式模式（Server-Sent Events）。事件类型：`thinking`, `content`, `tool_call`, `tool_result`, `step`, `complete`。

### Team 端点

#### `POST /api/v1/team/run`

运行 Team 多 Agent 协作任务。

```json
// 请求
{
  "message": "研究并撰写技术文章",
  "members": ["researcher", "writer", "reviewer"],
  "delegate_to_all": false,
  "team_name": "AI Team",
  "session_id": "session-123"
}

// 响应
{
  "success": true,
  "team_name": "AI Team",
  "message": "最终合成结果",
  "member_runs": [
    {
      "member_name": "Researcher",
      "member_role": "Research Specialist",
      "task": "...",
      "response": "...",
      "success": true,
      "steps": 5
    }
  ],
  "total_steps": 15,
  "iterations": 3
}
```

**可用角色**: `researcher`, `writer`, `coder`, `reviewer`, `analyst`

#### `GET /api/v1/team/roles`

获取所有可用的 Team 角色及其配置。

### Knowledge 端点（RAG）

#### `POST /api/v1/knowledge/upload`

上传文档到知识库。

#### `POST /api/v1/knowledge/search`

搜索知识库（支持 hybrid/semantic/keyword 模式）。

### ACP 端点 (Agent Client Protocol)

ACP 端点实现 [Zed Agent Client Protocol](https://agentclientprotocol.com/)，支持代码编辑器集成。

#### `POST /api/v1/acp/agent/initialize`

初始化 ACP 连接，协商协议能力。

```json
// 请求 (JSON-RPC 2.0)
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "agents/initialize",
  "params": {
    "protocolVersion": "1.0",
    "clientInfo": {"name": "MyEditor", "version": "1.0.0"}
  }
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 0,
  "result": {
    "protocolVersion": 1,
    "agentCapabilities": {
      "loadSession": true,
      "promptCapabilities": {"image": false, "embeddedContext": true},
      "mcp": {"http": true, "sse": true}
    },
    "agentInfo": {"name": "omni-agents", "version": "0.1.0"}
  }
}
```

#### `POST /api/v1/acp/session/new`

创建新会话。

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "session/new",
  "params": {
    "cwd": "/path/to/project",
    "mcpServers": []
  }
}

// 响应
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {"sessionId": "sess_abc123def456"}
}
```

#### `POST /api/v1/acp/session/prompt`

发送用户提示（同步模式）。

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "session/prompt",
  "params": {
    "sessionId": "sess_abc123def456",
    "prompt": [
      {"type": "text", "text": "分析这段代码的问题"}
    ]
  }
}
```

#### `POST /api/v1/acp/session/prompt/stream`

发送用户提示（流式模式），返回 SSE 事件流。

事件类型：
- `session/update` (sessionUpdate: `agent_thought_chunk`) - Agent 思考过程
- `session/update` (sessionUpdate: `agent_message_chunk`) - Agent 回复内容
- `session/update` (sessionUpdate: `tool_call`) - 工具调用开始
- `session/update` (sessionUpdate: `tool_call_update`) - 工具调用更新

### 其他端点

- `GET /api/v1/tools/` - 列出所有可用工具
- `GET /health` - 健康检查

## 可用工具

### 基础工具 (deepagents 风格)

| 工具 | 描述 | 参数 |
|------|------|------|
| `read_file` | 读取文件内容（带行号） | `path`, `offset`, `limit` |
| `write_file` | 写入文件 | `path`, `content` |
| `edit_file` | 编辑文件（字符串替换） | `path`, `old_str`, `new_str`, `replace_all` |
| `ls` | 列出目录内容（含大小和时间） | `path`, `recursive` |
| `glob` | 按模式查找文件 | `pattern`, `path` |
| `grep` | 搜索文件内容（支持正则） | `pattern`, `path`, `include`, `context` |
| `bash` | 执行 Bash 命令 | `command`, `timeout` |
| `get_skill` | 加载 Skill 专家指导 | `skill_name` |
| `session_note` | 存储会话记忆 | `note` |
| `recall_note` | 查询会话记忆 | `query` |

### 高级工具

| 工具 | 描述 | 参数 |
|------|------|------|
| `spawn_agent` | 动态创建子 Agent | `task`, `role`, `context`, `tools`, `max_steps` |
| `search_knowledge` | RAG 知识库搜索 | `query`, `top_k`, `mode` |
| `get_user_input` | 请求用户补充信息 | `user_input_fields`, `context` |

### MCP 工具

通过 `mcp.json` 配置扩展，如 `web_search_exa` 等。

### Skills 专家系统

内置 Skills: `mcp-builder`, `document-skills`, `web-tools`, `webapp-testing`, `web-spider` (Firecrawl), `travel-planner` 等。

## 核心功能详解

### SpawnAgent 子任务委派

`spawn_agent` 工具允许父 Agent 动态创建子 Agent 执行委派任务：

```python
# 子 Agent 用法示例
spawn_agent(
    task="审计 src/auth 模块的安全性",
    role="security auditor",
    context="这是一个 FastAPI 应用，使用 SQLAlchemy。重点检查用户输入处理。",
    tools=["read_file", "bash"],
    max_steps=20
)
```

配置选项：
```bash
ENABLE_SPAWN_AGENT=true
SPAWN_AGENT_MAX_DEPTH=3        # 最大嵌套深度
SPAWN_AGENT_DEFAULT_MAX_STEPS=15
SPAWN_AGENT_TOKEN_LIMIT=50000
```

适用场景：
- 需要专业角色的任务（security auditor, test writer）
- 分解复杂任务为独立子任务
- 避免主 Agent 上下文污染

### Team 多 Agent 协作

Team 系统采用 Leader-Member 模式进行任务协作：

```python
# Team 工作流程
# 1. Leader 分析任务
# 2. Leader 使用 delegate_task_to_member 工具委派给合适成员
# 3. 成员执行任务返回结果
# 4. Leader 综合结果给出最终答案
```

预定义角色：
| 角色 | 职责 | 默认工具 |
|------|------|----------|
| `researcher` | 信息搜索与整理 | `read`, `bash` |
| `writer` | 内容撰写与组织 | `write`, `edit` |
| `coder` | 编程与技术问题 | `read`, `write`, `edit`, `bash` |
| `reviewer` | 质量审查与反馈 | `read` |
| `analyst` | 数据分析与洞察 | 所有工具 |

### MsgHub 事件驱动多 Agent 通信

MsgHub 借鉴 AgentScope 的 subscriber 机制，通过事件驱动实现 Agent 间自动消息广播：

```python
from omni_agent.core import Agent, MsgHub, MsgHubConfig

designer = Agent(llm_client=llm, name="designer", system_prompt="UI designer")
developer = Agent(llm_client=llm, name="developer", system_prompt="Developer")
reviewer = Agent(llm_client=llm, name="reviewer", system_prompt="Code reviewer")

config = MsgHubConfig(
    max_rounds=6,
    max_steps_per_turn=5,
    announcement="Design review session.",
)

async with MsgHub([designer, developer, reviewer], config=config) as hub:
    result = await hub.run("Design a REST API for user auth")
    hub.add(new_agent)
    hub.delete("reviewer")
    result2 = await hub.run("Refine the design based on feedback")
```

核心机制：

- Agent 完成发言后触发 COMPLETION 事件
- MsgHub 事件处理器捕获并自动广播给其他参与者
- 通过 `Agent.observe(msg)` 注入消息到目标 Agent 历史
- 支持自定义 Orchestrator 控制发言顺序（默认 round-robin）
- Agent 返回 `<hub_complete>` 标签结束讨论

### Ralph 迭代模式

Ralph Loop 是一种迭代开发方法论，通过重复执行相同的 prompt，让 AI 看到自己之前的工作并逐步改进，直到任务完成。

```python
from omni_agent.core import Agent, RalphConfig

# 方式1: 简单启用（使用默认配置）
agent = Agent(llm_client=llm_client, tools=tools, ralph=True)

# 方式2: 自定义配置
agent = Agent(
    llm_client=llm_client,
    tools=tools,
    ralph=RalphConfig(
        max_iterations=20,
        completion_promise="TASK COMPLETE",
        idle_threshold=3,
    ),
)

# 统一入口执行
result, logs = await agent.run(task="重构 src/utils 模块")
```

核心组件：

| 组件 | 功能 |
|------|------|
| `ToolResultCache` | 工具结果缓存，支持摘要和完整内容按需获取 |
| `WorkingMemory` | 结构化工作记忆，持久化到 `.ralph/memory.json` |
| `ContextManager` | 上下文管理器，协调摘要和迭代历史 |
| `CompletionDetector` | 多条件完成检测（Promise标签、最大迭代、空闲检测） |

Ralph 专用工具：

| 工具 | 描述 |
|------|------|
| `get_cached_result` | 获取之前工具调用的完整结果 |
| `get_working_memory` | 查看工作记忆摘要 |
| `update_working_memory` | 更新进度、发现、待办等 |
| `signal_completion` | 信号任务完成 |

完成检测条件：
- `PROMISE_TAG`: 检测 `<promise>TASK COMPLETE</promise>` 标签
- `MAX_ITERATIONS`: 达到最大迭代次数
- `IDLE_THRESHOLD`: 连续 N 次无文件修改

### Sandbox 沙箱隔离

基于 [agent-sandbox](https://github.com/agent-infra/sandbox) 的代码隔离执行环境，每个 Session 独立沙箱：

```python
from omni_agent.sandbox import SandboxManager, SandboxToolkit

manager = SandboxManager(base_url="http://localhost:8080")
await manager.initialize()

toolkit = SandboxToolkit(manager)
tools = await toolkit.get_tools("session-123")
```

启动沙箱容器：

```bash
docker run -d --security-opt seccomp=unconfined -p 8080:8080 ghcr.io/agents-infra/sandbox:latest
```

沙箱工具集：

| 工具 | 描述 |
|------|------|
| `bash` | 在沙箱中执行 Shell 命令 |
| `read_file` | 读取沙箱内文件 |
| `write_file` | 写入沙箱内文件 |
| `edit_file` | 编辑沙箱内文件 |
| `list_dir` | 列出沙箱内目录 |
| `python` | 执行 Python 代码 (Jupyter) |

配置：

```bash
ENABLE_SANDBOX=true
SANDBOX_URL=http://localhost:8080
SANDBOX_AUTO_START=false      # 自动启动 Docker 容器
SANDBOX_TTL_SECONDS=3600      # 沙箱实例存活时间
SANDBOX_MAX_INSTANCES=100     # 最大沙箱数量
```

### RAG 知识库

基于 PostgreSQL + pgvector 的混合检索系统：

```python
# 搜索模式
search_knowledge(
    query="如何配置 Agent",
    top_k=5,
    mode="hybrid"  # hybrid, semantic, keyword
)
```

### Graph 执行引擎

受 LangGraph 启发的声明式工作流定义，支持：

- **顺序执行**: 节点按顺序执行
- **并行执行**: 多个节点同时执行
- **条件路由**: 基于状态动态选择下一个节点
- **状态 Reducer**: 合并并行执行结果

```python
from omni_agent.core import StateGraph, START, END, AgentNode, create_router
from typing import TypedDict, Annotated
import operator

class WorkflowState(TypedDict):
    task: str
    status: str
    results: Annotated[list, operator.add]

async def analyzer(state):
    if "urgent" in state["task"]:
        return {"status": "urgent", "results": ["Analyzed as urgent"]}
    return {"status": "normal", "results": ["Analyzed as normal"]}

async def urgent_handler(state):
    return {"results": ["Handled urgently: " + state["task"]]}

async def normal_handler(state):
    return {"results": ["Handled normally: " + state["task"]]}

graph = StateGraph(WorkflowState)
graph.add_node("analyzer", analyzer)
graph.add_node("urgent", urgent_handler)
graph.add_node("normal", normal_handler)

graph.add_edge(START, "analyzer")
graph.add_conditional_edges(
    "analyzer",
    create_router("status", {"urgent": "urgent", "normal": "normal"})
)
graph.add_edge("urgent", END)
graph.add_edge("normal", END)

app = graph.compile()
result = await app.invoke({"task": "urgent fix bug", "status": "", "results": []})
```

**AgentNode**: 将现有 Agent 封装为图节点

```python
from omni_agent.core import AgentNode

researcher = AgentNode(
    name="researcher",
    llm_client=client,
    system_prompt="You are a research assistant.",
    tools=[search_tool],
    input_key="task",
    output_key="result",
)

graph.add_node("research", researcher)
```

配置：
```bash
ENABLE_RAG=true
DASHSCOPE_API_KEY=your_key     # 向量嵌入
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
CHUNK_SIZE=500
RAG_TOP_K=5
```

### ACP 协议集成

实现 [Zed Agent Client Protocol](https://agentclientprotocol.com/)，支持代码编辑器与 Agent 的标准化通信。基于官方 [agent-client-protocol](https://github.com/agentclientprotocol/python-sdk) Python SDK 实现。

```bash
# 配置
ENABLE_ACP=true
```

#### 支持的后端

| 后端 | CLI 命令 | ACP 参数 | 说明 |
|------|----------|----------|------|
| Claude | `claude` | `--experimental-acp` | Anthropic Claude Code |
| Codex | `codex` | `--experimental-acp` | OpenAI Codex CLI |
| Qwen | `npx @qwen-code/qwen-code` | `--experimental-acp` | 通义千问 |
| Goose | `goose` | `acp` (子命令) | Block's Goose |
| Auggie | `auggie` | `--acp` | Augment Code |
| Kimi | `kimi` | `--acp` | Moonshot Kimi |
| OpenCode | `opencode` | `acp` (子命令) | OpenCode CLI |
| iFlow | `iflow` | `--experimental-acp` | iFlow CLI |

#### 多后端客户端

```python
import asyncio
from omni_agent.acp import AcpClient, MessageEvent, run_prompt

# 方式一：使用 AcpClient 类
async def example_client():
    async with AcpClient(backend="claude", workspace="/path/to/project") as client:
        client.handler.set_event_callback(lambda e: print(e.text) if isinstance(e, MessageEvent) else None)
        await client.prompt("What is 2 + 2?")

# 方式二：简单 API
async def example_simple():
    result = await run_prompt(
        backend="codex",
        prompt="Write hello world in Python",
        auto_approve=True,
    )
    print(result)

asyncio.run(example_client())
```

示例脚本：

```bash
# 列出可用后端
uv run python examples/acp/multi_backend.py --list

# 使用特定后端
uv run python examples/acp/multi_backend.py --backend claude
uv run python examples/acp/multi_backend.py --backend codex -p "Hello"
uv run python examples/acp/multi_backend.py --backend qwen

# 流式输出
uv run python examples/acp/streaming_example.py --backend claude
```

#### 使用方式

**1. Stdio 模式（推荐，用于编辑器集成）**

```bash
# 直接运行 ACP 服务
omni-agents-acp --workspace /path/to/project

# 或通过模块运行
uv run python -m omni_agent.acp.acp_server --workspace /path/to/project
```

在编辑器（如 Zed）中配置自定义 Agent：

```json
{
  "assistant": {
    "custom_agents": [
      {
        "name": "omni-agents",
        "command": "omni-agents-acp",
        "args": ["--workspace", "${workspace}"]
      }
    ]
  }
}
```

**2. HTTP 模式（用于 Web 集成）**

启动服务后访问 `/api/v1/acp/*` 端点（见下文 API 端点章节）。

协议特性：
- **JSON-RPC 2.0**: 标准化的请求/响应格式
- **会话管理**: 创建、管理、取消会话
- **流式更新**: 实时推送思考过程、工具调用、消息内容
- **工具调用追踪**: 详细的工具执行状态和结果

支持的 Session Updates：

| 类型 | 说明 |
|------|------|
| `agent_thought_chunk` | Agent 思考过程（实时流） |
| `agent_message_chunk` | Agent 回复内容（实时流） |
| `tool_call` | 工具调用开始 |
| `tool_call_update` | 工具调用状态更新 |
| `plan` | 执行计划（TODO 列表） |

工具类型映射：

| 内部工具 | ACP ToolKind |
|----------|--------------|
| `read_file` | `read` |
| `write_file`, `edit_file` | `edit` |
| `bash` | `execute` |
| `web_search` | `fetch` |
| `search_knowledge` | `search` |

### 多模态消息支持

支持在消息中包含图片、音频、视频等多模态内容：

```python
from omni_agent.schemas import (
    Message, TextBlock, ImageBlock, AudioBlock,
    Base64Source, URLSource
)
from omni_agent.core import file_to_base64

# 方式1: 使用 URL
msg = Message(
    role="user",
    content=[
        TextBlock(text="分析这张图片:"),
        ImageBlock(source=URLSource(url="https://example.com/image.png")),
    ]
)

# 方式2: 使用 Base64 (本地文件)
data, mime = file_to_base64("./screenshot.png")
msg = Message(
    role="user",
    content=[
        TextBlock(text="这个截图有什么问题?"),
        ImageBlock(source=Base64Source(media_type=mime, data=data)),
    ]
)

# Message helper 方法
text = msg.get_text_content()           # 提取纯文本
images = msg.get_content_blocks(ImageBlock)  # 获取所有图片块
has_audio = msg.has_content_blocks(AudioBlock)  # 检查是否包含音频
```

支持的内容块类型：

| 类型 | 描述 | OpenAI 格式 |
|------|------|-------------|
| `TextBlock` | 文本内容 | `{type: "text", text: "..."}` |
| `ImageBlock` | 图片 (URL/Base64) | `{type: "image_url", image_url: {url: "..."}}` |
| `AudioBlock` | 音频 (仅 Base64) | `{type: "input_audio", input_audio: {...}}` |
| `VideoBlock` | 视频 (URL/Base64) | `{type: "video_url", video_url: {...}}` |

### Token 管理

自动 token 计算和消息压缩，防止上下文溢出：

- 使用 tiktoken (cl100k_base) 精确计算
- 超过限制时自动压缩历史消息
- 保留用户消息，压缩 Agent 执行过程
- 可减少 50-70% token 使用

### Session 管理

支持三种存储后端：

| 后端 | 适用场景 | 配置 |
|------|----------|------|
| File | 开发/单机 | `SESSION_BACKEND=file` |
| Redis | 生产/分布式 | `SESSION_BACKEND=redis` |
| PostgreSQL | 持久化/查询 | `SESSION_BACKEND=postgres` |

```bash
# Session 配置
SESSION_MAX_AGE_DAYS=7
SESSION_MAX_RUNS_PER_SESSION=100
SESSION_HISTORY_RUNS=3
```

### 记忆系统

基于 Markdown 文件的记忆存储，按类型分离，profile/habit 提升到用户级别（跨会话持久）。

#### 目录结构

```text
.agent_memories/{user_id}/
├── profile.md                    # 用户画像（跨会话持久）
├── habit.md                      # 用户习惯（跨会话持久）
└── sessions/
    └── {session_id}/
        ├── context.md            # 当前会话上下文
        └── meta.json             # 轻量元数据
```

#### 核心设计

| 文件 | 级别 | 内容 | 持久性 |
|------|------|------|--------|
| `profile.md` | 用户级 | 职业、背景、技能、偏好 | 跨会话 |
| `habit.md` | 用户级 | 工作流程、操作习惯 | 跨会话 |
| `context.md` | 会话级 | 当前任务、轮次摘要 | 会话内 |
| `meta.json` | 会话级 | created_at, updated_at, round_count | 会话内 |

#### 使用方式

```python
from omni_agent.core import Memory, MemoryManager

mem = Memory(user_id="user_001", session_id="sess_abc")
mem.init_memory(task="重构记忆系统")

# 读写 Markdown 文件
mem.write_profile("- Python 高级开发者\n- 偏好简洁代码\n")
mem.append_habit("- TDD 开发流程\n")
mem.append_context("## Round 1\n\n完成了 Memory 类重写\n")

# 读取
profile = mem.read_profile()
habit = mem.read_habit()
context = mem.read_context()

# 上下文注入（拼接三个 .md 到 <user_memory> 标签）
prompt_context = mem.get_context_for_prompt()

# 元数据
mem.increment_round()
print(mem.round_count)

# 管理器
mgr = MemoryManager()
mgr.list_sessions("user_001")
mgr.cleanup_expired(max_age_days=7)
```

#### 深度检索工具 (DeepRecallMemoryTool)

`deep_recall_memory` 工具在三个 .md 文件中进行搜索：

| 模式 | 说明 | 依赖 |
|------|------|------|
| `keyword` | 按段落切分 .md，关键词匹配 | 无 |
| `semantic` | 向量语义搜索 | PostgreSQL + pgvector |
| `hybrid` | 混合搜索，合并语义和关键词结果 | PostgreSQL + pgvector（降级为 keyword） |

参数：

- `query`: 搜索文本（必填）
- `memory_type`: 按类型过滤（profile/habit/context）
- `mode`: 搜索模式（默认 hybrid）
- `limit`: 结果数量上限（默认 5）

#### 自动迁移

旧 JSON 格式（memory.json + memory_detail.json）首次加载时自动迁移：

- profile 条目写入 `profile.md`
- habit 条目写入 `habit.md`
- task + context + core_facts 写入 `context.md`
- 旧文件重命名为 `.json.bak` 保留备份

## 功能对比

| 特性 | Mini-Agent | Omni Agent |
|------|-----------|---------------|
| 接口方式 | CLI | RESTful API + Web UI |
| Token 管理 | Yes | Yes |
| 消息总结 | Yes | Yes |
| MCP 支持 | Yes | Yes |
| Skills 系统 | No | Yes |
| 流式输出 | No | Yes (SSE) |
| 会话记忆 | No | Yes |
| 多后端 Session | No | Yes (File/Redis/PostgreSQL) |
| Web 前端 | No | Yes (React) |
| SpawnAgent | No | Yes |
| Team 多 Agent | No | Yes |
| RAG 知识库 | No | Yes |

## 评测与 Benchmark

### 内置 Eval 体系

6 类评测用例 (61 cases)，覆盖 Agent 核心能力：

```bash
# 运行全部 eval
uv run python -m omni_agent.eval --tags quick

# 按类别运行
uv run python -m omni_agent.eval --dataset evals/safety
uv run python -m omni_agent.eval --dataset evals/tool_usage
```

| 类别 | 用例数 | 测试内容 |
|------|--------|----------|
| `tool_usage` | 15 | 文件读写、编辑、Bash、组合操作 |
| `multi_step` | 11 | API 设计、配置迁移、日志分析、依赖修复 |
| `code_generation` | 10 | 算法、类设计、装饰器、bug 修复、设计模式 |
| `reasoning` | 8 | 日志分析、数据提取、代码审查、性能分析 |
| `safety` | 10 | 路径逃逸、危险命令、Prompt 注入、环境泄露 |
| `efficiency` | 7 | 单步完成、直接读取、批量操作 |

### 外部 Benchmark

集成 BFCL 和 GAIA 两个标准 benchmark：

```bash
# BFCL - 函数调用能力评测
uv run python -m omni_agent.eval.benchmarks bfcl --categories simple --max-cases 20

# GAIA - 真实世界问答 (自动加载 MCP 工具)
uv run python -m omni_agent.eval.benchmarks gaia --levels 1 --max-cases 10

# 开启 Thinking 模式
uv run python -m omni_agent.eval.benchmarks gaia --levels 1 --max-cases 5 --thinking

# 运行全部
uv run python -m omni_agent.eval.benchmarks all --output eval_results
```

| Benchmark | 类别 | 结果 | 说明 |
|-----------|------|------|------|
| BFCL | simple (20) | 100% | 单函数调用准确率 |
| BFCL | simple+multiple+irrelevance (30) | 96.7% | 多类别混合 |
| GAIA | Level 1 (10) | 60% | 真实世界问答 + Web 搜索 |

CLI 参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--categories` | `simple` | BFCL 类别 (逗号分隔) |
| `--levels` | `1` | GAIA 难度等级 (1/2/3) |
| `--max-cases` | `20` | 每类别最大用例数 |
| `--max-steps` | `15` | GAIA Agent 最大步数 |
| `--timeout` | `120` | 单个用例超时 (秒) |
| `--thinking` | `false` | 启用 Thinking 推理模式 |
| `--output` | `eval_results` | 结果输出目录 |

## 开发指南

### 添加新工具

1. 在 `src/omni_agent/tools/` 创建工具文件
2. 继承 `Tool` 基类
3. 在 `api/deps.py` 中注册

```python
from omni_agent.tools.base import Tool, ToolResult

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Tool description"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Parameter"}
            },
            "required": ["param"]
        }

    async def execute(self, param: str) -> ToolResult:
        return ToolResult(success=True, content="Result")
```

### 添加新 Skill

1. 在 `src/omni_agent/skills/` 创建目录
2. 创建 `SKILL.md` 文件定义内容
3. 自动被 `get_skill` 工具识别

### 运行测试

```bash
make test
# 或
uv run pytest tests/core/test_agent.py -v
```

## 生产部署

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY . .
RUN uv sync --frozen
CMD ["uv", "run", "uvicorn", "omni_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t omni-agents .
docker run -p 8000:8000 --env-file .env omni-agents
```

### systemd

创建 `/etc/systemd/system/omni-agent.service`：

```ini
[Unit]
Description=Omni Agent Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/skill-agent
EnvironmentFile=/path/to/.env
ExecStart=/home/your_user/.local/bin/uv run uvicorn omni_agent.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable omni-agents && sudo systemctl start omni-agents
```

## 可观测性与追踪

### Langfuse（推荐）

系统支持 [Langfuse](https://langfuse.com) 作为生产级可观测性解决方案：

```bash
# .env 配置
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_HOST="https://cloud.langfuse.com"  # 或自部署地址
```

Langfuse 提供：

- **自动 LLM 追踪**: 通过 LiteLLM callback 自动记录所有 LLM 调用
- **Agent 执行追踪**: 完整的 Agent 执行流程、工具调用、嵌套层级
- **Token 和成本统计**: 实时 token 使用和成本计算
- **可视化 Dashboard**: Web 界面查看和分析 traces
- **采样和过滤**: 支持采样率配置，减少生产环境数据量

配置选项：

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| `LANGFUSE_ENABLED` | `false` | 启用 Langfuse 追踪 |
| `LANGFUSE_PUBLIC_KEY` | - | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | - | Langfuse 私钥 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 服务地址 |
| `LANGFUSE_SAMPLE_RATE` | `1.0` | 采样率 (0.0-1.0) |
| `LANGFUSE_FLUSH_INTERVAL` | `5.0` | 数据刷新间隔(秒) |

### 本地日志（Deprecated）

> 当 `LANGFUSE_ENABLED=true` 时，以下本地日志功能被禁用。

#### AgentLogger（单 Agent 日志）

Agent 执行日志保存在 `~/.omni-agent/log/`：

```bash
ls -lht ~/.omni-agents/log/ | head -5
cat ~/.omni-agents/log/agent_run_20251113_223233.log
```

#### TraceLogger（多 Agent 追踪）

工作流追踪日志保存在 `~/.omni-agent/traces/`：

```bash
uv run python -m omni_agent.utils.trace_viewer list
uv run python -m omni_agent.utils.trace_viewer view trace_team_20251205_abc123.jsonl
uv run python -m omni_agent.utils.trace_viewer flow trace_dependency_workflow_20251205_xyz789.jsonl
```

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| MCP 工具未加载 | 检查 `ENABLE_MCP=true` 和 `mcp.json` 配置 |
| Token 超限 | 增加 `token_limit` 或确保 `enable_summarization=True` |
| 模块导入错误 | 使用 `uv run` 或设置 `PYTHONPATH` 包含 `src/` |
| RAG 搜索失败 | 检查 PostgreSQL + pgvector 配置和 DashScope API Key |
| Sandbox 连接失败 | 确保 Docker 容器运行且端口 8080 可访问 |

## 参考资料

- [FastAPI](https://fastapi.tiangolo.com/)
- [Anthropic API](https://docs.anthropic.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [agent-sandbox](https://github.com/agent-infra/sandbox)
- [uv](https://github.com/astral-sh/uv)

## 详细文档

- [流式输出](./docs/STREAMING.md)
- [追踪系统指南](./docs/TRACING_GUIDE.md)
- [Sandbox 隔离执行](./examples/08_sandbox_execution.py)
- [前端指南](./frontend/README.md)
- [开发指南](./CLAUDE.md)

## License

MIT License
