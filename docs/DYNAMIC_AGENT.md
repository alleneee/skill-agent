# Dynamic Agent Configuration

本文档介绍如何根据请求动态配置 Agent，而不是使用固定的全局配置。

## 概述

从现在开始，你可以通过 API 请求动态定制 Agent 的行为：

- ✅ **自定义工作空间**：为不同用户或任务使用独立的工作目录
- ✅ **选择性工具加载**：只加载特定任务需要的工具，减少开销
- ✅ **动态 token 限制**：根据任务复杂度调整 token 管理策略
- ✅ **自定义系统提示**：为特定场景提供专门的 system prompt
- ✅ **按需 MCP 配置**：为不同场景加载不同的 MCP 工具集

## 架构变化

### 之前（静态配置）

```python
# 所有请求使用相同的配置
agent = get_agent()  # 从全局 settings 读取
```

### 现在（动态配置）

```python
# 每个请求可以有不同的配置
agent = await agent_factory.create_agent(llm_client, config)
```

## 使用方法

### 1. 基本用法（使用默认配置）

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "读取当前目录的 README.md 文件"
  }'
```

不提供 `config` 字段时，使用 `.env` 中的默认配置。

### 2. 自定义工作空间

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建一个 hello.txt 文件",
    "config": {
      "workspace_dir": "/tmp/user-123-workspace"
    }
  }'
```

**用途**：
- 多用户隔离（每个用户有独立的工作空间）
- 临时任务使用临时目录
- 项目级别隔离

### 3. 限制执行步数

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "计算 1+1",
    "config": {
      "max_steps": 3
    }
  }'
```

**用途**：
- 简单任务限制资源消耗
- 防止复杂任务超时
- 快速响应场景

### 4. 选择性加载工具

#### 场景 1：只读操作（只加载 read 工具）

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我分析这个项目的代码结构",
    "config": {
      "enable_base_tools": true,
      "base_tools_filter": ["read"],
      "enable_mcp_tools": false,
      "enable_skills": false,
      "enable_rag": false
    }
  }'
```

**好处**：
- 提高安全性（禁止写操作）
- 减少工具列表，降低 token 消耗
- 更快的响应速度

#### 场景 2：代码生成任务（read + write + edit）

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我创建一个 Python 爬虫脚本",
    "config": {
      "enable_base_tools": true,
      "base_tools_filter": ["read", "write", "edit"],
      "enable_mcp_tools": false,
      "enable_skills": true
    }
  }'
```

#### 场景 3：系统运维任务（read + bash）

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "检查系统磁盘使用情况",
    "config": {
      "enable_base_tools": true,
      "base_tools_filter": ["read", "bash"],
      "enable_mcp_tools": false
    }
  }'
```

### 5. 禁用所有 MCP 工具

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "分析代码",
    "config": {
      "enable_mcp_tools": false
    }
  }'
```

**用途**：
- 需要快速响应的场景
- 不需要外部工具的任务
- 减少不必要的工具调用

### 6. 选择特定 MCP 工具

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "搜索关于 Python asyncio 的信息",
    "config": {
      "enable_mcp_tools": true,
      "mcp_tools_filter": ["web_search_exa", "get_code_context_exa"]
    }
  }'
```

**用途**：
- 只加载特定场景需要的 MCP 工具
- 减少工具描述的 token 消耗
- 提高 LLM 工具选择的准确性

### 7. 使用自定义 MCP 配置

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "执行特殊任务",
    "config": {
      "mcp_config_path": "/path/to/custom-mcp.json"
    }
  }'
```

**用途**：
- 不同场景使用不同的 MCP 工具集
- A/B 测试不同的 MCP 配置
- 特殊项目需要特殊工具

### 8. 自定义 System Prompt

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "写一段代码",
    "config": {
      "system_prompt": "你是一个专业的 Python 开发者，擅长编写干净、高效的代码。你总是遵循 PEP8 规范，并添加详细的文档字符串。"
    }
  }'
```

**用途**：
- 特定领域的专家 Agent（医疗、法律、金融等）
- 特定编程语言的专家
- 特定风格的代码生成

### 9. Token 管理配置

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "长对话任务",
    "config": {
      "token_limit": 150000,
      "enable_summarization": true
    }
  }'
```

**用途**：
- 长对话需要更高的 token 限制
- 短任务可以禁用自动摘要以提高性能

### 10. 组合配置

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我创建一个 Web API",
    "config": {
      "workspace_dir": "/tmp/project-api",
      "max_steps": 30,
      "token_limit": 100000,
      "enable_base_tools": true,
      "base_tools_filter": ["read", "write", "edit", "bash"],
      "enable_mcp_tools": true,
      "mcp_tools_filter": ["get_code_context_exa"],
      "enable_skills": true,
      "enable_rag": false,
      "system_prompt": "你是一个 FastAPI 专家，擅长创建 RESTful API。"
    }
  }'
```

## Python SDK 使用示例

```python
import httpx

async def create_custom_agent_task():
    """使用动态配置创建 agent 任务"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/agent/run",
            json={
                "message": "分析这个项目",
                "config": {
                    "workspace_dir": "/tmp/analysis",
                    "max_steps": 20,
                    "enable_base_tools": True,
                    "base_tools_filter": ["read"],
                    "enable_mcp_tools": False
                }
            }
        )
        return response.json()
```

