# FastAPI Agent

一个功能完整的 AI Agent 系统，基于 FastAPI 构建，灵感来自 [MiniMax-AI/Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent)。

## ✨ 核心特性

### 🚀 基础能力
- ✅ **FastAPI Web API**: 生产级 RESTful API，支持 OpenAPI 文档
- ✅ **工具执行**: 文件操作（读/写/编辑）、Bash 命令、Skills 调用
- ✅ **多模型支持**: 兼容 Anthropic Claude 和 MiniMax M2
- ✅ **完整执行循环**: Agent 自动执行多步任务直到完成

### 🔥 高级功能
- ✅ **Token 管理**: 使用 tiktoken 精确计算 token，防止上下文溢出
- ✅ **自动消息总结**: 超过 token 限制时自动压缩历史消息
- ✅ **AgentLogger 日志系统**: 结构化 JSON 日志，完整追踪执行过程
- ✅ **MCP 集成**: 支持 Model Context Protocol，扩展外部工具能力
- ✅ **Skills 系统**: 内置专业 Skills，提供领域专家级指导
- ✅ **流式输出**: 支持 Server-Sent Events (SSE) 实时流式响应
- ✅ **会话记忆**: 使用 NoteTool 自动管理长期记忆和会话上下文
- ✅ **Web 前端**: ChatGPT 风格的 React 前端界面

### 📊 性能与监控
- ✅ **执行时间追踪**: 精确记录每个工具的执行时间（毫秒级）
- ✅ **Token 使用监控**: 实时追踪 token 使用情况和百分比
- ✅ **独立日志文件**: 每次运行生成时间戳日志，便于调试和审计

## 📁 项目结构

```
skill-agent/
├── src/
│   └── fastapi_agent/          # 主要代码
│       ├── main.py             # FastAPI 应用入口
│       ├── api/                # API 路由层
│       │   ├── deps.py         # 依赖注入（MCP 初始化）
│       │   └── v1/             # API v1 版本
│       │       ├── router.py   # 主路由
│       │       ├── agent.py    # Agent 端点（含流式）
│       │       ├── tools.py    # 工具列表端点
│       │       └── health.py   # 健康检查
│       ├── core/               # 核心组件
│       │   ├── agent.py        # Agent 核心逻辑
│       │   ├── llm_client.py   # LLM 客户端（含流式）
│       │   ├── config.py       # 配置管理
│       │   ├── token_manager.py    # Token 管理与消息总结
│       │   └── agent_logger.py     # 结构化日志系统
│       ├── tools/              # 工具实现
│       │   ├── base.py         # 工具基类
│       │   ├── file_tools.py   # 文件操作
│       │   ├── bash_tool.py    # Bash 执行
│       │   └── note_tool.py    # 会话记忆管理
│       ├── services/           # 服务层
│       │   └── mcp_manager.py  # MCP 集成管理
│       ├── skills/             # Skills 系统
│       │   ├── skill_tool.py   # Skill 工具实现
│       │   ├── document-skills/    # 文档处理 Skills
│       │   ├── mcp-builder/        # MCP 构建 Skill
│       │   └── ... (更多 Skills)
│       ├── schemas/            # Pydantic 数据模型
│       └── models/             # 数据模型定义
├── frontend/                   # React Web 前端
│   ├── src/
│   │   ├── pages/Chat.tsx      # 主聊天页面
│   │   ├── services/           # API 服务层
│   │   ├── stores/             # Zustand 状态管理
│   │   └── types/              # TypeScript 类型
│   ├── package.json
│   └── vite.config.ts
├── tests/                      # 测试套件
│   ├── api/
│   ├── core/
│   └── tools/
├── docs/                       # 文档
│   └── STREAMING.md            # 流式输出文档
├── skills/                     # 外部 Skills 定义
├── examples/                   # 示例代码
├── workspace/                  # Agent 工作目录
├── mcp.json                    # MCP 服务器配置
├── pyproject.toml             # 项目配置（uv）
├── test_frontend.sh            # 前端测试脚本
└── README.md
```

