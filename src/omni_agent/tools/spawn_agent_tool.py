"""SpawnAgentTool - 允许 Agent 动态创建子 Agent 进行任务委派。"""

from typing import Any, Optional

from omni_agent.tools.base import Tool, ToolResult


class SpawnAgentTool(Tool):
    """用于生成子 Agent 自主处理特定任务的工具。

    此工具允许父 Agent 根据任务需求动态创建专门的子 Agent。
    子 Agent 可以有不同的角色、工具集和配置。

    类似于 Claude Code 的 Task 工具功能。
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        parent_tools: dict[str, Tool],
        workspace_dir: str,
        current_depth: int = 0,
        max_depth: int = 3,
        parent_logger: Optional["AgentLogger"] = None,
        default_max_steps: int = 15,
        default_token_limit: int = 50000,
    ):
        """初始化 SpawnAgentTool。

        Args:
            llm_client: 用于子 Agent 通信的 LLM 客户端
            parent_tools: 父 Agent 可用的工具字典
            workspace_dir: 工作目录路径
            current_depth: 当前嵌套深度（根 Agent 为 0）
            max_depth: 允许的最大嵌套深度
            parent_logger: 用于事件跟踪的可选父 Agent 日志记录器
            default_max_steps: 子 Agent 的默认最大步骤数
            default_token_limit: 子 Agent 的默认 token 限制
        """
        self._llm_client = llm_client
        self._parent_tools = parent_tools
        self._workspace_dir = workspace_dir
        self._current_depth = current_depth
        self._max_depth = max_depth
        self._parent_logger = parent_logger
        self._default_max_steps = default_max_steps
        self._default_token_limit = default_token_limit

    @property
    def name(self) -> str:
        return "spawn_agent"

    @property
    def description(self) -> str:
        return f"""Spawn a specialized sub-agents to handle a specific task autonomously.

Use this when:
- A task requires specialized expertise or a different approach
- Breaking down a complex task into independent subtasks
- You need focused work on a specific problem without cluttering your main context
- Parallel exploration of different solutions

The sub-agents will execute the task and return its final result to you.
You remain in control and can use the result to continue your work.

