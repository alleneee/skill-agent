# 工具开发规范

## 基类契约

所有工具必须继承 `Tool` 基类 (`src/omni_agent/tools/base.py`)，实现以下接口：

| 属性/方法 | 类型 | 必须 | 说明 |
|-----------|------|------|------|
| `name` | `property -> str` | 是 | 工具名称，全局唯一，snake_case |
| `description` | `property -> str` | 是 | 工具描述，LLM 据此决定是否调用 |
| `parameters` | `property -> dict` | 是 | JSON Schema 格式的参数定义 |
| `execute(**kwargs)` | `async -> ToolResult` | 是 | 工具执行逻辑 |
| `instructions` | `property -> str\|None` | 否 | 注入到 System Prompt 的使用说明 |
| `add_instructions_to_prompt` | `property -> bool` | 否 | 是否启用 instructions 注入 |

## 返回值规范

所有 `execute()` 必须返回 `ToolResult`：

```python
class ToolResult(BaseModel):
    success: bool
    content: str = ""
    error: str | None = None
```

规则：
- 成功时 `success=True`，结果放 `content`，`error=None`
- 失败时 `success=False`，错误信息放 `error`
- `content` 超过 `output_limit`（默认 10000 字符）会被 ToolExecutor 自动截断
- 禁止在 `execute()` 中抛出未捕获异常，ToolExecutor 会兜底但日志不够详细

## 参数 Schema 设计

使用标准 JSON Schema 格式：

```python
@property
def parameters(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要读取的文件绝对路径",
            },
            "offset": {
                "type": "integer",
                "description": "起始行号（从 0 开始）",
                "default": 0,
            },
        },
        "required": ["file_path"],
    }
```

规则：
- `description` 要精确，LLM 依赖它理解参数含义
- 必填参数放 `required` 数组
- 可选参数设 `default` 值
- 枚举值用 `enum` 约束
- 嵌套对象用 `$ref` 或内联 `object`
- 禁止使用 `anyOf`/`oneOf` 等复杂组合，部分 LLM 解析不稳定

## description 编写规范

工具 description 直接决定 LLM 是否正确选择和调用工具：

- 首句说明工具的核心功能（做什么）
- 说明适用场景（什么时候用）
- 说明限制条件（什么时候不该用）
- 避免模糊词汇（"可能"、"大概"）
- 长度控制在 100-300 字符

好的示例：
```
"Read the contents of a file. Supports offset and limit for large files. Use absolute paths only."
```

差的示例：
```
"This tool can be used to read files from the filesystem."
```

## 工具注册

在 `src/omni_agent/api/deps.py` 的 `get_tools()` 中注册：

```python
def get_tools() -> list[Tool]:
    tools = [
        ReadTool(workspace_dir=workspace_dir),
        WriteTool(workspace_dir=workspace_dir),
        EditTool(workspace_dir=workspace_dir),
        BashTool(),
        MyNewTool(),  # 新增工具
    ]
    return tools
```

加载优先级：BaseTool > MCP Tools > Skills

## 错误处理

```python
async def execute(self, **kwargs) -> ToolResult:
    file_path = kwargs.get("file_path")
    if not file_path:
        return ToolResult(success=False, error="file_path is required")

    path = Path(file_path)
    if not path.exists():
        return ToolResult(success=False, error=f"File not found: {file_path}")

    try:
        content = path.read_text(encoding="utf-8")
        return ToolResult(success=True, content=content)
    except PermissionError:
        return ToolResult(success=False, error=f"Permission denied: {file_path}")
    except UnicodeDecodeError:
        return ToolResult(success=False, error=f"Binary file not supported: {file_path}")
```

规则：
- 参数校验在前，执行逻辑在后
- 错误信息包含具体参数值，方便 LLM 理解和修正
- 区分不同错误类型，给出有意义的错误描述
- 不要返回 Python traceback 给 LLM，只返回人可读信息

## 安全约束

- 文件操作工具必须接受 `workspace_dir` 参数，限制操作范围
- 禁止在工具中硬编码密钥或凭证
- Bash 工具必须设置超时（默认 120 秒）
- 工具不得直接修改 Agent 状态（通过 ToolResult 返回数据）

## 测试模式

每个工具对应 `tests/tools/test_<tool_name>.py`：

```python
import pytest
from omni_agent.tools.my_tool import MyTool

@pytest.fixture
def tool(tmp_path):
    return MyTool(workspace_dir=str(tmp_path))

class TestMyTool:
    @pytest.mark.asyncio
    async def test_execute_success(self, tool, tmp_path):
        (tmp_path / "test.txt").write_text("hello")
        result = await tool.execute(file_path=str(tmp_path / "test.txt"))
        assert result.success is True
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        result = await tool.execute(file_path="/nonexistent")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_param(self, tool):
        result = await tool.execute()
        assert result.success is False

    def test_schema_valid(self, tool):
        schema = tool.to_schema()
        assert schema["name"] == tool.name
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"
```

测试覆盖要求：
- 正常路径 + 错误路径 + 边界条件
- Schema 格式验证
- 参数缺失/非法处理
- 覆盖率 >= 80%

## MCP 工具特殊说明

MCP 工具通过 `mcp_loader.py` 在启动时从外部 Server 加载，不需手写 Tool 子类。

开发自定义 MCP Server 时需注意：
- 工具名称不得与已有 BaseTool/内部工具冲突
- 在 `mcp.json` 中配置，支持 stdio/SSE/HTTP 三种传输
- 通过 `disabled: true` 可临时禁用而不删除配置
- 调试日志写入 `/tmp/mcp_init_debug.log`

## Skill 与 Tool 的区别

| 维度 | Tool | Skill |
|------|------|-------|
| 本质 | 可执行代码 | 知识文档 (SKILL.md) |
| 触发 | LLM 通过 tool_call 调用 | LLM 通过 `get_skill` 工具加载 |
| 输出 | ToolResult（数据） | Prompt 注入（指导） |
| 位置 | `src/omni_agent/tools/` | `src/omni_agent/skills/` 或 `./skills/` |
