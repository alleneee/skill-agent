# 内置 Web Research Team 使用指南

## 概述

内置的 Web Research Team 包含两个专业 Agent:
- **Web Search Agent**: 使用 exa MCP 工具进行网络搜索
- **Web Spider Agent**: 使用 firecrawl MCP 工具进行网页爬取

Leader Agent 会自动协调这两个 Agent 来完成复杂的网络研究任务。

## 快速开始

### 1. 基础使用

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Search for latest AI news and summarize",
    "use_team": true
  }'
```

### 2. 带会话的多轮对话

```bash
# 第一轮
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Search for Python async programming articles",
    "use_team": true,
    "session_id": "my-session-123"
  }'

# 第二轮（有上下文）
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Crawl the first article and extract code examples",
    "use_team": true,
    "session_id": "my-session-123",
    "num_history_runs": 3
  }'
```

### 3. 自定义配置

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Search and crawl Python tutorials",
    "use_team": true,
    "config": {
      "max_steps": 30,
      "workspace_dir": "./my-workspace"
    }
  }'
```

## API 参数说明

### 请求参数 (AgentRequest)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 任务描述 |
| `use_team` | boolean | 否 | 是否使用内置 Team（默认 false） |
| `session_id` | string | 否 | 会话 ID，用于多轮对话 |
| `num_history_runs` | integer | 否 | 包含历史轮数（默认 3，范围 1-20） |
| `config` | object | 否 | 动态配置（见下方） |

### 动态配置 (AgentConfig)

| 参数 | 类型 | 说明 |
|------|------|------|
| `workspace_dir` | string | 工作目录路径 |
| `max_steps` | integer | 最大执行步数 |
| `system_prompt` | string | 自定义系统提示词 |

### 响应参数 (AgentResponse)

| 参数 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 执行是否成功 |
| `message` | string | Agent 响应内容 |
| `steps` | integer | 执行步数 |
| `logs` | array | 执行日志（单 Agent 模式） |
| `session_id` | string | 会话 ID |
| `run_id` | string | 本次运行 ID |

## 使用场景示例

### 场景 1: 快速搜索

适用于需要快速获取网络信息的场景。

```json
{
  "message": "Find the latest OpenAI announcements",
  "use_team": true
}
```

### 场景 2: 深度研究

搜索后爬取详细内容进行深度分析。

```json
{
  "message": "Search for machine learning tutorials, then crawl the top 3 results and compare their approaches",
  "use_team": true,
  "config": {
    "max_steps": 50
  }
}
```

### 场景 3: 持续研究

多轮对话保持上下文，进行持续研究。

```json
{
  "message": "Continue from the previous search and extract code examples from the second article",
  "use_team": true,
  "session_id": "research-project-001",
  "num_history_runs": 5
}
```

## Team 内部机制

### 成员配置

```python
# Web Search Agent
TeamMemberConfig(
    id="web_search_agent",
    name="Web Search Agent",
    role="Web Search Specialist",
    tools=["exa_search", ...],  # 自动过滤包含 "exa" 或 "search" 的工具
)

# Web Spider Agent
TeamMemberConfig(
    id="web_spider_agent",
    name="Web Spider Agent",
    role="Web Crawling Specialist",
    tools=["firecrawl", ...],  # 自动过滤包含 "firecrawl" 或 "crawl" 的工具
)
```

### Leader 协调策略

Leader 会根据任务自动决定委托策略：

1. **搜索任务** → 委托给 Web Search Agent
2. **爬取任务** → 委托给 Web Spider Agent
3. **综合任务** → 先搜索后爬取，或并行执行

### 工具过滤机制

Team 启动时会自动从所有可用工具中过滤出相关工具：

```python
# 搜索工具: 名称包含 "exa" 或 "search"
exa_tools = [t.name for t in available_tools
             if "exa" in t.name.lower() or "search" in t.name.lower()]

# 爬取工具: 名称包含 "firecrawl" 或 "crawl"
firecrawl_tools = [t.name for t in available_tools
                   if "firecrawl" in t.name.lower() or "crawl" in t.name.lower()]
```

## 前置要求

### 1. MCP 工具配置

确保 `mcp.json` 中配置了 exa 和 firecrawl 服务器：

```json
{
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-exa"],
      "env": {
        "EXA_API_KEY": "your-exa-api-key"
      }
    },
    "firecrawl": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-firecrawl"],
      "env": {
        "FIRECRAWL_API_KEY": "your-firecrawl-api-key"
      }
    }
  }
}
```

### 2. 环境变量

在 `.env` 文件中设置：

```bash
# LLM 配置
LLM_API_KEY=your-api-key
LLM_MODEL=openai:gpt-4o-mini

# MCP 启用
ENABLE_MCP=true
MCP_CONFIG_PATH=mcp.json
```

## 运行测试

### 使用测试脚本

```bash
# 确保服务器运行
make dev

# 在另一个终端运行测试
uv run python examples/test_builtin_team.py
```

### 单个测试

```bash
# 测试基础功能
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "Search for AI news", "use_team": true}'
```

## 故障排查

### Team 工具未加载

检查：
1. `ENABLE_MCP=true` 在 `.env` 中
2. `mcp.json` 配置正确
3. 查看启动日志确认 MCP 工具已加载
4. 使用 `GET /api/v1/tools/` 查看所有可用工具

### 工具过滤问题

如果工具没有正确分配给 Agent，检查工具名称是否包含关键词：
- 搜索工具应包含 "exa" 或 "search"
- 爬取工具应包含 "firecrawl" 或 "crawl"

### 委托失败

检查 member_id 是否正确：
- Web Search Agent: `web_search_agent`
- Web Spider Agent: `web_spider_agent`

## 扩展

### 添加自定义 Team

参考 `src/fastapi_agent/core/builtin_teams.py`：

```python
def create_custom_team(llm_client, available_tools, workspace_dir):
    config = TeamConfig(
        name="Custom Team",
        members=[
            TeamMemberConfig(
                id="custom_agent_1",
                name="Custom Agent 1",
                role="Specialist",
                tools=["tool1", "tool2"],
            ),
        ],
    )
    return Team(config=config, llm_client=llm_client, ...)
```

然后在 `api/deps.py` 中添加依赖函数，并在端点中注入使用。

## 相关文档

- `docs/RUNCONTEXT_DESIGN.md` - RunContext 设计理念
- `REFACTORING_SUMMARY.md` - Team 重构总结
- `examples/correct_team_usage.py` - 正确使用示例
- `examples/test_team_session.py` - 会话管理示例
