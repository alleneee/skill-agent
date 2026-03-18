"""工具执行器模块.

处理 Agent 的工具调用，支持：
- 单个工具执行
- 批量工具执行（串行/并行）
- 输出长度截断
- 执行时间统计

使用示例:
    executor = ToolExecutor(tools={"bash": BashTool()})
    result = await executor.execute_single(
        tool_call_id="call_123",
        function_name="bash",
        arguments={"command": "ls"}
    )
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from omni_agent.tools.base import Tool, ToolResult


@dataclass
class ToolExecutionResult:
    tool_name: str
    tool_call_id: str
    result: ToolResult
    execution_time: float
    arguments: dict[str, Any]


class ToolExecutor:
    def __init__(
        self,
        tools: dict[str, Tool] | None = None,
        output_limit: int = 10000,
        parallel_execution: bool = False,
    ) -> None:
        self._tools = tools or {}
        self._output_limit = output_limit
        self._parallel_execution = parallel_execution

    def set_tools(self, tools: dict[str, Tool]) -> None:
        self._tools = tools

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute_single(
        self,
        tool_call_id: str,
        function_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        start_time = time.time()

        if function_name not in self._tools:
            result = ToolResult(
                success=False,
                content="",
                error=f"Unknown tool: {function_name}",
            )
        else:
            try:
                tool = self._tools[function_name]
                result = await tool.execute(**arguments)
                if result.success:
                    result = ToolResult(
                        success=True,
                        content=self._truncate_output(result.content),
                        error=None,
                    )
            except Exception as e:
                result = ToolResult(
                    success=False,
                    content="",
                    error=f"Tool execution failed: {str(e)}",
                )

        return ToolExecutionResult(
            tool_name=function_name,
            tool_call_id=tool_call_id,
            result=result,
            execution_time=time.time() - start_time,
            arguments=arguments,
        )

    async def execute_batch(
        self,
        tool_calls: list[tuple[str, str, dict[str, Any]]],
    ) -> list[ToolExecutionResult]:
        if not tool_calls:
            return []

        if self._parallel_execution and len(tool_calls) > 1:
            tasks = [self.execute_single(call_id, name, args) for call_id, name, args in tool_calls]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for call_id, name, args in tool_calls:
                result = await self.execute_single(call_id, name, args)
                results.append(result)
            return results

    def _truncate_output(self, content: str) -> str:
        if not content:
            return content
        if len(content) > self._output_limit:
            return content[: self._output_limit] + f"\n...[truncated, total {len(content)} chars]"
        return content
