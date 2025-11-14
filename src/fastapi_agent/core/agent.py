"""Core Agent implementation."""

import time
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi_agent.core.agent_logger import AgentLogger
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.token_manager import TokenManager
from fastapi_agent.schemas.message import Message
from fastapi_agent.tools.base import Tool, ToolResult


class Agent:
    """Agent with tool execution loop."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 120000,  # 120k tokens for claude-3-5-sonnet (200k context)
        enable_summarization: bool = True,
        enable_logging: bool = True,
        log_dir: str | None = None,
    ) -> None:
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        self.workspace_dir = Path(workspace_dir)

        # Initialize Token Manager
        self.token_manager = TokenManager(
            llm_client=llm_client,
            token_limit=token_limit,
            enable_summarization=enable_summarization,
        )

        # Initialize Agent Logger
        self.enable_logging = enable_logging
        if enable_logging:
            self.logger = AgentLogger(log_dir=log_dir)
        else:
            self.logger = None

        # Ensure workspace exists
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Add workspace info to system prompt
        if "Current Workspace" not in system_prompt:
            workspace_info = (
                f"\n\n## Current Workspace\n"
                f"You are currently working in: `{self.workspace_dir.absolute()}`\n"
                f"All relative paths will be resolved relative to this directory."
            )
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt

        # Initialize message history
        self.messages: list[Message] = [
            Message(role="system", content=system_prompt)
        ]

        # Execution logs for API response
        self.execution_logs: list[dict[str, Any]] = []

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    async def run(self) -> tuple[str, list[dict[str, Any]]]:
        """Execute agent loop until task is complete or max steps reached.

        Returns:
            Tuple of (final_response, execution_logs)
        """
        self.execution_logs = []
        step = 0

        # Start new log file for this run
        if self.logger:
            log_file = self.logger.start_new_run()
            print(f"📝 Logging to: {log_file}")

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

            # Log LLM response
            log_entry = {
                "type": "llm_response",
                "thinking": response.thinking,
                "content": response.content,
                "has_tool_calls": bool(response.tool_calls),
                "tool_count": len(response.tool_calls) if response.tool_calls else 0,
            }
            self.execution_logs.append(log_entry)

            if self.logger:
                self.logger.log_response(
                    content=response.content,
                    thinking=response.thinking,
                    tool_calls=response.tool_calls,
                )

            # Add assistant message
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
            )
            self.messages.append(assistant_msg)

            # Check if task is complete (no tool calls)
            if not response.tool_calls:
                self.execution_logs.append({
                    "type": "completion",
                    "message": "Task completed successfully"
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

                # Add tool result message
                tool_msg = Message(
                    role="tool",
                    content=result.content if result.success else f"Error: {result.error}",
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

        # Max steps reached
        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        self.execution_logs.append({
            "type": "max_steps_reached",
            "message": error_msg
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

                # Add tool result message
                tool_msg = Message(
                    role="tool",
                    content=result.content if result.success else f"Error: {result.error}",
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