## 🚀 快速开始

### 1. 安装 uv（推荐）

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 安装项目依赖

```bash
# 使用 uv（推荐，速度更快）
uv sync

# 或使用传统方式
pip install -e .
```

### 3. 配置环境变量

创建 `.env` 文件：

```bash
# LLM 配置
LLM_API_KEY=your_api_key_here

# Anthropic Claude
LLM_API_BASE=https://api.anthropic.com
LLM_MODEL=claude-3-5-sonnet-20241022

# 或使用 MiniMax M2
# LLM_API_BASE=https://api.minimaxi.com/anthropic
# LLM_MODEL=MiniMax-M2

# Agent 配置
AGENT_MAX_STEPS=50
AGENT_WORKSPACE_DIR=./workspace

# 功能开关
ENABLE_MCP=true              # 启用 MCP 集成
ENABLE_SKILLS=true           # 启用 Skills 系统
MCP_CONFIG_PATH=mcp.json     # MCP 配置文件路径
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
# 使用 Make（推荐）
make dev

# 或使用 uv 直接运行
uv run uvicorn fastapi_agent.main:app --reload --host 0.0.0.0 --port 8000

# 或传统方式
python -m fastapi_agent.main
```

服务启动后，访问：
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **工具列表**: http://localhost:8000/api/v1/tools/

### 6. 启动前端（可选）

```bash
# 进入前端目录
cd frontend

# 安装依赖（首次运行）
npm install

# 启动开发服务器
npm run dev
```

前端服务启动后，访问：
- **Web 界面**: http://localhost:3001

## 💻 使用方法

### 通过 Web 界面（推荐）

1. 启动后端服务（见上方"启动服务"）
2. 启动前端服务：`cd frontend && npm run dev`
3. 访问 http://localhost:3001
4. 点击"新对话"创建会话
5. 输入消息，实时查看流式回复和工具调用过程

**前端功能**：
- 💬 ChatGPT 风格的对话界面
- 🔄 实时流式输出
- 🛠️ 工具调用可视化
- 💾 会话管理（创建、切换、删除）
- 📊 执行状态监控（步骤进度、Token 使用）
- 📝 Markdown 渲染

详细说明见 [frontend/README.md](./frontend/README.md)

### 通过 Python 客户端

```python
import httpx
import asyncio

async def run_agent():
    url = "http://localhost:8000/api/v1/agent/run"

    request_data = {
        "message": "使用 web_search_exa 搜索最新的 AI 新闻",
        "max_steps": 15,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=request_data)
        result = response.json()

        print(f"✅ 任务完成")
        print(f"📝 响应: {result['message']}")
        print(f"📊 步骤数: {result['steps']}")
        print(f"📋 日志文件: ~/.fastapi-agent/log/")

asyncio.run(run_agent())
```

### 通过 curl

```bash
# 普通请求
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建一个 Python 脚本，输出斐波那契数列的前 10 个数字",
    "max_steps": 10
  }'

# 流式请求（实时输出）
curl -N -X POST http://localhost:8000/api/v1/agent/run/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "使用 Markdown 格式介绍你自己",
    "max_steps": 10
  }'
```

### 通过交互式文档

访问 http://localhost:8000/docs 使用 Swagger UI 进行交互式测试。

## 🛠️ API 端点

### `POST /api/v1/agent/run`

运行 Agent 执行任务（普通模式）。

**请求体：**

```json
{
  "message": "任务描述",
  "workspace_dir": "./workspace",  // 可选，默认使用配置值
  "max_steps": 50,                 // 可选，默认使用配置值
  "session_id": "session-123"      // 可选，会话 ID（用于记忆管理）
}
```

**响应：**

```json
{
  "success": true,
  "message": "任务完成结果",
  "steps": 5,
  "logs": [
    {
      "type": "step",
      "step": 1,
      "max_steps": 50,
      "tokens": 1234,          // Token 使用情况
      "token_limit": 120000
    },
    {
      "type": "tool_call",
      "tool": "web_search_exa",
      "arguments": {...}
    },
    {
      "type": "tool_result",
      "tool": "web_search_exa",
      "success": true,
      "content": "...",
      "execution_time": 5.079  // 执行时间（秒）
    },
    ...
  ]
}
```

