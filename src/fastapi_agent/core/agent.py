"""Core Agent implementation."""

import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi_agent.core.agent_logger import AgentLogger
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.token_manager import TokenManager
from fastapi_agent.core.prompt_builder import (
    SystemPromptConfig,
    SystemPromptBuilder,
)
from fastapi_agent.schemas.message import Message
from fastapi_agent.skills.skill_loader import SkillLoader
from fastapi_agent.tools.base import Tool, ToolResult


class Agent:
    """Agent with tool execution loop."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: Optional[str] = None,
        prompt_config: Optional[SystemPromptConfig] = None,
        tools: list[Tool] | None = None,
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 120000,  # 120k tokens for claude-3-5-sonnet (200k context)
        enable_summarization: bool = True,
        enable_logging: bool = True,
        log_dir: str | None = None,
        name: str | None = None,
        skill_loader: Optional[SkillLoader] = None,
        tool_output_limit: int = 10000,  # Maximum characters for tool output
    ) -> None:
        """Initialize Agent.

        Args:
            llm_client: LLM client
            system_prompt: 系统提示字符串(旧方式,向后兼容)
            prompt_config: 系统提示配置(新方式,推荐)
            tools: 工具列表
            max_steps: 最大执行步数
            workspace_dir: 工作空间目录
            token_limit: Token 限制
            enable_summarization: 是否启用自动摘要
            enable_logging: 是否启用日志
            log_dir: 已废弃，日志目录现在由 RUN_LOG_DIR 配置
            name: Agent 名称
            skill_loader: Skill 加载器(用于注入 skills 元数据到系统提示)
            tool_output_limit: 工具输出最大字符数(防止Token爆炸)
        """
        self.llm = llm_client
        self.name = name  # Agent name for team coordination
        self.tools = {tool.name: tool for tool in (tools or [])}
        self.max_steps = max_steps
        self.workspace_dir = Path(workspace_dir)
        self.skill_loader = skill_loader
        self.tool_output_limit = tool_output_limit

        # Initialize Token Manager
        self.token_manager = TokenManager(
            llm_client=llm_client,
            token_limit=token_limit,
            enable_summarization=enable_summarization,
        )

        # Initialize Agent Logger
        self.enable_logging = enable_logging
        if enable_logging:
            self.logger = AgentLogger()
        else:
            self.logger = None

        # Ensure workspace exists
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Build system prompt
        if prompt_config:
            # 新方式: 使用结构化配置
            self.system_prompt = self._build_structured_prompt(prompt_config)
        elif system_prompt:
            # 旧方式: 直接使用字符串(向后兼容)
            if "Current Workspace" not in system_prompt and "workspace_info" not in system_prompt:
                workspace_info = (
                    f"\n\n## Current Workspace\n"
                    f"You are currently working in: `{self.workspace_dir.absolute()}`\n"
                    f"All relative paths will be resolved relative to this directory."
                )
                system_prompt = system_prompt + workspace_info
            self.system_prompt = system_prompt
        else:
            # 默认提示
            self.system_prompt = self._build_default_prompt()

        # Initialize message history
        self.messages: list[Message] = [
            Message(role="system", content=self.system_prompt)
        ]

        # Execution logs for API response
        self.execution_logs: list[dict[str, Any]] = []

    def _collect_tool_instructions(self) -> list[str]:
        """收集需要添加到系统提示的工具说明."""
        instructions = []
        for tool in self.tools.values():
            if tool.add_instructions_to_prompt and tool.instructions:
                instructions.append(tool.instructions)
        return instructions

    def _build_structured_prompt(self, config: SystemPromptConfig) -> str:
        """使用 SystemPromptBuilder 构建结构化系统提示."""
        # 收集工具说明
        tool_instructions = self._collect_tool_instructions()

        # 使用构建器
        builder = SystemPromptBuilder()
        return builder.build(
            config=config,
            workspace_dir=self.workspace_dir,
            skill_loader=self.skill_loader,
            tool_instructions=tool_instructions,
        )

    def _build_default_prompt(self) -> str:
        """构建默认系统提示."""
        config = SystemPromptConfig(
            description="You are a helpful AI assistant.",
            instructions=[
                "Always think step by step",
                "Use available tools when appropriate",
                "Provide clear and accurate responses",
            ],
        )
        return self._build_structured_prompt(config)

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def _truncate_tool_output(self, content: str) -> str:
        """Truncate tool output if it exceeds the limit.

        Args:
            content: Tool output content

        Returns:
            Truncated content with indicator if exceeded limit
        """
        if len(content) <= self.tool_output_limit:
            return content

        truncated = content[:self.tool_output_limit]
        return f"{truncated}\n\n[... output truncated, {len(content) - self.tool_output_limit} more characters ...]"

    async def run(self) -> tuple[str, list[dict[str, Any]]]:
        """Execute agent loop until task is complete or max steps reached.

        Returns:
            Tuple of (final_response, execution_logs)
        """
        self.execution_logs = []
        step = 0
        total_input_tokens = 0
        total_output_tokens = 0

        if self.logger:
            log_file = self.logger.start_new_run()
            print(f"Logging to: {log_file}")

        while step < self.max_steps:
            step += 1

            # Check and maybe summarize message history to prevent context overflow
            current_tokens = self.token_manager.estimate_tokens(self.messages)
            self.messages = await self.token_manager.maybe_summarize_messages(self.messages)

            # Log step and token usage
            self.execution_logs.append({
                "type": "step",
                "step": step,
                "max_steps": self.max_steps,
                "tokens": current_tokens,
                "token_limit": self.token_manager.token_limit,
            })

            if self.logger:
                self.logger.log_step(
                    step=step,
                    max_steps=self.max_steps,
                    token_count=current_tokens,
                    token_limit=self.token_manager.token_limit,
                )

            # Get tool schemas
            tool_schemas = [tool.to_schema() for tool in self.tools.values()]

            # Log LLM request
            if self.logger:
                self.logger.log_request(
                    messages=self.messages,
                    tools=tool_schemas,
                    token_count=current_tokens,
                )

            # Call LLM
            try:
                response = await self.llm.generate(
                    messages=self.messages,
                    tools=tool_schemas
                )
            except Exception as e:
                error_msg = f"LLM call failed: {str(e)}"
                self.execution_logs.append({
                    "type": "error",
                    "message": error_msg
                })
                if self.logger:
                    self.logger.log_completion(
                        final_response=error_msg,
                        total_steps=step,
                        reason="error",
                    )
                return error_msg, self.execution_logs

            if response.usage:
                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens

            log_entry = {
                "type": "llm_response",
                "thinking": response.thinking,
                "content": response.content,
                "has_tool_calls": bool(response.tool_calls),
                "tool_count": len(response.tool_calls) if response.tool_calls else 0,
                "input_tokens": response.usage.input_tokens if response.usage else 0,
                "output_tokens": response.usage.output_tokens if response.usage else 0,
            }
            self.execution_logs.append(log_entry)

            if self.logger:
                self.logger.log_response(
                    content=response.content,
                    thinking=response.thinking,
                    tool_calls=response.tool_calls,
                    input_tokens=response.usage.input_tokens if response.usage else None,
                    output_tokens=response.usage.output_tokens if response.usage else None,
                )

            # Add assistant message
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
            )
            self.messages.append(assistant_msg)

            if not response.tool_calls:
                self.execution_logs.append({
                    "type": "completion",
                    "message": "Task completed successfully",
                    "total_input_tokens": total_input_tokens,
                    "total_output_tokens": total_output_tokens,
                    "total_tokens": total_input_tokens + total_output_tokens,
                })
                if self.logger:
                    self.logger.log_completion(
                        final_response=response.content,
                        total_steps=step,
                        reason="task_completed",
                    )
                return response.content, self.execution_logs

            # Execute tool calls
            for tool_call in response.tool_calls:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                # Log tool call
                self.execution_logs.append({
                    "type": "tool_call",
                    "tool": function_name,
                    "arguments": arguments,
                })

                # Execute tool and measure execution time
                start_time = time.time()
                if function_name not in self.tools:
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"Unknown tool: {function_name}",
                    )
                else:
                    try:
                        tool = self.tools[function_name]
                        result = await tool.execute(**arguments)
                    except Exception as e:
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"Tool execution failed: {str(e)}",
                        )
                execution_time = time.time() - start_time

                # Log tool result
                self.execution_logs.append({
                    "type": "tool_result",
                    "tool": function_name,
                    "success": result.success,
                    "content": result.content if result.success else None,
                    "error": result.error if not result.success else None,
                    "execution_time": execution_time,
                })

                if self.logger:
                    self.logger.log_tool_execution(
                        tool_name=function_name,
                        arguments=arguments,
                        success=result.success,
                        content=result.content if result.success else None,
                        error=result.error if not result.success else None,
                        execution_time=execution_time,
                    )

                # Add tool result message (truncate if too long to prevent token explosion)
                tool_content = result.content if result.success else f"Error: {result.error}"
                if result.success:
                    tool_content = self._truncate_tool_output(tool_content)

                tool_msg = Message(
                    role="tool",
                    content=tool_content,
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        self.execution_logs.append({
            "type": "max_steps_reached",
            "message": error_msg,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
        })
        if self.logger:
            self.logger.log_completion(
                final_response=error_msg,
                total_steps=self.max_steps,
                reason="max_steps_reached",
            )
        return error_msg, self.execution_logs

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()

    async def run_stream(self) -> AsyncIterator[dict[str, Any]]:
        """Execute agent loop with streaming output.

        Yields:
            dict: Stream events containing:
                - type: 'step' | 'thinking' | 'content' | 'tool_call' | 'tool_result' | 'done' | 'error'
                - data: Event-specific data
        """
        step = 0

        # Start new log file for this run
        if self.logger:
            log_file = self.logger.start_new_run()
            yield {
                "type": "log_file",
                "data": {"log_file": str(log_file)},
            }

        while step < self.max_steps:
            step += 1

            # Check and maybe summarize message history
            current_tokens = self.token_manager.estimate_tokens(self.messages)
            self.messages = await self.token_manager.maybe_summarize_messages(self.messages)

            # Yield step info
            yield {
                "type": "step",
                "data": {
                    "step": step,
                    "max_steps": self.max_steps,
                    "tokens": current_tokens,
                    "token_limit": self.token_manager.token_limit,
                },
            }

            if self.logger:
                self.logger.log_step(
                    step=step,
                    max_steps=self.max_steps,
                    token_count=current_tokens,
                    token_limit=self.token_manager.token_limit,
                )

            # Get tool schemas
            tool_schemas = [tool.to_schema() for tool in self.tools.values()]

            # Stream LLM response
            thinking_buffer = ""
            content_buffer = ""
            tool_calls_buffer = []

            try:
                async for event in self.llm.generate_stream(
                    messages=self.messages,
                    tools=tool_schemas
                ):
                    event_type = event.get("type")

                    if event_type == "thinking_delta":
                        delta = event.get("delta", "")
                        thinking_buffer += delta
                        yield {
                            "type": "thinking",
                            "data": {"delta": delta},
                        }

                    elif event_type == "content_delta":
                        delta = event.get("delta", "")
                        content_buffer += delta
                        yield {
                            "type": "content",
                            "data": {"delta": delta},
                        }

                    elif event_type == "tool_use":
                        tool_call = event.get("tool_call")
                        if tool_call:
                            tool_calls_buffer.append(tool_call)
                            yield {
                                "type": "tool_call",
                                "data": {
                                    "tool": tool_call.function.name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }

                    elif event_type == "done":
                        response = event.get("response")
                        break

            except Exception as e:
                error_msg = f"LLM call failed: {str(e)}"
                yield {
                    "type": "error",
                    "data": {"message": error_msg},
                }
                if self.logger:
                    self.logger.log_completion(
                        final_response=error_msg,
                        total_steps=step,
                        reason="error",
                    )
                return

            # Add assistant message to history
            assistant_msg = Message(
                role="assistant",
                content=content_buffer,
                thinking=thinking_buffer if thinking_buffer else None,
                tool_calls=tool_calls_buffer if tool_calls_buffer else None,
            )
            self.messages.append(assistant_msg)

            # If no tool calls, task is complete
            if not tool_calls_buffer:
                if self.logger:
                    self.logger.log_completion(
                        final_response=content_buffer,
                        total_steps=step,
                        reason="completed",
                    )
                yield {
                    "type": "done",
                    "data": {
                        "message": content_buffer,
                        "steps": step,
                        "reason": "completed",
                    },
                }
                return

            # Execute tools
            for tool_call in tool_calls_buffer:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                # Execute tool and measure time
                start_time = time.time()
                if function_name not in self.tools:
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"Unknown tool: {function_name}",
                    )
                else:
                    try:
                        tool = self.tools[function_name]
                        result = await tool.execute(**arguments)
                    except Exception as e:
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"Tool execution failed: {str(e)}",
                        )
                execution_time = time.time() - start_time

                # Yield tool result
                yield {
                    "type": "tool_result",
                    "data": {
                        "tool": function_name,
                        "success": result.success,
                        "content": result.content if result.success else None,
                        "error": result.error if not result.success else None,
                        "execution_time": execution_time,
                    },
                }

                if self.logger:
                    self.logger.log_tool_execution(
                        tool_name=function_name,
                        arguments=arguments,
                        success=result.success,
                        content=result.content if result.success else None,
                        error=result.error if not result.success else None,
                        execution_time=execution_time,
                    )

                # Add tool result message (truncate if too long to prevent token explosion)
                tool_content = result.content if result.success else f"Error: {result.error}"
                if result.success:
                    tool_content = self._truncate_tool_output(tool_content)

                tool_msg = Message(
                    role="tool",
                    content=tool_content,
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

        # Max steps reached
        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        if self.logger:
            self.logger.log_completion(
                final_response=error_msg,
                total_steps=self.max_steps,
                reason="max_steps_reached",
            )
        yield {
            "type": "error",
            "data": {
                "message": error_msg,
                "reason": "max_steps_reached",
            },
        }
