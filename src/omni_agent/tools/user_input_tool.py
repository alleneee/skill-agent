"""用户输入工具，用于人机交互循环。

此工具允许 agents 在需要时暂停执行并向用户请求额外信息。

灵感来自 agno 的 UserControlFlowTools 实现。
"""

from typing import Any

from pydantic import BaseModel, Field

from omni_agent.tools.base import Tool, ToolResult


class UserInputField(BaseModel):
    """单个用户输入字段的模式。"""

    field_name: str = Field(..., description="需要获取输入的字段名称")
    field_type: str = Field(
        default="str", description="字段类型 (str, int, float, bool, list, dict)"
    )
    field_description: str = Field(..., description="字段描述")
    value: Any | None = Field(default=None, description="用户提供的值")


class UserInputRequest(BaseModel):
    """包含多个字段的用户输入请求。"""

    fields: list[UserInputField] = Field(default_factory=list, description="需要用户输入的字段列表")
    context: str | None = Field(default=None, description="解释为什么需要输入的附加上下文")


class GetUserInputTool(Tool):
    """在 agents 执行期间请求用户输入的工具。

    当 agents 需要额外信息才能继续时，可以调用此工具暂停执行并向用户请求输入。

    工具执行本身不做任何事情 - agents 循环检测到此工具调用后会处理暂停/恢复逻辑。
    """

    TOOL_NAME = "get_user_input"

    @property
    def name(self) -> str:
        return self.TOOL_NAME

    @property
    def description(self) -> str:
        return (
            "Request additional information from the user. Use this when you need "
            "clarification or missing information to complete a task. Provide all "
            "required fields as if the user were filling out a form."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_input_fields": {
                    "type": "array",
                    "description": "List of fields requiring user input",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_name": {
                                "type": "string",
                                "description": "The name of the field",
                            },
                            "field_type": {
                                "type": "string",
                                "description": "The type of the field (str, int, float, bool, list, dict)",
                                "enum": ["str", "int", "float", "bool", "list", "dict"],
                            },
                            "field_description": {
                                "type": "string",
                                "description": "A description of what information is needed",
                            },
                        },
                        "required": ["field_name", "field_description"],
                    },
                },
                "context": {
                    "type": "string",
                    "description": "Additional context explaining why this input is needed",
                },
            },
            "required": ["user_input_fields"],
        }

    @property
    def instructions(self) -> str:
        return """
## User Input Tool Guidelines

You have access to the `get_user_input` tool to request information from the user.

### When to Use:
- When you don't have enough information to complete a task
- When you need clarification on ambiguous requirements
- When you need user confirmation or preferences
- When critical information is missing (e.g., API keys, file paths, configuration values)

### How to Use:
1. Call `get_user_input` with the fields you need
2. Provide clear, concise descriptions for each field
3. Specify the expected type for each field
4. Include context explaining why the information is needed

### Important Guidelines:
- **Don't guess or make up information** - ask the user instead
- **Include only required fields** - don't ask for information you already have
- **Provide clear descriptions** - help the user understand what's needed
- **Use appropriate field types** - this helps with input validation
- **Don't ask the same question twice** - accept whatever the user provides

### Example:
```json
{
    "user_input_fields": [
        {
            "field_name": "api_key",
            "field_type": "str",
            "field_description": "Your API key for the external service"
        },
        {
            "field_name": "output_format",
            "field_type": "str",
            "field_description": "Preferred output format (json, csv, or xml)"
        }
    ],
    "context": "I need these details to configure the data export"
}
```
"""

    @property
    def add_instructions_to_prompt(self) -> bool:
        return True

    async def execute(
        self, user_input_fields: list[dict[str, str]], context: str | None = None, **kwargs
    ) -> ToolResult:
        """执行工具 - 实际逻辑由 agents 循环处理。

        此方法会被调用，但真正的处理发生在 agents 的执行循环中，
        它会检测到此工具并暂停等待用户输入。

        Args:
            user_input_fields: 需要输入的字段定义列表
            context: 解释为什么需要输入的可选上下文

        Returns:
            表示请求已注册的 ToolResult
        """
        # The actual pause/resume logic is handled by the agents loop
        # This just returns a placeholder result
        return ToolResult(
            success=True, content="User input request registered. Waiting for user response."
        )


def is_user_input_tool_call(tool_name: str) -> bool:
    """检查工具调用是否为用户输入工具。"""
    return tool_name == GetUserInputTool.TOOL_NAME


def parse_user_input_fields(arguments: dict[str, Any]) -> list[UserInputField]:
    """从工具调用参数中解析用户输入字段。

    Args:
        arguments: 包含 user_input_fields 的工具调用参数

    Returns:
        UserInputField 对象列表
    """
    fields = []
    for field_data in arguments.get("user_input_fields", []):
        fields.append(
            UserInputField(
                field_name=field_data.get("field_name", ""),
                field_type=field_data.get("field_type", "str"),
                field_description=field_data.get("field_description", ""),
            )
        )
    return fields