## 实际应用场景

### 场景 1：多租户 SaaS 平台

每个租户使用独立的工作空间和配置：

```python
def create_tenant_config(tenant_id: str):
    return {
        "workspace_dir": f"/data/tenants/{tenant_id}/workspace",
        "max_steps": 50,
        "enable_base_tools": True,
        # 企业客户可以使用 MCP 工具
        "enable_mcp_tools": tenant_id.startswith("enterprise_"),
    }

# 请求示例
request = {
    "message": user_input,
    "config": create_tenant_config("enterprise_user_123")
}
```

### 场景 2：教育平台（限制学生权限）

```python
def create_student_config():
    return {
        "max_steps": 10,  # 限制执行步数
        "enable_base_tools": True,
        "base_tools_filter": ["read"],  # 只允许读操作
        "enable_mcp_tools": False,  # 禁用外部工具
        "system_prompt": "你是一个编程教学助手，帮助学生理解代码，但不直接提供完整答案。"
    }
```

### 场景 3：代码审查服务

```python
def create_code_review_config():
    return {
        "workspace_dir": "/tmp/code-review",
        "max_steps": 15,
        "enable_base_tools": True,
        "base_tools_filter": ["read"],  # 只读模式
        "enable_mcp_tools": True,
        "mcp_tools_filter": ["get_code_context_exa"],  # 只使用代码上下文工具
        "system_prompt": """你是一个专业的代码审查员，擅长发现：
        - 潜在的 bug
        - 性能问题
        - 安全漏洞
        - 代码风格问题
        请提供详细的改进建议。"""
    }
```

### 场景 4：临时脚本生成

```python
def create_script_generation_config():
    return {
        "workspace_dir": "/tmp/scripts",
        "max_steps": 20,
        "enable_base_tools": True,
        "base_tools_filter": ["write", "edit", "bash"],
        "enable_mcp_tools": True,
        "mcp_tools_filter": ["get_code_context_exa"],
        "enable_skills": True
    }
```

## 性能优化建议

### 1. 减少工具数量

工具越少，LLM 的 context 越小，响应越快：

```json
{
  "config": {
    "enable_base_tools": true,
    "base_tools_filter": ["read", "write"],  // 只加载需要的工具
    "enable_mcp_tools": false  // 禁用不需要的 MCP 工具
  }
}
```

**预期效果**：
- 减少 20-30% 的 token 消耗
- 减少 10-15% 的响应时间
- 提高工具选择准确性

### 2. 调整 max_steps

简单任务使用较小的 `max_steps`：

```json
{
  "config": {
    "max_steps": 5  // 简单查询任务
  }
}
```

### 3. 按需加载 MCP 工具

不要一次性加载所有 MCP 工具：

```json
{
  "config": {
    "enable_mcp_tools": true,
    "mcp_tools_filter": ["web_search_exa"]  // 只加载需要的
  }
}
```

## 向后兼容性

旧的 API 调用方式仍然支持：

```json
{
  "message": "任务",
  "workspace_dir": "/tmp/workspace",  // DEPRECATED
  "max_steps": 50  // DEPRECATED
}
```

会自动转换为：

```json
{
  "message": "任务",
  "config": {
    "workspace_dir": "/tmp/workspace",
    "max_steps": 50
  }
}
```

## 配置优先级

1. **请求级配置** (`config` 字段) - 最高优先级
2. **向后兼容字段** (`workspace_dir`, `max_steps`) - 中等优先级
3. **全局配置** (`.env` 文件) - 最低优先级

## 注意事项

### 1. MCP 工具加载

- 全局 MCP 工具在启动时加载（`mcp.json`）
- 可以通过 `mcp_config_path` 使用自定义配置
- 自定义 MCP 配置会按需加载，完成后自动清理连接

### 2. 工具过滤

- `base_tools_filter`：必须是有效的工具名称列表
  - 有效值：`["read", "write", "edit", "bash", "session_note", "recall_note"]`
- `mcp_tools_filter`：必须是已加载 MCP 工具的名称
  - 可以通过 `GET /api/v1/tools/` 查看所有可用工具

### 3. 安全考虑

- 限制用户可以访问的工作空间路径
- 限制 `max_steps` 的最大值防止资源滥用
- 禁用危险工具（如 `bash`）对于不受信任的输入

## 监控和调试

查看请求使用的工具：

```bash
# 查看所有可用工具
curl http://localhost:8000/api/v1/tools/

# 检查响应日志
# 日志位置：~/.fastapi-agent/log/
```

## 总结

动态 Agent 配置让你可以：

1. ✅ **灵活性**：根据不同场景动态调整 agent 行为
2. ✅ **性能**：只加载需要的工具，减少开销
3. ✅ **安全性**：限制特定场景的权限
4. ✅ **多租户**：每个用户/租户独立配置
5. ✅ **可扩展**：轻松支持新的使用场景

开始使用动态配置，让你的 Agent 更加智能和高效！