### `POST /api/v1/agent/run/stream`

运行 Agent 执行任务（流式模式，使用 Server-Sent Events）。

**请求体：**同 `/api/v1/agent/run`

**响应：**Server-Sent Events 流，事件类型包括：

- `thinking`: Agent 思考过程
- `content`: Agent 回复内容（增量）
- `tool_call`: 工具调用
- `tool_result`: 工具执行结果
- `step`: 步骤状态更新
- `complete`: 执行完成

详细说明见 [docs/STREAMING.md](./docs/STREAMING.md)

### `GET /api/v1/tools/`

列出所有可用工具（包括基础工具、MCP 工具和 Skills）。

### `GET /health`

健康检查端点。

## 🧰 可用工具

### 基础工具

1. **read_file**: 读取文件内容
   - 参数: `path`, `offset` (可选), `limit` (可选)

2. **write_file**: 写入文件
   - 参数: `path`, `content`

3. **edit_file**: 编辑文件（字符串替换）
   - 参数: `path`, `old_str`, `new_str`

4. **bash**: 执行 Bash 命令
   - 参数: `command`, `timeout` (可选)

5. **get_skill**: 加载 Skill 专家指导
   - 参数: `skill_name`

6. **note**: 会话记忆管理（自动启用）
   - `note_store`: 存储长期记忆
   - `note_query`: 查询相关记忆
   - `note_delete`: 删除记忆
   - `note_list`: 列出所有记忆

### MCP 工具（通过 mcp.json 配置）

- **web_search_exa**: Exa AI 网络搜索
- 更多工具可通过 MCP 服务器扩展...

### Skills 专家系统

内置 Skills 包括：
- **web-tools**: 网络抓取、API 交互工具
- **mcp-builder**: MCP 服务器开发指导
- **document-skills**: 文档处理（PDF、图片、DOCX 等）
- 更多 Skills 请查看 `src/fastapi_agent/skills/` 目录

## 🎯 核心功能详解

### Token 管理与消息总结

使用 tiktoken 进行精确 token 计算，防止上下文溢出：

```python
# 自动特性（无需手动配置）
# - 精确 token 计算（cl100k_base encoder）
# - 超过 120k tokens 时自动触发消息总结
# - 保留所有用户消息，压缩 agent 执行过程
# - 通常可减少 50-70% 的 token 使用量
```

配置选项（在 Agent 初始化时）：

```python
Agent(
    llm_client=llm_client,
    system_prompt="...",
    tools=[...],
    token_limit=120000,         # Token 限制（默认 120k）
    enable_summarization=True,  # 启用自动总结（默认 True）
)
```

### AgentLogger 结构化日志

每次运行自动生成独立的时间戳日志文件：

```bash
# 日志位置
~/.fastapi-agent/log/agent_run_YYYYMMDD_HHMMSS.log

# 日志包含
- STEP: 步骤信息 + Token 使用统计
- REQUEST: LLM 请求（消息、工具、token 数）
- RESPONSE: LLM 响应（内容、thinking、工具调用）
- TOOL_EXECUTION: 工具执行（参数、结果、执行时间）
- COMPLETION: 完成信息（最终响应、总步骤、原因）
```

示例日志：

```json
[4] TOOL_EXECUTION
{
  "tool_name": "web_search_exa",
  "arguments": {
    "query": "Gemini 3 release date",
    "numResults": 8
  },
  "success": true,
  "execution_time_seconds": 5.079,
  "result": "Title: Gemini 3: Release Date..."
}
```

### MCP 集成

支持 Model Context Protocol，轻松扩展外部工具：

```json
// mcp.json 示例
{
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y", "exa-mcp-server", "tools=web_search_exa"],
      "env": {"EXA_API_KEY": "your_key"},
      "disabled": false
    }
  }
}
```

