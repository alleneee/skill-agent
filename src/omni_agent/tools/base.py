"""工具基类。"""

from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Tool execution result."""

    success: bool
    content: str = ""
    error: str | None = None


class Tool:
    """Base class for all tools."""

    @property
    def name(self) -> str:
        """Tool name."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Tool description."""
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        """Tool parameters schema (JSON Schema format)."""
        raise NotImplementedError

    @property
    def instructions(self) -> str | None:
        """Tool usage instructions to be added to system prompt.

        返回 None 表示不添加说明到系统提示。
        返回字符串表示要添加的使用说明。

        Example:
            return '''
            When using this tool:
            - Always check the result carefully
            - Use absolute paths when possible
            '''
        """
        return None

    @property
    def add_instructions_to_prompt(self) -> bool:
        """是否将工具说明添加到系统提示."""
        return False

    async def execute(self, *args, **kwargs) -> ToolResult:
        """Execute the tool with arbitrary arguments."""
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        """Convert tool to Anthropic tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
