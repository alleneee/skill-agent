from typing import Any

from omni_agent.core.tool_executor import ToolExecutionResult, ToolExecutor
from omni_agent.tools.base import Tool, ToolResult


class EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo input"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    async def execute(self, text: str = "") -> ToolResult:
        return ToolResult(success=True, content=text)


class FailTool(Tool):
    @property
    def name(self) -> str:
        return "fail"

    @property
    def description(self) -> str:
        return "Always fails"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self) -> ToolResult:
        raise RuntimeError("Tool crashed")


class TestToolExecutorInit:
    def test_default_init(self) -> None:
        executor = ToolExecutor()
        assert executor.tool_names == []
        assert executor._output_limit == 10000

    def test_with_tools(self) -> None:
        echo = EchoTool()
        executor = ToolExecutor(tools={"echo": echo})
        assert executor.tool_names == ["echo"]

    def test_custom_output_limit(self) -> None:
        executor = ToolExecutor(output_limit=500)
        assert executor._output_limit == 500


class TestToolExecutorMethods:
    def test_set_tools(self) -> None:
        executor = ToolExecutor()
        echo = EchoTool()
        executor.set_tools({"echo": echo})
        assert executor.tool_names == ["echo"]

    def test_get_tool(self) -> None:
        echo = EchoTool()
        executor = ToolExecutor(tools={"echo": echo})
        assert executor.get_tool("echo") is echo
        assert executor.get_tool("missing") is None

    def test_has_tool(self) -> None:
        echo = EchoTool()
        executor = ToolExecutor(tools={"echo": echo})
        assert executor.has_tool("echo") is True
        assert executor.has_tool("missing") is False


class TestExecuteSingle:
    async def test_successful_execution(self) -> None:
        executor = ToolExecutor(tools={"echo": EchoTool()})
        result = await executor.execute_single("call_1", "echo", {"text": "hello"})
        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "echo"
        assert result.tool_call_id == "call_1"
        assert result.result.success is True
        assert result.result.content == "hello"
        assert result.execution_time >= 0

    async def test_unknown_tool(self) -> None:
        executor = ToolExecutor()
        result = await executor.execute_single("call_1", "nonexistent", {})
        assert result.result.success is False
        assert "Unknown tool" in result.result.error

    async def test_tool_exception_caught(self) -> None:
        executor = ToolExecutor(tools={"fail": FailTool()})
        result = await executor.execute_single("call_1", "fail", {})
        assert result.result.success is False
        assert "Tool execution failed" in result.result.error
        assert "Tool crashed" in result.result.error

    async def test_output_truncation(self) -> None:
        executor = ToolExecutor(tools={"echo": EchoTool()}, output_limit=10)
        result = await executor.execute_single("call_1", "echo", {"text": "a" * 100})
        assert result.result.success is True
        assert len(result.result.content) < 100
        assert "truncated" in result.result.content


class TestExecuteBatch:
    async def test_empty_batch(self) -> None:
        executor = ToolExecutor()
        results = await executor.execute_batch([])
        assert results == []

    async def test_serial_batch(self) -> None:
        executor = ToolExecutor(tools={"echo": EchoTool()})
        calls = [
            ("call_1", "echo", {"text": "a"}),
            ("call_2", "echo", {"text": "b"}),
        ]
        results = await executor.execute_batch(calls)
        assert len(results) == 2
        assert results[0].result.content == "a"
        assert results[1].result.content == "b"

    async def test_parallel_batch(self) -> None:
        executor = ToolExecutor(
            tools={"echo": EchoTool()},
            parallel_execution=True,
        )
        calls = [
            ("call_1", "echo", {"text": "a"}),
            ("call_2", "echo", {"text": "b"}),
        ]
        results = await executor.execute_batch(calls)
        assert len(results) == 2

    async def test_mixed_success_failure(self) -> None:
        executor = ToolExecutor(tools={"echo": EchoTool(), "fail": FailTool()})
        calls = [
            ("call_1", "echo", {"text": "ok"}),
            ("call_2", "fail", {}),
        ]
        results = await executor.execute_batch(calls)
        assert results[0].result.success is True
        assert results[1].result.success is False


class TestTruncateOutput:
    def test_no_truncation_within_limit(self) -> None:
        executor = ToolExecutor(output_limit=100)
        assert executor._truncate_output("short") == "short"

    def test_truncation_over_limit(self) -> None:
        executor = ToolExecutor(output_limit=10)
        result = executor._truncate_output("a" * 50)
        assert "truncated" in result
        assert "50 chars" in result

    def test_empty_content(self) -> None:
        executor = ToolExecutor()
        assert executor._truncate_output("") == ""

    def test_none_like_empty(self) -> None:
        executor = ToolExecutor()
        assert executor._truncate_output("") == ""
