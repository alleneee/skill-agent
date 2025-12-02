# FastAPI Agent

一个功能完整的 AI Agent 系统，基于 FastAPI 构建

## 核心特性

### 基础能力
- **FastAPI Web API**: 生产级 RESTful API，支持 OpenAPI 文档
- **工具执行**: 文件操作（读/写/编辑）、Bash 命令、Skills 调用
- **多模型支持**: 兼容 Anthropic Claude 和 MiniMax M2
- **完整执行循环**: Agent 自动执行多步任务直到完成

### 高级功能
- **Token 管理**: 使用 tiktoken 精确计算 token，防止上下文溢出
- **自动消息总结**: 超过 token 限制时自动压缩历史消息
- **AgentLogger 日志系统**: 结构化 JSON 日志，完整追踪执行过程
- **MCP 集成**: 支持 Model Context Protocol，扩展外部工具能力
- **Skills 系统**: 内置专业 Skills，提供领域专家级指导
- **流式输出**: 支持 Server-Sent Events (SSE) 实时流式响应
- **会话记忆**: 使用 NoteTool 自动管理长期记忆和会话上下文
- **多后端 Session 存储**: 支持 File/Redis/PostgreSQL 三种存储后端
- **Web 前端**: ChatGPT 风格的 React 前端界面

### 多 Agent 协作
- **SpawnAgentTool**: 动态创建子 Agent 执行委派任务（类似 Claude Code Task 工具）
- **Team 系统**: Leader-Member 多 Agent 协作，支持智能任务委派
- **RAG 知识库**: 混合检索（语义+关键词），基于 PostgreSQL + pgvector

### 性能与监控
- **执行时间追踪**: 精确记录每个工具的执行时间（毫秒级）
- **Token 使用监控**: 实时追踪 token 使用情况和百分比
- **独立日志文件**: 每次运行生成时间戳日志，便于调试和审计

## 项目结构

```
skill-agent/
├── src/
│   └── fastapi_agent/          # 主要代码
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
│       │   ├── agent.py        # Agent 核心逻辑
│       │   ├── team.py         # Team 多 Agent 协作
│       │   ├── llm_client.py   # LLM 客户端（含流式）
│       │   ├── config.py       # 配置管理
│       │   ├── token_manager.py    # Token 管理与消息总结
│       │   ├── agent_logger.py     # 结构化日志系统
│       │   ├── session.py          # Session 数据模型
│       │   ├── session_storage.py  # 存储后端抽象层
│       │   └── session_manager.py  # 统一 Session 管理器
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
│       ├── skills/             # Skills 系统
│       │   ├── skill_tool.py   # Skill 工具实现
│       │   └── ...             # 内置 Skills
│       └── schemas/            # Pydantic 数据模型
│           ├── message.py      # Agent 请求/响应
│           └── team.py         # Team 请求/响应
├── frontend/                   # React Web 前端
├── tests/                      # 测试套件
├── skills/                     # 外部 Skills 定义
├── workspace/                  # Agent 工作目录
├── mcp.json                    # MCP 服务器配置
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
# LLM 配置
LLM_API_KEY=your_api_key_here
LLM_API_BASE=https://api.anthropic.com
LLM_MODEL=claude-3-5-sonnet-20241022

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
```

### 4. 配置 MCP（可选）

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
uv run uvicorn fastapi_agent.main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后，访问：
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health
- 工具列表: http://localhost:8000/api/v1/tools/

### 6. 启动前端（可选）

```bash
cd frontend && npm install && npm run dev
```

前端访问: http://localhost:3001

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

访问 http://localhost:8000/docs 使用 Swagger UI 进行交互式测试。

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

### 其他端点

- `GET /api/v1/tools/` - 列出所有可用工具
- `GET /health` - 健康检查

## 可用工具

### 基础工具

| 工具 | 描述 | 参数 |
|------|------|------|
| `read_file` | 读取文件内容 | `path`, `offset`, `limit` |
| `write_file` | 写入文件 | `path`, `content` |
| `edit_file` | 编辑文件（字符串替换）| `path`, `old_str`, `new_str` |
| `bash` | 执行 Bash 命令 | `command`, `timeout` |
| `get_skill` | 加载 Skill 专家指导 | `skill_name` |
| `session_note` | 存储会话记忆 | `note` |
| `recall_note` | 查询会话记忆 | `query` |

### 高级工具

| 工具 | 描述 | 参数 |
|------|------|------|
| `spawn_agent` | 动态创建子 Agent | `task`, `role`, `context`, `tools`, `max_steps` |
| `search_knowledge` | RAG 知识库搜索 | `query`, `top_k`, `mode` |

### MCP 工具

通过 `mcp.json` 配置扩展，如 `web_search_exa` 等。

### Skills 专家系统

内置 Skills: `mcp-builder`, `document-skills`, `web-tools`, `webapp-testing` 等。

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

配置：
```bash
ENABLE_RAG=true
DASHSCOPE_API_KEY=your_key     # 向量嵌入
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
CHUNK_SIZE=500
RAG_TOP_K=5
```

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

## 功能对比

| 特性 | Mini-Agent | FastAPI Agent |
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
| RAG 知识库 | No | Yes

## 开发指南

### 添加新工具

1. 在 `src/fastapi_agent/tools/` 创建工具文件
2. 继承 `Tool` 基类
3. 在 `api/deps.py` 中注册

```python
from fastapi_agent.tools.base import Tool, ToolResult

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

1. 在 `src/fastapi_agent/skills/` 创建目录
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
CMD ["uv", "run", "uvicorn", "fastapi_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t fastapi-agent .
docker run -p 8000:8000 --env-file .env fastapi-agent
```

### systemd

创建 `/etc/systemd/system/fastapi-agent.service`：

```ini
[Unit]
Description=FastAPI Agent Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/skill-agent
EnvironmentFile=/path/to/.env
ExecStart=/home/your_user/.local/bin/uv run uvicorn fastapi_agent.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable fastapi-agent && sudo systemctl start fastapi-agent
```

## 日志

Agent 执行日志保存在 `~/.fastapi-agent/log/`：

```bash
ls -lht ~/.fastapi-agent/log/ | head -5
cat ~/.fastapi-agent/log/agent_run_20251113_223233.log
```

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| MCP 工具未加载 | 检查 `ENABLE_MCP=true` 和 `mcp.json` 配置 |
| Token 超限 | 增加 `token_limit` 或确保 `enable_summarization=True` |
| 模块导入错误 | 使用 `uv run` 或设置 `PYTHONPATH` 包含 `src/` |
| RAG 搜索失败 | 检查 PostgreSQL + pgvector 配置和 DashScope API Key |

## 参考资料

- [FastAPI](https://fastapi.tiangolo.com/)
- [Anthropic API](https://docs.anthropic.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [uv](https://github.com/astral-sh/uv)

## 详细文档

- [流式输出](./docs/STREAMING.md)
- [前端指南](./frontend/README.md)
- [开发指南](./CLAUDE.md)

## License

MIT License