Current depth: {self._current_depth}/{self._max_depth}"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Clear, specific description of what the sub-agents should accomplish",
                },
                "role": {
                    "type": "string",
                    "description": "Specialized role for the sub-agents (e.g., 'security auditor', 'test writer', 'documentation expert')",
                },
                "context": {
                    "type": "string",
                    "description": "Relevant background information or context from your current work",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific tools to enable. Use tool names like 'read_file', 'write_file', 'edit_file', 'bash'. If not specified, inherits parent tools (except spawn_agent at max depth).",
                },
                "max_steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "description": f"Maximum steps for sub-agents execution (default: {self._default_max_steps})",
                },
            },
            "required": ["task"],
        }

    @property
    def instructions(self) -> str:
        return """## Sub-Agent (spawn_agent) Usage Guidelines

When using spawn_agent to delegate tasks:

1. **Be specific**: Provide clear, focused tasks with concrete success criteria
2. **Provide context**: Share relevant information the sub-agents needs to understand the task
3. **Choose appropriate tools**: Only enable tools the sub-agents actually needs
4. **Set reasonable limits**: Use smaller max_steps for simple tasks (5-10), larger for complex ones (15-25)

### Good use cases:
- "Analyze the security of the authentication module in /src/auth" (role: security auditor)
- "Write unit tests for the calculate_total function" (role: test writer)
- "Research best practices for implementing caching in FastAPI" (role: researcher)
- "Review this code for performance issues" (role: performance analyst)

### Poor use cases:
- Vague tasks like "help me with this project"
- Tasks that require your current conversation context (sub-agents start fresh)
- Simple tasks you could do directly with one or two tool calls

### Example:
```
spawn_agent(
    task="Analyze all Python files in /src for potential SQL injection vulnerabilities",
    role="security auditor",
    context="This is a FastAPI application using SQLAlchemy. Focus on user input handling.",
    tools=["read_file", "bash"],
    max_steps=20
)
```"""

    @property
    def add_instructions_to_prompt(self) -> bool:
        return True

    async def execute(
        self,
        task: str,
        role: str | None = None,
        context: str | None = None,
        tools: list[str] | None = None,
        max_steps: int | None = None,
        **kwargs,
    ) -> ToolResult:
        """使用给定配置执行子 Agent。

        Args:
            task: 子 Agent 要完成的任务
            role: 子 Agent 的可选专门角色
            context: 来自父 Agent 的可选上下文信息
            tools: 要启用的可选工具名称列表
            max_steps: 可选的最大步骤限制

        Returns:
            包含子 Agent 最终响应的 ToolResult
        """
        # Import here to avoid circular imports
        from omni_agent.core.agent import Agent

        # Check depth limit
        if self._current_depth >= self._max_depth:
            return ToolResult(
                success=False,
                error=f"Maximum agents nesting depth ({self._max_depth}) reached. Cannot spawn more sub-agents. Consider completing the task with available tools instead.",
            )

        try:
            # Build sub-agents tools
            sub_tools = self._build_sub_agent_tools(tools)

            # Build system prompt for sub-agents
            system_prompt = self._build_sub_agent_prompt(role, context)

            # Determine max_steps
            effective_max_steps = min(max_steps or self._default_max_steps, 30)

            # Create sub-agents
            sub_agent = Agent(
                llm_client=self._llm_client,
                system_prompt=system_prompt,
                tools=sub_tools,
                max_steps=effective_max_steps,
                workspace_dir=self._workspace_dir,
                token_limit=self._default_token_limit,
                enable_summarization=True,
                enable_logging=True,
                name=f"sub_agent_d{self._current_depth + 1}_{role or 'general'}",
            )

            # Log sub-agents spawn event
            if self._parent_logger:
                self._parent_logger.log_event(
                    "SUB_AGENT_SPAWN",
                    {
                        "task": task[:200],  # Truncate for logging
                        "role": role,
                        "depth": self._current_depth + 1,
                        "max_depth": self._max_depth,
                        "tools": [t.name for t in sub_tools],
                        "max_steps": effective_max_steps,
                    },
                )

            # Run sub-agents
            sub_agent.add_user_message(task)
            result, logs = await sub_agent.run()

            # Calculate execution stats
            steps_used = len([log for log in logs if log.get("type") == "step"])
            tool_calls = len([log for log in logs if log.get("type") == "tool_call"])
            errors = [
                log for log in logs if log.get("type") == "error" or not log.get("success", True)
            ]

            # Log completion event
            if self._parent_logger:
                self._parent_logger.log_event(
                    "SUB_AGENT_COMPLETE",
                    {
                        "task": task[:200],
                        "role": role,
                        "depth": self._current_depth + 1,
                        "steps_used": steps_used,
                        "tool_calls": tool_calls,
                        "success": len(errors) == 0,
                    },
                )

            # Format result for parent agents
            formatted_result = self._format_result(
                task=task,
                role=role,
                result=result,
                steps_used=steps_used,
                tool_calls=tool_calls,
                max_steps=effective_max_steps,
            )

            return ToolResult(success=True, content=formatted_result)

        except Exception as e:
            error_msg = f"Sub-agents execution failed: {str(e)}"

            if self._parent_logger:
                self._parent_logger.log_event(
                    "SUB_AGENT_ERROR",
                    {
                        "task": task[:200],
                        "role": role,
                        "error": str(e),
                    },
                )

            return ToolResult(success=False, error=error_msg)

    def _build_sub_agent_tools(self, tool_names: list[str] | None) -> list[Tool]:
        """为子 Agent 构建工具列表。

        Args:
            tool_names: 要包含的可选特定工具名称列表

        Returns:
            子 Agent 的 Tool 实例列表
        """
        if tool_names is not None:
            # Filter to requested tools only
            tools = []
            for name in tool_names:
                if name in self._parent_tools:
                    tool = self._parent_tools[name]
                    # Don't include spawn_agent if at max depth - 1
                    if name == "spawn_agent" and self._current_depth + 1 >= self._max_depth:
                        continue
                    tools.append(tool)
            return tools

        # Inherit all parent tools
        tools = []
        for name, tool in self._parent_tools.items():
            if name == "spawn_agent":
                # Create new SpawnAgentTool with incremented depth
                if self._current_depth + 1 < self._max_depth:
                    new_spawn_tool = SpawnAgentTool(
                        llm_client=self._llm_client,
                        parent_tools=self._parent_tools,
                        workspace_dir=self._workspace_dir,
                        current_depth=self._current_depth + 1,
                        max_depth=self._max_depth,
                        parent_logger=self._parent_logger,
                        default_max_steps=self._default_max_steps,
                        default_token_limit=self._default_token_limit,
                    )
                    tools.append(new_spawn_tool)
                # else: skip spawn_agent at max depth
            else:
                tools.append(tool)

        return tools

    def _build_sub_agent_prompt(self, role: str | None, context: str | None) -> str:
        """为子 Agent 构建系统提示。

        Args:
            role: 可选的专门角色
            context: 来自父 Agent 的可选上下文

        Returns:
            系统提示字符串
        """
        parts = []

        # Role definition
        if role:
            parts.append(f"You are a specialized AI assistant acting as a **{role}**.")
        else:
            parts.append("You are an AI assistant executing a delegated task.")

        # Core instructions
        parts.append("""
Your task has been delegated from a parent agents. Focus on completing it efficiently and thoroughly.

## Guidelines
- Stay focused on the assigned task - do not deviate
- Be thorough but concise in your work
- Use available tools when necessary
- Report your findings and results clearly at the end
- If you encounter blockers, explain them clearly

## Important
- You have independent context - you don't see the parent's conversation
- Complete your task fully before finishing
- Provide actionable results the parent can use
""")

        # Context from parent
        if context:
            parts.append(f"""
## Context from Parent Agent
{context}
""")

        # Workspace info
        parts.append(f"""
## Workspace
You are working in: `{self._workspace_dir}`
All relative paths are resolved from this directory.
""")

        # Depth info
        if self._current_depth + 1 < self._max_depth:
            parts.append(f"""
## Sub-Agent Capability
You can spawn sub-agents if needed (depth {self._current_depth + 1}/{self._max_depth}).
Use this sparingly and only for truly independent subtasks.
""")

        return "\n".join(parts)

    def _format_result(
        self,
        task: str,
        role: str | None,
        result: str,
        steps_used: int,
        tool_calls: int,
        max_steps: int,
    ) -> str:
        """为父 Agent 格式化子 Agent 结果。

        Args:
            task: 原始任务
            role: 子 Agent 角色
            result: 子 Agent 的最终响应
            steps_used: 执行的步骤数
            tool_calls: 进行的工具调用数
            max_steps: 允许的最大步骤数

        Returns:
            格式化的结果字符串
        """
        header = "## Sub-Agent Execution Result"
        if role:
            header += f" ({role})"

        # Truncate task if too long
        task_display = task[:300] + "..." if len(task) > 300 else task

        return f"""{header}

**Task:** {task_display}
**Execution:** {steps_used}/{max_steps} steps, {tool_calls} tool calls
**Depth:** {self._current_depth + 1}/{self._max_depth}

---

{result}
"""