MCP 工具会自动加载并在 Agent 中可用。

## 📊 与 Mini-Agent 的对比

| 特性 | Mini-Agent | FastAPI Agent |
|------|-----------|---------------|
| 接口方式 | CLI | RESTful API + Web UI |
| 部署方式 | 本地运行 | Web 服务 |
| 集成方式 | 命令行 | HTTP API + 前端界面 |
| Token 管理 | ✅ | ✅ |
| 消息总结 | ✅ | ✅ |
| 结构化日志 | ✅ | ✅ (AgentLogger) |
| 工具系统 | ✅ | ✅ |
| MCP 支持 | ✅ | ✅ |
| Skills 系统 | ❌ | ✅ |
| 执行时间追踪 | ❌ | ✅ |
| RESTful API | ❌ | ✅ |
| 流式输出 | ❌ | ✅ (SSE) |
| 会话记忆 | ❌ | ✅ (NoteTool) |
| Web 前端 | ❌ | ✅ (React + TypeScript) |

## 🔧 开发指南

### 添加新工具

1. 在 `src/fastapi_agent/tools/` 创建新工具文件
2. 继承 `Tool` 基类：

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
        # 实现工具逻辑
        return ToolResult(success=True, content="Result")
```

3. 在 `api/deps.py` 中注册工具

### 添加新 Skill

1. 在 `src/fastapi_agent/skills/` 创建 Skill 目录
2. 创建 `SKILL.md` 文件定义 Skill 内容
3. Skill 会自动被 `get_skill` 工具识别

### 运行测试

```bash
# 运行所有测试
make test

# 或使用 pytest
uv run pytest

# 运行特定测试
uv run pytest tests/core/test_agent.py
```

## 🚢 生产部署

### 使用 Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 复制项目文件
COPY . .

# 安装依赖
RUN uv sync --frozen

# 启动服务
CMD ["uv", "run", "uvicorn", "fastapi_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建和运行：

```bash
docker build -t fastapi-agent .
docker run -p 8000:8000 --env-file .env fastapi-agent
```

### 使用 systemd

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

启动服务：

```bash
sudo systemctl enable fastapi-agent
sudo systemctl start fastapi-agent
sudo systemctl status fastapi-agent
```

## 📝 日志查看

Agent 执行日志自动保存在 `~/.fastapi-agent/log/` 目录：

```bash
# 查看最新日志
ls -lht ~/.fastapi-agent/log/ | head -5

# 查看特定日志
cat ~/.fastapi-agent/log/agent_run_20251113_223233.log

# 实时监控（如果使用 systemd）
journalctl -u fastapi-agent -f
```

## 🐛 故障排除

### MCP 工具未加载

确保 `mcp.json` 配置正确，并且 `ENABLE_MCP=true`：

```bash
# 检查 MCP 配置
cat mcp.json

# 检查环境变量
echo $ENABLE_MCP

# 查看启动日志
grep "MCP" /tmp/direct_startup.log
```

### Token 超限

调整 `token_limit` 或启用自动总结：

```python
# 在创建 Agent 时
Agent(
    ...,
    token_limit=200000,         # 增加限制
    enable_summarization=True,  # 确保启用总结
)
```

### 模块导入错误

确保从项目根目录运行，并设置正确的 `PYTHONPATH`：

```bash
cd skill-agent
export PYTHONPATH=/path/to/skill-agent/src:$PYTHONPATH
python -m fastapi_agent.main
```

## 📚 参考资料

- [MiniMax Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Anthropic API 文档](https://docs.anthropic.com/)
- [MiniMax API 文档](https://platform.minimaxi.com/document)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [uv 包管理器](https://github.com/astral-sh/uv)
- [Server-Sent Events (SSE)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

## 📖 详细文档

- [流式输出实现](./docs/STREAMING.md) - 详细的流式输出功能和 API 说明
- [前端使用指南](./frontend/README.md) - React 前端的使用和开发指南
- [开发指南](./CLAUDE.md) - 贡献者和开发者指南

## 📄 License

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
