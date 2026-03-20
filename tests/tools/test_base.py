from typing import Any

import pytest

from omni_agent.tools.base import Tool, ToolResult


class TestToolResult:
    def test_creation_with_all_fields(self):
        result = ToolResult(success=True, content="output", error="some error")
        assert result.success is True
        assert result.content == "output"
        assert result.error == "some error"

    def test_default_content_is_empty(self):
        result = ToolResult(success=False)
        assert result.content == ""

    def test_default_error_is_none(self):
        result = ToolResult(success=True)
        assert result.error is None

    def test_success_true(self):
        result = ToolResult(success=True, content="done")
        assert result.success is True
        assert result.content == "done"
        assert result.error is None

    def test_success_false_with_error(self):
        result = ToolResult(success=False, error="failed")
        assert result.success is False
        assert result.error == "failed"

    def test_serialization(self):
        result = ToolResult(success=True, content="hello", error=None)
        data = result.model_dump()
        assert data == {"success": True, "content": "hello", "error": None}

    def test_serialization_roundtrip(self):
        original = ToolResult(success=False, content="data", error="err")
        data = original.model_dump()
        restored = ToolResult(**data)
        assert restored == original


class TestToolBaseClass:
    def test_name_raises_not_implemented(self):
        tool = Tool()
        with pytest.raises(NotImplementedError):
            _ = tool.name

    def test_description_raises_not_implemented(self):
        tool = Tool()
        with pytest.raises(NotImplementedError):
            _ = tool.description

    def test_parameters_raises_not_implemented(self):
        tool = Tool()
        with pytest.raises(NotImplementedError):
            _ = tool.parameters

    async def test_execute_raises_not_implemented(self):
        tool = Tool()
        with pytest.raises(NotImplementedError):
            await tool.execute()

    def test_instructions_default_is_none(self):
        tool = Tool()
        assert tool.instructions is None

    def test_add_instructions_to_prompt_default_is_false(self):
        tool = Tool()
        assert tool.add_instructions_to_prompt is False


class ConcreteTool(Tool):
    @property
    def name(self) -> str:
        return "test_tool"

    @property
    def description(self) -> str:
        return "A test tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "input value"},
            },
            "required": ["input"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"received: {kwargs.get('input', '')}")


class ConcreteToolWithInstructions(ConcreteTool):
    @property
    def instructions(self) -> str:
        return "Use this tool carefully."

    @property
    def add_instructions_to_prompt(self) -> bool:
        return True


class TestToSchema:
    def test_schema_keys(self):
        tool = ConcreteTool()
        schema = tool.to_schema()
        assert set(schema.keys()) == {"name", "description", "input_schema"}

    def test_schema_name(self):
        tool = ConcreteTool()
        schema = tool.to_schema()
        assert schema["name"] == "test_tool"

    def test_schema_description(self):
        tool = ConcreteTool()
        schema = tool.to_schema()
        assert schema["description"] == "A test tool"

    def test_schema_input_schema(self):
        tool = ConcreteTool()
        schema = tool.to_schema()
        assert schema["input_schema"]["type"] == "object"
        assert "input" in schema["input_schema"]["properties"]
        assert schema["input_schema"]["required"] == ["input"]


class TestConcreteTool:
    async def test_execute_returns_tool_result(self):
        tool = ConcreteTool()
        result = await tool.execute(input="hello")
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.content == "received: hello"

    async def test_execute_without_input(self):
        tool = ConcreteTool()
        result = await tool.execute()
        assert result.success is True
        assert result.content == "received: "

    def test_name_property(self):
        tool = ConcreteTool()
        assert tool.name == "test_tool"

    def test_description_property(self):
        tool = ConcreteTool()
        assert tool.description == "A test tool"

    def test_parameters_property(self):
        tool = ConcreteTool()
        params = tool.parameters
        assert params["type"] == "object"

    def test_instructions_inherited_default(self):
        tool = ConcreteTool()
        assert tool.instructions is None
        assert tool.add_instructions_to_prompt is False

    def test_instructions_override(self):
        tool = ConcreteToolWithInstructions()
        assert tool.instructions == "Use this tool carefully."
        assert tool.add_instructions_to_prompt is True
