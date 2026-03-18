"""Ralph 模式专用工具集.

提供工具结果缓存访问和工作记忆操作能力。
"""

from typing import Any

from omni_agent.core.ralph import ContextManager, WorkingMemory
from omni_agent.tools.base import Tool, ToolResult


class GetCachedResultTool(Tool):
    """获取缓存的工具结果.

    在 Ralph 模式下，工具结果会被摘要化以节省上下文。
    此工具用于检索之前执行的工具的完整结果内容。
    """

    def __init__(self, context_manager: ContextManager) -> None:
        self._context_manager = context_manager

    @property
    def name(self) -> str:
        return "get_cached_result"

    @property
    def description(self) -> str:
        return (
            "Retrieve the full content of a previously executed tool result. "
            "Use this when you need complete details that were summarized earlier. "
            "Provide the tool_call_id from the original execution."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_call_id": {
                    "type": "string",
                    "description": "The ID of the tool call to retrieve full result for",
                },
            },
            "required": ["tool_call_id"],
        }

    async def execute(self, tool_call_id: str) -> ToolResult:
        content = self._context_manager.get_full_tool_result(tool_call_id)
        if content is None:
            return ToolResult(
                success=False,
                error=f"No cached result found for tool_call_id: {tool_call_id}",
            )
        return ToolResult(success=True, content=content)


class UpdateWorkingMemoryTool(Tool):
    """更新工作记忆.

    允许 Agent 在 Ralph 迭代过程中记录进度、发现、待办事项、决策和错误。
    这些信息会持久化到文件系统，跨迭代保持。
    """

    def __init__(self, working_memory: WorkingMemory) -> None:
        self._memory = working_memory

    @property
    def name(self) -> str:
        return "update_working_memory"

    @property
    def description(self) -> str:
        return (
            "Update the working memory with progress, findings, decisions, or todos. "
            "This persists information across Ralph iterations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "add_progress",
                        "add_finding",
                        "add_todo",
                        "complete_todo",
                        "add_decision",
                        "add_error",
                    ],
                    "description": "The type of memory update to perform",
                },
                "content": {
                    "type": "string",
                    "description": "The content to add (description, finding, task, or error message)",
                },
                "reason": {
                    "type": "string",
                    "description": "For decisions, the reasoning behind the decision",
                },
                "todo_key": {
                    "type": "string",
                    "description": "For complete_todo action, the key of the todo to mark complete",
                },
                "context": {
                    "type": "string",
                    "description": "For errors, additional context about the error",
                },
            },
            "required": ["action", "content"],
        }

    async def execute(
        self,
        action: str,
        content: str,
        reason: str | None = None,
        todo_key: str | None = None,
        context: str | None = None,
    ) -> ToolResult:
        try:
            if action == "add_progress":
                self._memory.add_progress(content)
                return ToolResult(success=True, content="Progress recorded")

            elif action == "add_finding":
                self._memory.add_finding(content)
                return ToolResult(success=True, content="Finding recorded")

            elif action == "add_todo":
                key = self._memory.add_todo(content)
                return ToolResult(success=True, content=f"Todo added with key: {key}")

            elif action == "complete_todo":
                if not todo_key:
                    return ToolResult(
                        success=False, error="todo_key is required for complete_todo action"
                    )
                success = self._memory.complete_todo(todo_key)
                if success:
                    return ToolResult(success=True, content=f"Todo {todo_key} marked complete")
                return ToolResult(success=False, error=f"Todo {todo_key} not found")

            elif action == "add_decision":
                if not reason:
                    return ToolResult(
                        success=False, error="reason is required for add_decision action"
                    )
                self._memory.add_decision(content, reason)
                return ToolResult(success=True, content="Decision recorded")

            elif action == "add_error":
                self._memory.add_error(content, context)
                return ToolResult(success=True, content="Error recorded")

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GetWorkingMemoryTool(Tool):
    """获取工作记忆.

    检索当前工作记忆的摘要，包括进度、发现、待办事项、决策和错误。
    支持按类别过滤或获取全部内容。
    """

    def __init__(self, working_memory: WorkingMemory) -> None:
        self._memory = working_memory

    @property
    def name(self) -> str:
        return "get_working_memory"

    @property
    def description(self) -> str:
        return (
            "Retrieve the current working memory summary including progress, "
            "findings, pending todos, and any errors from previous iterations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "progress", "findings", "todo", "decisions", "errors"],
                    "description": "Filter memory by category, or 'all' for full summary",
                },
            },
            "required": [],
        }

    async def execute(self, category: str = "all") -> ToolResult:
        try:
            if category == "all":
                return ToolResult(success=True, content=self._memory.to_context_string())

            category_map = {
                "progress": WorkingMemory.CATEGORY_PROGRESS,
                "findings": WorkingMemory.CATEGORY_FINDINGS,
                "todo": WorkingMemory.CATEGORY_TODO,
                "decisions": WorkingMemory.CATEGORY_DECISIONS,
                "errors": WorkingMemory.CATEGORY_ERRORS,
            }

            if category not in category_map:
                return ToolResult(success=False, error=f"Unknown category: {category}")

            entries = self._memory.get_by_category(category_map[category])
            if not entries:
                return ToolResult(success=True, content=f"No {category} entries found")

            lines = [f"## {category.title()} ({len(entries)} entries)"]
            for entry in entries:
                lines.append(f"- [{entry.iteration}] {entry.value}")

            return ToolResult(success=True, content="\n".join(lines))

        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SignalCompletionTool(Tool):
    """发送完成信号.

    当 Agent 确认任务完成时调用此工具。
    输出包含 <promise>TASK COMPLETE</promise> 标签，
    CompletionDetector 会检测此标签并终止 Ralph 循环。
    """

    @property
    def name(self) -> str:
        return "signal_completion"

    @property
    def description(self) -> str:
        return (
            "Signal that the Ralph loop task is complete. "
            "Use this when you have finished the assigned task and verified the results."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was accomplished",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence level (0-1) that the task is truly complete",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": ["summary"],
        }

    @property
    def instructions(self) -> str:
        return (
            "When using signal_completion:\n"
            "- Only call this when you are confident the task is fully complete\n"
            "- Include a summary of what was accomplished\n"
            "- The output will contain a <promise>TASK COMPLETE</promise> tag"
        )

    @property
    def add_instructions_to_prompt(self) -> bool:
        return True

    async def execute(self, summary: str, confidence: float = 1.0) -> ToolResult:
        return ToolResult(
            success=True,
            content=f"Task Summary: {summary}\nConfidence: {confidence}\n<promise>TASK COMPLETE</promise>",
        )
