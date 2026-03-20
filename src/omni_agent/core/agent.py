"""核心 Agent 实现，采用统一架构.

本模块实现了 Agent 的完整生命周期管理，包括：
- 事件驱动的执行流程（EventEmitter + EventType）
- 状态管理（AgentState + AgentStatus）
- 执行循环（AgentLoop）
- Hook 扩展机制（HookManager + AgentHook）
- Checkpoint 断点续传
- 运行时取消机制

核心类:
    - Agent: 用户接口，封装所有配置和执行逻辑
    - AgentLoop: 执行引擎，负责 LLM 调用和工具执行
    - AgentState: 运行时状态，包括消息历史、token 统计等
    - EventEmitter: 事件分发器，支持 STEP_START/LLM_RESPONSE/TOOL_START 等事件

执行流程:
    1. Agent.run() 调用 AgentLoop.run()
    2. AgentLoop 循环执行 _execute_step()
    3. 每步: LLM 生成 -> 解析工具调用 -> 执行工具 -> 添加结果到消息
    4. 直到: 无工具调用（完成）/ max_steps / 等待用户输入 / 错误 / 取消
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

from omni_agent.core.agent_base import AgentBase, AgentStatus
from omni_agent.core.checkpoint import Checkpoint, CheckpointConfig
from omni_agent.core.hooks import AgentHook, HookContext
from omni_agent.core.langfuse_tracing import LangfuseTracer, get_tracer
from omni_agent.core.llm_client import LLMClient
from omni_agent.core.memory_hook import MemoryHook, create_memory_hook
from omni_agent.core.planner import Plan, PlanStatus
from omni_agent.core.prompt_builder import SystemPromptBuilder, SystemPromptConfig
from omni_agent.core.ralph import RalphConfig, RalphLoop
from omni_agent.core.token_manager import TokenManager
from omni_agent.core.tool_executor import ToolExecutor
from omni_agent.schemas.message import Message, ToolCall, UserInputField, UserInputRequest
from omni_agent.skills.skill_loader import SkillLoader
from omni_agent.tools.base import Tool
from omni_agent.tools.user_input_tool import (
    GetUserInputTool,
    is_user_input_tool_call,
    parse_user_input_fields,
)


class EventType(Enum):
    """Agent 事件类型.

    定义 Agent 执行过程中可能触发的所有事件类型，
    用于事件驱动的执行流程和日志记录。
    """

    STEP_START = "step_start"
    STEP_END = "step_end"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    USER_INPUT_REQUIRED = "user_input_required"
    COMPLETION = "completion"
    CANCELLED = "cancelled"
    ERROR = "error"
    TOKEN_SUMMARY = "token_summary"
    RALPH_ITERATION_START = "ralph_iteration_start"
    RALPH_ITERATION_END = "ralph_iteration_end"
    RALPH_COMPLETION = "ralph_completion"
    PLAN_CREATED = "plan_created"
    PLAN_STEP_COMPLETED = "plan_step_completed"


@dataclass
class AgentEvent:
    """Agent 事件.

    封装事件类型、数据、步骤和时间戳，用于事件分发。
    """

    type: EventType
    data: dict[str, Any]
    step: int = 0
    timestamp: float = field(default_factory=time.time)


EventHandler = Callable[[AgentEvent], Awaitable[None]]


class EventEmitter:
    """事件分发器.

    支持按事件类型注册处理器，也支持全局处理器接收所有事件。
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def on_all(self, handler: EventHandler) -> None:
        self._global_handlers.append(handler)

    def off_all(self, handler: EventHandler) -> None:
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    async def emit(self, event: AgentEvent) -> None:
        for handler in self._global_handlers:
            await handler(event)
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            await handler(event)

    def clear(self) -> None:
        self._handlers.clear()
        self._global_handlers.clear()


@dataclass
class AgentState:
    """Agent 运行时状态.

    管理 Agent 的完整运行时状态，包括执行状态、消息历史、
    token 统计、用户输入等待和断点续传支持。
    """

    status: AgentStatus = AgentStatus.IDLE
    current_step: int = 0
    max_steps: int = 50
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    messages: list[Message] = field(default_factory=list)
    pending_user_input: UserInputRequest | None = None
    paused_tool_call_id: str | None = None
    error_message: str | None = None
    last_checkpoint_id: str | None = None
    thread_id: str | None = None

    def reset_for_run(self, preserve_messages: bool = False) -> None:
        self.status = AgentStatus.RUNNING
        self.current_step = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.pending_user_input = None
        self.paused_tool_call_id = None
        self.error_message = None
        if not preserve_messages:
            self.last_checkpoint_id = None

    def increment_step(self) -> int:
        self.current_step += 1
        return self.current_step

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def mark_waiting_input(self, request: UserInputRequest, tool_call_id: str) -> None:
        self.status = AgentStatus.WAITING_INPUT
        self.pending_user_input = request
        self.paused_tool_call_id = tool_call_id

    def mark_completed(self) -> None:
        self.status = AgentStatus.COMPLETED
        self.pending_user_input = None
        self.paused_tool_call_id = None

    def mark_error(self, message: str) -> None:
        self.status = AgentStatus.ERROR
        self.error_message = message

    def mark_cancelled(self, message: str = "Task cancelled by user") -> None:
        self.status = AgentStatus.CANCELLED
        self.error_message = message

    def resume_from_input(self) -> None:
        if self.status == AgentStatus.WAITING_INPUT:
            self.status = AgentStatus.RUNNING
            self.pending_user_input = None
            self.paused_tool_call_id = None

    def resume_from_checkpoint(self) -> None:
        if self.status in (AgentStatus.IDLE, AgentStatus.COMPLETED, AgentStatus.ERROR):
            self.status = AgentStatus.RUNNING
            self.error_message = None

    @property
    def is_running(self) -> bool:
        return self.status == AgentStatus.RUNNING

    @property
    def is_waiting_input(self) -> bool:
        return self.status == AgentStatus.WAITING_INPUT

    @property
    def is_completed(self) -> bool:
        return self.status == AgentStatus.COMPLETED

    @property
    def is_error(self) -> bool:
        return self.status == AgentStatus.ERROR

    @property
    def is_cancelled(self) -> bool:
        return self.status == AgentStatus.CANCELLED

    @property
    def can_continue(self) -> bool:
        return self.status == AgentStatus.RUNNING and self.current_step < self.max_steps

    def to_checkpoint_data(self) -> dict:
        return {
            "step": self.current_step,
            "status": self.status.value,
            "messages": self.messages,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "pending_user_input": self.pending_user_input,
            "paused_tool_call_id": self.paused_tool_call_id,
            "error_message": self.error_message,
        }

    @classmethod
    def from_checkpoint(cls, checkpoint: "Checkpoint", max_steps: int = 50) -> "AgentState":
        return cls(
            status=AgentStatus(checkpoint.status),
            current_step=checkpoint.step,
            max_steps=max_steps,
            total_input_tokens=checkpoint.token_usage.get("input", 0),
            total_output_tokens=checkpoint.token_usage.get("output", 0),
            messages=checkpoint.get_messages(),
            last_checkpoint_id=checkpoint.id,
            thread_id=checkpoint.thread_id,
        )


class HookManager:
    """Hook 管理器.

    管理多个 AgentHook 实例，按优先级排序执行，
    支持 before_run、on_step、after_run 三个触发点。
    """

    def __init__(self) -> None:
        self._hooks: list[AgentHook] = []

    def add(self, hook: AgentHook) -> None:
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority)

    def remove(self, hook: AgentHook) -> None:
        if hook in self._hooks:
            self._hooks.remove(hook)

    def clear(self) -> None:
        self._hooks.clear()

    async def trigger_before_run(self, ctx: HookContext) -> None:
        for hook in self._hooks:
            await hook.before_run(ctx)

    async def trigger_on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        for hook in self._hooks:
            await hook.on_step(ctx, step_data)

    async def trigger_after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        for hook in self._hooks:
            await hook.after_run(ctx, result, success)

    async def trigger_on_feedback(
        self, ctx: HookContext, feedback_type: str, data: dict[str, Any]
    ) -> None:
        for hook in self._hooks:
            await hook.on_feedback(ctx, feedback_type, data)


ToolResultCallback = Callable[[str, str, dict[str, Any], str], Coroutine[Any, Any, None]]


@dataclass
class LoopConfig:
    """执行循环配置.

    Attributes:
        max_steps: 最大执行步数
        parallel_tools: 是否并行执行工具
        checkpoint: 断点续传配置
        on_tool_result: 工具执行后的回调 (tool_call_id, tool_name, arguments, content)
        cancel_event: 取消事件，设置后将中止执行
    """

    max_steps: int = 50
    parallel_tools: bool = False
    checkpoint: CheckpointConfig | None = None
    on_tool_result: ToolResultCallback | None = None
    cancel_event: asyncio.Event | None = None


@dataclass
class StepResult:
    """单步执行结果.

    Attributes:
        completed: 任务是否完成
        waiting_input: 是否等待用户输入
        cancelled: 是否被取消
        content: 响应内容
        error: 错误信息（如有）
    """

    completed: bool = False
    waiting_input: bool = False
    cancelled: bool = False
    content: str = ""
    error: str | None = None


class AgentLoop:
    """Agent 执行引擎.

    核心执行循环，负责协调 LLM 调用、工具执行和状态管理。
    支持同步/流式执行、断点续传和用户输入等待。

    执行流程:
        1. reset_for_run() 重置状态
        2. 循环 _execute_step() 直到完成/max_steps/等待输入
        3. 每步: LLM 生成 -> 解析工具 -> 执行工具 -> 添加结果
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_executor: ToolExecutor,
        token_manager: TokenManager,
        event_emitter: EventEmitter,
        config: LoopConfig | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._llm = llm_client
        self._tool_executor = tool_executor
        self._token_manager = token_manager
        self._events = event_emitter
        self._config = config or LoopConfig()
        self._tool_schemas: list[dict[str, Any]] | None = None
        self._agent_id = agent_id or str(uuid4())
        self._hooks = HookManager()

    @property
    def checkpoint_enabled(self) -> bool:
        return (
            self._config.checkpoint is not None
            and self._config.checkpoint.enabled
            and self._config.checkpoint.storage is not None
        )

    async def _save_checkpoint(
        self,
        state: AgentState,
        trigger: str,
        pending_tool_calls: list[ToolCall] | None = None,
    ) -> str | None:
        if not self.checkpoint_enabled:
            return None

        config = self._config.checkpoint
        assert config is not None
        storage = config.get_storage()

        checkpoint = Checkpoint.create(
            agent_id=self._agent_id,
            thread_id=state.thread_id or str(uuid4()),
            step=state.current_step,
            status=state.status.value,
            messages=state.messages,
            pending_tool_calls=pending_tool_calls,
            input_tokens=state.total_input_tokens,
            output_tokens=state.total_output_tokens,
            metadata={"trigger": trigger},
            parent_id=state.last_checkpoint_id,
        )

        await storage.save(checkpoint)
        state.last_checkpoint_id = checkpoint.id

        if config.max_checkpoints_per_thread > 0:
            existing = await storage.list_checkpoints(
                checkpoint.thread_id,
                limit=config.max_checkpoints_per_thread + 10,
            )
            if len(existing) > config.max_checkpoints_per_thread:
                for old_cp in existing[config.max_checkpoints_per_thread :]:
                    await storage.delete(old_cp.id)

        return checkpoint.id

    def set_tools(self, tools: dict[str, Tool]) -> None:
        self._tool_executor.set_tools(tools)
        self._tool_schemas = [tool.to_schema() for tool in tools.values()]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        if self._tool_schemas is None:
            return []
        return self._tool_schemas

    @property
    def hooks(self) -> HookManager:
        return self._hooks

    def _is_cancelled(self) -> bool:
        """检查是否已被取消。"""
        if self._config.cancel_event is None:
            return False
        return self._config.cancel_event.is_set()

    def _cleanup_incomplete_messages(self, state: AgentState) -> int:
        """清理不完整的消息，保证消息一致性。

        取消时可能存在不完整的 assistant 消息（有 tool_calls 但没有对应的 tool 结果），
        此方法会移除这些不完整的消息。

        Returns:
            移除的消息数量
        """
        if not state.messages:
            return 0

        last_assistant_idx = -1
        for i in range(len(state.messages) - 1, -1, -1):
            if state.messages[i].role == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx == -1:
            return 0

        last_msg = state.messages[last_assistant_idx]
        if last_msg.tool_calls:
            expected_tool_results = {tc.id for tc in last_msg.tool_calls}
            actual_tool_results = set()
            for msg in state.messages[last_assistant_idx + 1 :]:
                if msg.role == "tool" and msg.tool_call_id:
                    actual_tool_results.add(msg.tool_call_id)

            if expected_tool_results != actual_tool_results:
                removed_count = len(state.messages) - last_assistant_idx
                state.messages = state.messages[:last_assistant_idx]
                return removed_count

        return 0

    def set_cancel_event(self, event: asyncio.Event) -> None:
        """设置取消事件。"""
        self._config.cancel_event = event

    async def run(self, state: AgentState, metadata: dict[str, Any] | None = None) -> str:
        state.reset_for_run()
        state.max_steps = self._config.max_steps

        ctx = HookContext(state=state, step=0)
        await self._hooks.trigger_before_run(ctx)

        while state.current_step < self._config.max_steps:
            if self._is_cancelled():
                self._cleanup_incomplete_messages(state)
                cancel_msg = "Task cancelled by user"
                state.mark_cancelled(cancel_msg)
                await self._events.emit(
                    AgentEvent(
                        type=EventType.CANCELLED,
                        step=state.current_step,
                        data={"message": cancel_msg},
                    )
                )
                await self._hooks.trigger_after_run(ctx, cancel_msg, False)
                return cancel_msg

            state.increment_step()
            ctx.step = state.current_step

            result = await self._execute_step(state, metadata)

            if result.cancelled:
                self._cleanup_incomplete_messages(state)
                cancel_msg = "Task cancelled by user"
                state.mark_cancelled(cancel_msg)
                await self._events.emit(
                    AgentEvent(
                        type=EventType.CANCELLED,
                        step=state.current_step,
                        data={"message": cancel_msg},
                    )
                )
                await self._hooks.trigger_after_run(ctx, cancel_msg, False)
                return cancel_msg

            step_data = {
                "completed": result.completed,
                "content": result.content,
                "error": result.error,
            }
            await self._hooks.trigger_on_step(ctx, step_data)

            if result.completed:
                state.mark_completed()
                await self._events.emit(
                    AgentEvent(
                        type=EventType.COMPLETION,
                        step=state.current_step,
                        data={
                            "message": result.content,
                            "total_steps": state.current_step,
                            "total_input_tokens": state.total_input_tokens,
                            "total_output_tokens": state.total_output_tokens,
                        },
                    )
                )
                await self._hooks.trigger_after_run(ctx, result.content, True)
                return result.content

            if result.waiting_input:
                await self._hooks.trigger_after_run(ctx, "Waiting for user input", True)
                return "Waiting for user input"

            if result.error:
                state.mark_error(result.error)
                await self._events.emit(
                    AgentEvent(
                        type=EventType.ERROR,
                        step=state.current_step,
                        data={"message": result.error},
                    )
                )
                await self._hooks.trigger_after_run(ctx, result.error, False)
                return result.error

        error_msg = f"Task couldn't be completed after {self._config.max_steps} steps."
        state.mark_error(error_msg)
        await self._events.emit(
            AgentEvent(
                type=EventType.ERROR,
                step=state.current_step,
                data={"message": error_msg, "reason": "max_steps_reached"},
            )
        )
        await self._hooks.trigger_after_run(ctx, error_msg, False)
        return error_msg

    async def run_stream(
        self,
        state: AgentState,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        state.reset_for_run()
        state.max_steps = self._config.max_steps

        ctx = HookContext(state=state, step=0)
        await self._hooks.trigger_before_run(ctx)

        while state.current_step < self._config.max_steps:
            if self._is_cancelled():
                self._cleanup_incomplete_messages(state)
                cancel_msg = "Task cancelled by user"
                state.mark_cancelled(cancel_msg)
                await self._hooks.trigger_after_run(ctx, cancel_msg, False)
                yield {"type": "cancelled", "data": {"message": cancel_msg}}
                return

            state.increment_step()
            ctx.step = state.current_step

            async for event in self._execute_step_stream(state, metadata):
                yield event

                if event["type"] == "cancelled":
                    self._cleanup_incomplete_messages(state)
                    state.mark_cancelled(event["data"].get("message", "Task cancelled"))
                    await self._hooks.trigger_after_run(
                        ctx, event["data"].get("message", ""), False
                    )
                    return

                if event["type"] == "done":
                    state.mark_completed()
                    await self._hooks.trigger_after_run(ctx, event["data"].get("message", ""), True)
                    return

                if event["type"] == "user_input_required":
                    await self._hooks.trigger_after_run(ctx, "Waiting for user input", True)
                    return

                if event["type"] == "error":
                    state.mark_error(event["data"].get("message", "Unknown error"))
                    await self._hooks.trigger_after_run(
                        ctx, event["data"].get("message", ""), False
                    )
                    return

        error_msg = f"Task couldn't be completed after {self._config.max_steps} steps."
        await self._hooks.trigger_after_run(ctx, error_msg, False)
        yield {
            "type": "error",
            "data": {"message": error_msg, "reason": "max_steps_reached"},
        }

    async def _execute_step(
        self,
        state: AgentState,
        metadata: dict[str, Any] | None,
    ) -> StepResult:
        current_tokens = self._token_manager.estimate_tokens(state.messages)
        state.messages = await self._token_manager.maybe_summarize_messages(state.messages)

        await self._events.emit(
            AgentEvent(
                type=EventType.STEP_START,
                step=state.current_step,
                data={
                    "tokens": current_tokens,
                    "token_limit": self._token_manager.token_limit,
                    "max_steps": self._config.max_steps,
                },
            )
        )

        try:
            response = await self._llm.generate(
                messages=state.messages,
                tools=self._tool_schemas,
                metadata=metadata,
            )
        except Exception as e:
            return StepResult(error=f"LLM call failed: {str(e)}")

        if response.usage:
            state.add_tokens(response.usage.input_tokens, response.usage.output_tokens)

        await self._events.emit(
            AgentEvent(
                type=EventType.LLM_RESPONSE,
                step=state.current_step,
                data={
                    "content": response.content,
                    "thinking": response.thinking,
                    "has_tool_calls": bool(response.tool_calls),
                    "tool_count": len(response.tool_calls) if response.tool_calls else 0,
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
            )
        )

        assistant_msg = Message(
            role="assistant",
            content=response.content,
            thinking=response.thinking,
            tool_calls=response.tool_calls,
        )
        state.messages.append(assistant_msg)

        if not response.tool_calls:
            return StepResult(completed=True, content=response.content)

        for tool_call in response.tool_calls:
            if is_user_input_tool_call(tool_call.function.name):
                input_fields = parse_user_input_fields(tool_call.function.arguments)
                request = UserInputRequest(
                    tool_call_id=tool_call.id,
                    fields=[
                        UserInputField(
                            field_name=f.field_name,
                            field_type=f.field_type,
                            field_description=f.field_description,
                        )
                        for f in input_fields
                    ],
                    context=tool_call.function.arguments.get("context"),
                )
                state.mark_waiting_input(request, tool_call.id)

                await self._events.emit(
                    AgentEvent(
                        type=EventType.USER_INPUT_REQUIRED,
                        step=state.current_step,
                        data={
                            "tool_call_id": tool_call.id,
                            "fields": [f.model_dump() for f in input_fields],
                            "context": tool_call.function.arguments.get("context"),
                        },
                    )
                )

                ckpt_config = self._config.checkpoint
                if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_user_input:
                    await self._save_checkpoint(
                        state,
                        trigger="user_input_wait",
                        pending_tool_calls=[tool_call],
                    )

                return StepResult(waiting_input=True)

        if self._is_cancelled():
            return StepResult(cancelled=True)

        tool_calls_data = [
            (tc.id, tc.function.name, tc.function.arguments) for tc in response.tool_calls
        ]

        for call_id, name, args in tool_calls_data:
            await self._events.emit(
                AgentEvent(
                    type=EventType.TOOL_START,
                    step=state.current_step,
                    data={"tool": name, "arguments": args, "tool_call_id": call_id},
                )
            )

        results = await self._tool_executor.execute_batch(tool_calls_data)

        for exec_result in results:
            if self._is_cancelled():
                return StepResult(cancelled=True)
            await self._events.emit(
                AgentEvent(
                    type=EventType.TOOL_END,
                    step=state.current_step,
                    data={
                        "tool": exec_result.tool_name,
                        "tool_call_id": exec_result.tool_call_id,
                        "success": exec_result.result.success,
                        "content": exec_result.result.content
                        if exec_result.result.success
                        else None,
                        "error": exec_result.result.error
                        if not exec_result.result.success
                        else None,
                        "execution_time": exec_result.execution_time,
                    },
                )
            )

            tool_content = (
                exec_result.result.content
                if exec_result.result.success
                else f"Error: {exec_result.result.error}"
            )
            state.messages.append(
                Message(
                    role="tool",
                    content=tool_content,
                    tool_call_id=exec_result.tool_call_id,
                    name=exec_result.tool_name,
                )
            )

            if self._config.on_tool_result:
                tool_args = tool_calls_data[
                    [r.tool_call_id for r in results].index(exec_result.tool_call_id)
                ][2]
                await self._config.on_tool_result(
                    exec_result.tool_call_id,
                    exec_result.tool_name,
                    tool_args,
                    tool_content,
                )

        await self._events.emit(
            AgentEvent(
                type=EventType.STEP_END,
                step=state.current_step,
                data={"tools_executed": len(results)},
            )
        )

        ckpt_config = self._config.checkpoint
        if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_tool_execution:
            await self._save_checkpoint(state, trigger="tool_execution")

        return StepResult()

    async def _execute_step_stream(
        self,
        state: AgentState,
        metadata: dict[str, Any] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        current_tokens = self._token_manager.estimate_tokens(state.messages)
        state.messages = await self._token_manager.maybe_summarize_messages(state.messages)

        yield {
            "type": "step",
            "data": {
                "step": state.current_step,
                "max_steps": self._config.max_steps,
                "tokens": current_tokens,
                "token_limit": self._token_manager.token_limit,
            },
        }

        thinking_buffer = ""
        content_buffer = ""
        tool_calls_buffer = []

        try:
            async for event in self._llm.generate_stream(
                messages=state.messages,
                tools=self._tool_schemas,
                metadata=metadata,
            ):
                event_type = event.get("type")

                if event_type == "thinking_delta":
                    delta = event.get("delta", "")
                    thinking_buffer += delta
                    yield {"type": "thinking", "data": {"delta": delta}}

                elif event_type == "content_delta":
                    delta = event.get("delta", "")
                    content_buffer += delta
                    yield {"type": "content", "data": {"delta": delta}}

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
                    if response and response.usage:
                        state.add_tokens(response.usage.input_tokens, response.usage.output_tokens)
                    break

        except Exception as e:
            yield {"type": "error", "data": {"message": f"LLM call failed: {str(e)}"}}
            return

        assistant_msg = Message(
            role="assistant",
            content=content_buffer,
            thinking=thinking_buffer if thinking_buffer else None,
            tool_calls=tool_calls_buffer if tool_calls_buffer else None,
        )
        state.messages.append(assistant_msg)

        if not tool_calls_buffer:
            yield {
                "type": "done",
                "data": {
                    "message": content_buffer,
                    "steps": state.current_step,
                    "reason": "completed",
                },
            }
            return

        for tool_call in tool_calls_buffer:
            if is_user_input_tool_call(tool_call.function.name):
                input_fields = parse_user_input_fields(tool_call.function.arguments)
                request = UserInputRequest(
                    tool_call_id=tool_call.id,
                    fields=[
                        UserInputField(
                            field_name=f.field_name,
                            field_type=f.field_type,
                            field_description=f.field_description,
                        )
                        for f in input_fields
                    ],
                    context=tool_call.function.arguments.get("context"),
                )
                state.mark_waiting_input(request, tool_call.id)

                yield {
                    "type": "user_input_required",
                    "data": {
                        "tool_call_id": tool_call.id,
                        "fields": [f.model_dump() for f in input_fields],
                        "context": tool_call.function.arguments.get("context"),
                    },
                }

                ckpt_config = self._config.checkpoint
                if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_user_input:
                    await self._save_checkpoint(
                        state,
                        trigger="user_input_wait",
                        pending_tool_calls=[tool_call],
                    )

                return

        if self._is_cancelled():
            yield {"type": "cancelled", "data": {"message": "Task cancelled by user"}}
            return

        tool_calls_data = [
            (tc.id, tc.function.name, tc.function.arguments) for tc in tool_calls_buffer
        ]
        results = await self._tool_executor.execute_batch(tool_calls_data)

        for exec_result in results:
            if self._is_cancelled():
                yield {"type": "cancelled", "data": {"message": "Task cancelled by user"}}
                return

            yield {
                "type": "tool_result",
                "data": {
                    "tool": exec_result.tool_name,
                    "success": exec_result.result.success,
                    "content": exec_result.result.content if exec_result.result.success else None,
                    "error": exec_result.result.error if not exec_result.result.success else None,
                    "execution_time": exec_result.execution_time,
                },
            }

            tool_content = (
                exec_result.result.content
                if exec_result.result.success
                else f"Error: {exec_result.result.error}"
            )
            state.messages.append(
                Message(
                    role="tool",
                    content=tool_content,
                    tool_call_id=exec_result.tool_call_id,
                    name=exec_result.tool_name,
                )
            )

            if self._config.on_tool_result:
                tool_args = tool_calls_data[
                    [r.tool_call_id for r in results].index(exec_result.tool_call_id)
                ][2]
                await self._config.on_tool_result(
                    exec_result.tool_call_id,
                    exec_result.tool_name,
                    tool_args,
                    tool_content,
                )

        ckpt_config = self._config.checkpoint
        if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_tool_execution:
            await self._save_checkpoint(state, trigger="tool_execution")

    async def resume_from_input(
        self,
        state: AgentState,
        user_response: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not state.is_waiting_input or not state.paused_tool_call_id:
            return "Agent is not waiting for user input"

        tool_msg = Message(
            role="tool",
            content=str(user_response),
            tool_call_id=state.paused_tool_call_id,
            name="get_user_input",
        )
        state.messages.append(tool_msg)
        state.resume_from_input()

        return await self.run(state, metadata)

    async def resume_from_input_stream(
        self,
        state: AgentState,
        user_response: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if not state.is_waiting_input or not state.paused_tool_call_id:
            yield {"type": "error", "data": {"message": "Agent is not waiting for user input"}}
            return

        tool_msg = Message(
            role="tool",
            content=str(user_response),
            tool_call_id=state.paused_tool_call_id,
            name="get_user_input",
        )
        state.messages.append(tool_msg)
        state.resume_from_input()

        async for event in self.run_stream(state, metadata):
            yield event

    async def resume_from_checkpoint(
        self,
        checkpoint_id: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentState, str]:
        if not self.checkpoint_enabled:
            raise RuntimeError("Checkpoint is not enabled")

        config = self._config.checkpoint
        assert config is not None
        storage = config.get_storage()

        checkpoint: Checkpoint | None = None
        if checkpoint_id:
            checkpoint = await storage.load(checkpoint_id)
        elif thread_id:
            checkpoint = await storage.load_latest(thread_id)

        if checkpoint is None:
            raise ValueError(
                f"Checkpoint not found: checkpoint_id={checkpoint_id}, thread_id={thread_id}"
            )

        state = AgentState.from_checkpoint(checkpoint, max_steps=self._config.max_steps)
        state.resume_from_checkpoint()

        result = await self.run(state, metadata)
        return state, result

    async def resume_from_checkpoint_stream(
        self,
        checkpoint_id: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentState, AsyncIterator[dict[str, Any]]]:
        if not self.checkpoint_enabled:
            raise RuntimeError("Checkpoint is not enabled")

        config = self._config.checkpoint
        assert config is not None
        storage = config.get_storage()

        checkpoint: Checkpoint | None = None
        if checkpoint_id:
            checkpoint = await storage.load(checkpoint_id)
        elif thread_id:
            checkpoint = await storage.load_latest(thread_id)

        if checkpoint is None:
            raise ValueError(
                f"Checkpoint not found: checkpoint_id={checkpoint_id}, thread_id={thread_id}"
            )

        state = AgentState.from_checkpoint(checkpoint, max_steps=self._config.max_steps)
        state.resume_from_checkpoint()

        async def stream_generator() -> AsyncIterator[dict[str, Any]]:
            async for event in self.run_stream(state, metadata):
                yield event

        return state, stream_generator()


class Agent(AgentBase):
    """AI Agent 实现

    继承自 AgentBase，实现完整的 Agent 功能：
    - run()/run_stream(): 标准执行模式
    - ralph 参数: 启用 Ralph 迭代模式
    - hooks: 扩展执行流程

    支持功能:
        - 多种系统提示构建方式
        - Token 管理和自动摘要
        - 工具执行（支持并行）
        - 用户输入等待和恢复
        - Langfuse 追踪集成
        - Ralph 迭代开发模式

    创建示例:
        # 方式1: 直接指定模型（推荐）
        agent = Agent(
            model="openai/gpt-4o",
            api_key="sk-xxx",
            tools=[ReadTool(), WriteTool()],
            mcp_config="mcp.json",
            skills_dir="./skills",
        )

        # 方式2: 传入 LLMClient（向后兼容）
        agent = Agent(
            llm_client=my_llm_client,
            tools=[ReadTool()],
        )
    """

    _mcp_tools: list[Tool] = []
    _mcp_initialized: bool = False

    def __init__(
        self,
        # 模型配置（二选一）
        llm_client: LLMClient | None = None,
        model: str = "openai/gpt-4o",
        api_key: str | None = None,
        api_base: str | None = None,
        # 工具配置
        tools: list[Tool] | None = None,
        mcp_config: str | None = None,
        skills_dir: str | None = None,
        # 系统提示
        system_prompt: str | None = None,
        prompt_config: SystemPromptConfig | None = None,
        # 运行配置
        name: str | None = None,
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 120000,
        enable_summarization: bool = True,
        tool_output_limit: int = 10000,
        parallel_tools: bool = False,
        # 可选功能
        enable_logging: bool = True,
        log_dir: str | None = None,
        enable_memory: bool = False,
        memory_base_dir: str = "./.agent_memories",
        ralph: bool | RalphConfig = False,
        # Plan 配置
        enable_planning: bool = False,
        plan_threshold: int = 3,
        # 会话标识
        user_id: str | None = None,
        session_id: str | None = None,
        # 运行时控制
        cancel_event: asyncio.Event | None = None,
        # 向后兼容（已弃用）
        skill_loader: SkillLoader | None = None,
    ) -> None:
        import os

        super().__init__(name=name, max_steps=max_steps)

        self.workspace_dir = Path(workspace_dir)
        self.tool_output_limit = tool_output_limit
        self.user_id = user_id
        self.session_id = session_id
        self.enable_logging = enable_logging
        self.enable_memory = enable_memory
        self.enable_planning = enable_planning
        self._plan_threshold = plan_threshold
        self._mcp_config = mcp_config
        self._skills_dir = skills_dir

        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # 创建或使用传入的 LLMClient
        if llm_client is not None:
            self.llm = llm_client
        else:
            resolved_api_key = api_key or os.getenv("LLM_API_KEY", "")
            if not resolved_api_key:
                raise ValueError(
                    "API key required. Pass api_key parameter or set LLM_API_KEY env var"
                )
            self.llm = LLMClient(
                api_key=resolved_api_key,
                api_base=api_base,
                model=model,
            )

        # 构建工具列表
        self.tools: dict[str, Tool] = {}
        self.skill_loader: SkillLoader | None = skill_loader
        self._init_tools(tools or [])

        # 记忆 Hook
        self._memory_hook: MemoryHook | None = None
        if enable_memory and user_id and session_id:
            self._memory_hook = create_memory_hook(user_id, session_id, memory_base_dir, self.llm)
            if self._memory_hook:
                from omni_agent.tools.memory_tools import DeepRecallMemoryTool

                deep_recall = DeepRecallMemoryTool(self._memory_hook.memory, user_id, session_id)
                self.tools[deep_recall.name] = deep_recall

        self._state = AgentState(max_steps=max_steps)
        self._events = EventEmitter()

        self.token_manager = TokenManager(
            llm_client=self.llm,
            token_limit=token_limit,
            enable_summarization=enable_summarization,
        )

        self._tool_executor = ToolExecutor(
            tools=self.tools,
            output_limit=tool_output_limit,
            parallel_execution=parallel_tools,
        )

        self._ralph_loop: RalphLoop | None = None
        if ralph:
            ralph_config = ralph if isinstance(ralph, RalphConfig) else RalphConfig(enabled=True)
            self._ralph_loop = RalphLoop(
                config=ralph_config,
                workspace_dir=self.workspace_dir,
                summarize_fn=self._summarize_for_ralph,
            )

        loop_config = LoopConfig(
            max_steps=max_steps,
            parallel_tools=parallel_tools,
            on_tool_result=self._handle_ralph_tool_result if self._ralph_loop else None,
            cancel_event=cancel_event,
        )

        self._loop = AgentLoop(
            llm_client=self.llm,
            tool_executor=self._tool_executor,
            token_manager=self.token_manager,
            event_emitter=self._events,
            config=loop_config,
        )
        self._loop.set_tools(self.tools)

        if self._memory_hook:
            self._loop.hooks.add(self._memory_hook)

        self.tracer: LangfuseTracer | None = None
        self.execution_logs: list[dict[str, Any]] = []

        # 构建系统提示
        self.system_prompt = self._build_system_prompt(system_prompt, prompt_config)
        self._state.messages = [Message(role="system", content=self.system_prompt)]

    def _init_tools(self, tools: list[Tool]) -> None:
        """初始化工具列表（包括传入的工具、MCP工具、Skills）"""
        from omni_agent.skills.skill_tool import GetSkillTool

        # 添加传入的工具
        for tool in tools:
            self.tools[tool.name] = tool

        # 加载 Skills
        if self._skills_dir and Path(self._skills_dir).exists():
            self.skill_loader = SkillLoader(self._skills_dir)
            self.skill_loader.discover_skills()
            if self.skill_loader.loaded_skills:
                self.tools["get_skill"] = GetSkillTool(self.skill_loader)

    async def _load_mcp_tools(self) -> None:
        """异步加载 MCP 工具（首次调用 run 时执行）"""
        if self._mcp_initialized or not self._mcp_config:
            return

        if not Path(self._mcp_config).exists():
            self._mcp_initialized = True
            return

        try:
            from omni_agent.tools.mcp_loader import load_mcp_tools_async

            mcp_tools = await load_mcp_tools_async(self._mcp_config)
            if mcp_tools:
                for tool in mcp_tools:
                    self.tools[tool.name] = tool
                self._tool_executor = ToolExecutor(
                    tools=self.tools,
                    output_limit=self.tool_output_limit,
                    parallel_execution=self._loop._config.parallel_tools,
                )
                self._loop.set_tools(self.tools)
        except Exception:
            logger.warning("MCP tools loading failed", exc_info=True)
        finally:
            self._mcp_initialized = True

    def _build_system_prompt(
        self,
        system_prompt: str | None,
        prompt_config: SystemPromptConfig | None,
    ) -> str:
        """构建系统提示"""
        if prompt_config:
            result = self._build_structured_prompt(prompt_config)
        elif system_prompt:
            result = system_prompt
        else:
            result = self._build_default_prompt()

        # 注入工作目录信息
        if "Current Workspace" not in result and "workspace_info" not in result:
            workspace_info = (
                f"\n\n## Current Workspace\n"
                f"You are currently working in: `{self.workspace_dir.absolute()}`\n"
                f"All relative paths will be resolved relative to this directory."
            )
            result = result + workspace_info

        # 注入 Skills 元数据
        if self.skill_loader and self.skill_loader.loaded_skills:
            skills_metadata = self.skill_loader.get_skills_metadata_prompt()
            if skills_metadata:
                result = f"{result}\n\n{skills_metadata}"

        # 注入记忆上下文
        if self._memory_hook:
            memory_context = self._memory_hook.get_context_for_prompt()
            result = f"{result}\n\n{memory_context}"

        return result

    @property
    def messages(self) -> list[Message]:
        return self._state.messages

    @messages.setter
    def messages(self, value: list[Message]) -> None:
        self._state.messages = value

    @property
    def hooks(self) -> HookManager:
        return self._loop.hooks

    def add_hook(self, hook: AgentHook) -> None:
        self._loop.hooks.add(hook)

    def remove_hook(self, hook: AgentHook) -> None:
        self._loop.hooks.remove(hook)

    def _collect_tool_instructions(self) -> list[str]:
        instructions = []
        for tool in self.tools.values():
            if tool.add_instructions_to_prompt and tool.instructions:
                instructions.append(tool.instructions)
        return instructions

    def _build_structured_prompt(self, config: SystemPromptConfig) -> str:
        tool_instructions = self._collect_tool_instructions()
        builder = SystemPromptBuilder()
        return builder.build(
            config=config,
            workspace_dir=self.workspace_dir,
            skill_loader=self.skill_loader,
            tool_instructions=tool_instructions,
        )

    def _build_default_prompt(self) -> str:
        config = SystemPromptConfig(
            description="You are a helpful AI assistant.",
            instructions=[
                "Always think step by step",
                "Use available tools when appropriate",
                "Provide clear and accurate responses",
            ],
        )
        return self._build_structured_prompt(config)

    def add_user_message(self, content: str) -> None:
        self._state.messages.append(Message(role="user", content=content))

    def _setup_execution_logging(self) -> None:
        self.execution_logs = []

        async def collect_step_start(event: AgentEvent) -> None:
            self.execution_logs.append(
                {
                    "type": "step",
                    "step": event.step,
                    "max_steps": event.data.get("max_steps", self.max_steps),
                    "tokens": event.data.get("tokens", 0),
                    "token_limit": event.data.get("token_limit", self.token_manager.token_limit),
                }
            )
            if self.tracer:
                self.tracer.log_step(
                    step=event.step,
                    max_steps=event.data.get("max_steps", self.max_steps),
                    token_count=event.data.get("tokens", 0),
                    token_limit=event.data.get("token_limit", self.token_manager.token_limit),
                )

        async def collect_llm_response(event: AgentEvent) -> None:
            self.execution_logs.append(
                {
                    "type": "llm_response",
                    "thinking": event.data.get("thinking"),
                    "content": event.data.get("content"),
                    "has_tool_calls": event.data.get("has_tool_calls", False),
                    "tool_count": event.data.get("tool_count", 0),
                    "input_tokens": event.data.get("input_tokens", 0),
                    "output_tokens": event.data.get("output_tokens", 0),
                }
            )
            if self.tracer and event.data.get("input_tokens"):
                self.tracer.log_llm_response(
                    input_tokens=event.data.get("input_tokens", 0),
                    output_tokens=event.data.get("output_tokens", 0),
                )

        async def collect_tool_start(event: AgentEvent) -> None:
            self.execution_logs.append(
                {
                    "type": "tool_call",
                    "tool": event.data.get("tool"),
                    "arguments": event.data.get("arguments"),
                }
            )

        async def collect_tool_end(event: AgentEvent) -> None:
            if self.tracer:
                pass
            else:
                self.execution_logs.append(
                    {
                        "type": "tool_result",
                        "tool": event.data.get("tool"),
                        "success": event.data.get("success"),
                        "content": event.data.get("content"),
                        "error": event.data.get("error"),
                        "execution_time": event.data.get("execution_time"),
                    }
                )

        async def collect_user_input(event: AgentEvent) -> None:
            self.execution_logs.append(
                {
                    "type": "user_input_required",
                    "tool_call_id": event.data.get("tool_call_id"),
                    "fields": event.data.get("fields"),
                    "context": event.data.get("context"),
                }
            )

        async def collect_completion(event: AgentEvent) -> None:
            self.execution_logs.append(
                {
                    "type": "completion",
                    "message": "Task completed successfully",
                    "total_input_tokens": event.data.get("total_input_tokens", 0),
                    "total_output_tokens": event.data.get("total_output_tokens", 0),
                    "total_tokens": (
                        event.data.get("total_input_tokens", 0)
                        + event.data.get("total_output_tokens", 0)
                    ),
                }
            )
            if self.tracer:
                self.tracer.end_trace(
                    success=True,
                    final_response=event.data.get("message", ""),
                    total_steps=event.data.get("total_steps", self._state.current_step),
                    reason="task_completed",
                )

        async def collect_error(event: AgentEvent) -> None:
            reason = event.data.get("reason", "error")
            if reason == "max_steps_reached":
                self.execution_logs.append(
                    {
                        "type": "max_steps_reached",
                        "message": event.data.get("message"),
                        "total_input_tokens": self._state.total_input_tokens,
                        "total_output_tokens": self._state.total_output_tokens,
                        "total_tokens": self._state.total_tokens,
                    }
                )
            else:
                self.execution_logs.append(
                    {
                        "type": "error",
                        "message": event.data.get("message"),
                    }
                )
            if self.tracer:
                self.tracer.end_trace(
                    success=False,
                    final_response=event.data.get("message", ""),
                    total_steps=self._state.current_step,
                    reason=reason,
                )

        self._events.clear()
        self._events.on(EventType.STEP_START, collect_step_start)
        self._events.on(EventType.LLM_RESPONSE, collect_llm_response)
        self._events.on(EventType.TOOL_START, collect_tool_start)
        self._events.on(EventType.TOOL_END, collect_tool_end)
        self._events.on(EventType.USER_INPUT_REQUIRED, collect_user_input)
        self._events.on(EventType.COMPLETION, collect_completion)
        self._events.on(EventType.ERROR, collect_error)

    def _setup_tracer(self) -> None:
        if not self.enable_logging:
            self.tracer = None
            return

        self.tracer = get_tracer(
            name=self.name,
            user_id=self.user_id,
            session_id=self.session_id,
            metadata={"max_steps": self.max_steps},
        )
        task = ""
        if self._state.messages and len(self._state.messages) > 1:
            for msg in reversed(self._state.messages):
                if msg.role == "user":
                    task = msg.content[:200] if msg.content else ""
                    break
        self.tracer.start_trace(task)

    async def run(self, task: str | None = None) -> tuple[str, list[dict[str, Any]]]:
        await self._load_mcp_tools()

        if self._ralph_loop:
            if task:
                return await self._run_ralph_internal(task)
            user_msg = self._get_last_user_message()
            if user_msg:
                return await self._run_ralph_internal(user_msg)
            raise ValueError(
                "Ralph mode requires a task. Pass task parameter or call add_user_message() first."
            )

        if self.enable_planning:
            await self._maybe_create_plan()

        self._setup_tracer()
        self._setup_execution_logging()
        result = await self._loop.run(self._state, self._get_llm_metadata())

        if self.enable_planning:
            self._update_plan_on_completion(result)

        return result, self.execution_logs

    async def _maybe_create_plan(self) -> None:
        existing = Plan.load(self.workspace_dir)
        if existing and existing.status in (PlanStatus.IN_PROGRESS, PlanStatus.APPROVED):
            plan_context = (
                f"\n\n## Current Plan\n{existing.to_markdown()}\n"
                f"Continue from step {(existing.current_step_index or 0) + 1}."
            )
            self._state.messages.append(Message(role="system", content=plan_context))
            existing.start()
            existing.save(self.workspace_dir)
            await self._events.emit(
                AgentEvent(
                    type=EventType.PLAN_CREATED,
                    data={"plan": existing.to_markdown(), "resumed": True},
                )
            )
            return

        user_msg = self._get_last_user_message()
        if not user_msg or len(user_msg) < 50:
            return

        task_indicators = [
            "\n",
            "step",
            "1.",
            "2.",
            "first",
            "then",
            "finally",
            "and",
            "create",
            "refactor",
            "fix",
            "add",
            "update",
        ]
        complexity = sum(1 for ind in task_indicators if ind.lower() in user_msg.lower())
        if complexity < self._plan_threshold:
            return

        plan_prompt = (
            f"Analyze this task and create a step-by-step plan. "
            f"Return ONLY a numbered list of concrete steps (max 7 steps).\n\n"
            f"Task: {user_msg}"
        )
        try:
            response = await self.llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a planning assistant. Output only numbered steps.",
                    },
                    {"role": "user", "content": plan_prompt},
                ],
                tools=[],
            )
            steps_text = response.content or ""
            import re

            step_lines = re.findall(r"^\d+[\.\)]\s*(.+)$", steps_text, re.MULTILINE)
            if not step_lines:
                return

            from omni_agent.core.planner import PlanStep

            plan = Plan(
                task_summary=user_msg[:100],
                steps=[PlanStep(description=s.strip()) for s in step_lines],
                done_when=[f"All {len(step_lines)} steps completed"],
                status=PlanStatus.IN_PROGRESS,
            )
            plan.save(self.workspace_dir)

            plan_context = (
                f"\n\n## Execution Plan\n{plan.to_markdown()}\nFollow this plan step by step."
            )
            self._state.messages.append(Message(role="system", content=plan_context))
            await self._events.emit(
                AgentEvent(
                    type=EventType.PLAN_CREATED,
                    data={"plan": plan.to_markdown(), "resumed": False},
                )
            )
        except Exception:
            logger.warning("Plan creation failed", exc_info=True)

    def _update_plan_on_completion(self, result: str) -> None:
        plan = Plan.load(self.workspace_dir)
        if not plan or plan.status == PlanStatus.COMPLETED:
            return

        for i, step in enumerate(plan.steps):
            if not step.done:
                plan.mark_step_done(i)
                break

        plan.save(self.workspace_dir)

    async def run_stream(self, task: str | None = None) -> AsyncIterator[dict[str, Any]]:
        # 首次运行时加载 MCP 工具
        await self._load_mcp_tools()

        if self._ralph_loop:
            if not task:
                task = self._get_last_user_message()
            if not task:
                yield {"type": "error", "data": {"message": "Ralph mode requires a task"}}
                return
            async for event in self._run_ralph_stream_internal(task):
                yield event
            return

        self._setup_tracer()
        self._setup_execution_logging()
        async for event in self._loop.run_stream(self._state, self._get_llm_metadata()):
            yield event

    def _get_last_user_message(self) -> str | None:
        for msg in reversed(self._state.messages):
            if msg.role == "user" and msg.content:
                if isinstance(msg.content, str):
                    return msg.content
                return None
        return None

    def _get_llm_metadata(self) -> dict[str, Any] | None:
        if self.tracer:
            return self.tracer.get_litellm_metadata()
        return None

    def get_history(self) -> list[Message]:
        return self._state.messages.copy()

    @property
    def pending_user_input(self) -> UserInputRequest | None:
        return self._state.pending_user_input

    @property
    def is_waiting_for_input(self) -> bool:
        return self._state.is_waiting_input

    def provide_user_input(self, field_values: dict[str, Any]) -> None:
        if not self._state.pending_user_input:
            raise ValueError("No pending user input request")

        for input_field in self._state.pending_user_input.fields:
            if input_field.field_name in field_values:
                input_field.value = field_values[input_field.field_name]

        user_input_result = [
            {"name": input_field.field_name, "value": input_field.value}
            for input_field in self._state.pending_user_input.fields
        ]

        tool_msg = Message(
            role="tool",
            content=f"User inputs received: {json.dumps(user_input_result, ensure_ascii=False)}",
            tool_call_id=self._state.pending_user_input.tool_call_id,
            name=GetUserInputTool.TOOL_NAME,
        )
        self._state.messages.append(tool_msg)

        self.execution_logs.append(
            {
                "type": "user_input_received",
                "tool_call_id": self._state.pending_user_input.tool_call_id,
                "field_values": field_values,
            }
        )

        self._state.resume_from_input()

    async def resume(self) -> tuple[str, list[dict[str, Any]]]:
        if self._state.pending_user_input:
            raise ValueError(
                "Cannot resume: still waiting for user input. Call provide_user_input first."
            )
        return await self.run()

    async def resume_stream(self) -> AsyncIterator[dict[str, Any]]:
        if self._state.pending_user_input:
            raise ValueError(
                "Cannot resume: still waiting for user input. Call provide_user_input first."
            )
        async for event in self.run_stream():
            yield event

    @property
    def _pending_user_input(self) -> UserInputRequest | None:
        return self._state.pending_user_input

    @_pending_user_input.setter
    def _pending_user_input(self, value: UserInputRequest | None) -> None:
        self._state.pending_user_input = value

    @property
    def _current_step(self) -> int:
        return self._state.current_step

    @_current_step.setter
    def _current_step(self, value: int) -> None:
        self._state.current_step = value

    @property
    def _paused_tool_call_id(self) -> str | None:
        return self._state.paused_tool_call_id

    @_paused_tool_call_id.setter
    def _paused_tool_call_id(self, value: str | None) -> None:
        self._state.paused_tool_call_id = value

    def _truncate_tool_output(self, content: str) -> str:
        if len(content) <= self.tool_output_limit:
            return content
        truncated = content[: self.tool_output_limit]
        return f"{truncated}\n\n[... output truncated, {len(content) - self.tool_output_limit} more characters ...]"

    async def _handle_ralph_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        content: str,
    ) -> None:
        if self._ralph_loop:
            await self._ralph_loop.process_tool_result(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=arguments,
                content=content,
            )

    async def _summarize_for_ralph(self, content: str) -> str:
        response = await self.llm.generate(
            messages=[
                Message(
                    role="system",
                    content="You are a helpful assistant that creates concise summaries.",
                ),
                Message(role="user", content=content),
            ],
            tools=None,
        )
        return response.content or content[:500]

    @property
    def ralph_loop(self) -> RalphLoop | None:
        return self._ralph_loop

    @property
    def ralph_enabled(self) -> bool:
        return self._ralph_loop is not None

    def get_ralph_tools(self) -> list[Tool]:
        if not self._ralph_loop:
            return []

        from omni_agent.tools.ralph_tools import (
            GetCachedResultTool,
            GetWorkingMemoryTool,
            SignalCompletionTool,
            UpdateWorkingMemoryTool,
        )

        return [
            GetCachedResultTool(self._ralph_loop.context_manager),
            GetWorkingMemoryTool(self._ralph_loop.working_memory),
            UpdateWorkingMemoryTool(self._ralph_loop.working_memory),
            SignalCompletionTool(),
        ]

    def _inject_ralph_tools(self) -> None:
        """注入 Ralph 专用工具.

        将 get_cached_result、update_working_memory、get_working_memory、
        signal_completion 等工具注入到 Agent 的工具集中。
        """
        if not self._ralph_loop:
            return

        ralph_tools = self.get_ralph_tools()
        for tool in ralph_tools:
            self.tools[tool.name] = tool
        self._loop.set_tools(self.tools)

    def _build_ralph_system_prompt(self, base_prompt: str, task: str) -> str:
        """构建 Ralph 模式的系统提示.

        在基础系统提示上追加 Ralph 上下文信息，包括:
        - 当前迭代次数
        - 工作记忆内容
        - 完成信号指南
        - 工具使用说明

        Args:
            base_prompt: 基础系统提示
            task: 当前任务描述

        Returns:
            增强后的系统提示
        """
        if not self._ralph_loop:
            return base_prompt

        context_prefix = self._ralph_loop.get_context_prefix()
        iteration = self._ralph_loop.state.iteration

        ralph_section = f"""
## Ralph Mode (Iteration {iteration})

You are operating in Ralph iterative mode. Your task is:
{task}

### Working Memory
{context_prefix}

### Completion
When you have completed the task, use the `signal_completion` tool or output:
<promise>TASK COMPLETE</promise>

### Guidelines
- Review the working memory for context from previous iterations
- Use `update_working_memory` to record progress and findings
- Use `get_cached_result` to retrieve full tool outputs when summaries are insufficient
- Focus on making incremental progress each iteration
"""
        return f"{base_prompt}\n{ralph_section}"

    async def _run_ralph_internal(self, task: str) -> tuple[str, list[dict[str, Any]]]:
        """执行 Ralph 迭代循环.

        Ralph 模式下，同一任务会反复执行多次迭代，Agent 可以看到之前的工作成果
        并逐步改进，直到检测到完成条件。

        Args:
            task: 要执行的任务描述

        Returns:
            (最终结果, 执行日志列表)
        """
        if not self._ralph_loop:
            raise RuntimeError("Ralph mode is not enabled. Initialize Agent with ralph_config.")

        self._inject_ralph_tools()
        self._setup_tracer()
        self._setup_execution_logging()

        final_result = ""

        while not self._ralph_loop.state.completed:
            iteration = self._ralph_loop.start_iteration()

            await self._events.emit(
                AgentEvent(
                    type=EventType.RALPH_ITERATION_START,
                    step=0,
                    data={
                        "iteration": iteration,
                        "max_iterations": self._ralph_loop.config.max_iterations,
                    },
                )
            )

            ralph_system_prompt = self._build_ralph_system_prompt(self.system_prompt, task)
            self._state.messages = [
                Message(role="system", content=ralph_system_prompt),
                Message(role="user", content=task),
            ]

            result = await self._loop.run(self._state, self._get_llm_metadata())
            final_result = result

            completion_check = self._ralph_loop.check_completion(result)

            await self._events.emit(
                AgentEvent(
                    type=EventType.RALPH_ITERATION_END,
                    step=0,
                    data={
                        "iteration": iteration,
                        "completed": completion_check.completed,
                        "reason": completion_check.reason.value
                        if completion_check.reason
                        else None,
                    },
                )
            )

            if completion_check.completed:
                await self._events.emit(
                    AgentEvent(
                        type=EventType.RALPH_COMPLETION,
                        step=0,
                        data={
                            "iteration": iteration,
                            "reason": completion_check.reason.value
                            if completion_check.reason
                            else None,
                            "message": completion_check.message,
                        },
                    )
                )
                break

            messages_content = "\n".join(
                f"{m.role}: {m.content[:500]}" for m in self._state.messages if m.content
            )
            await self._ralph_loop.summarize_iteration(messages_content)

        return final_result, self.execution_logs

    async def run_ralph(self, task: str) -> tuple[str, list[dict[str, Any]]]:
        return await self._run_ralph_internal(task)

    async def _run_ralph_stream_internal(self, task: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行 Ralph 迭代循环.

        与 _run_ralph_internal 相同，但以流式方式输出中间事件，
        包括迭代开始/结束、LLM 响应流和完成信号。

        Args:
            task: 要执行的任务描述

        Yields:
            事件字典，包含 type 和 data 字段
        """
        if not self._ralph_loop:
            yield {"type": "error", "data": {"message": "Ralph mode is not enabled"}}
            return

        self._inject_ralph_tools()
        self._setup_tracer()
        self._setup_execution_logging()

        while not self._ralph_loop.state.completed:
            iteration = self._ralph_loop.start_iteration()

            yield {
                "type": "ralph_iteration_start",
                "data": {
                    "iteration": iteration,
                    "max_iterations": self._ralph_loop.config.max_iterations,
                },
            }

            ralph_system_prompt = self._build_ralph_system_prompt(self.system_prompt, task)
            self._state.messages = [
                Message(role="system", content=ralph_system_prompt),
                Message(role="user", content=task),
            ]

            final_content = ""
            async for event in self._loop.run_stream(self._state, self._get_llm_metadata()):
                yield event
                if event["type"] == "done":
                    final_content = event.get("data", {}).get("message", "")

            completion_check = self._ralph_loop.check_completion(final_content)

            yield {
                "type": "ralph_iteration_end",
                "data": {
                    "iteration": iteration,
                    "completed": completion_check.completed,
                    "reason": completion_check.reason.value if completion_check.reason else None,
                },
            }

            if completion_check.completed:
                yield {
                    "type": "ralph_completion",
                    "data": {
                        "iteration": iteration,
                        "reason": completion_check.reason.value
                        if completion_check.reason
                        else None,
                        "message": completion_check.message,
                    },
                }
                break

            messages_content = "\n".join(
                f"{m.role}: {m.content[:500]}" for m in self._state.messages if m.content
            )
            await self._ralph_loop.summarize_iteration(messages_content)

    async def run_ralph_stream(self, task: str) -> AsyncIterator[dict[str, Any]]:
        async for event in self._run_ralph_stream_internal(task):
            yield event

    def get_ralph_status(self) -> dict[str, Any] | None:
        if not self._ralph_loop:
            return None
        return self._ralph_loop.get_status()

    def reset_ralph(self) -> None:
        if self._ralph_loop:
            self._ralph_loop.reset()

    def observe(self, msg: "Message") -> None:
        """接收外部消息并注入到 Agent 的消息历史中。

        由 MsgHub 的广播处理器调用，将其他参与者的发言
        或系统公告注入到当前 Agent 的对话上下文中，使其
        在下一轮发言时能看到这些消息。

        Args:
            msg: 要注入的消息对象
        """
        self._state.messages.append(msg)

    async def execute_turn(self, max_steps: int = 10) -> tuple[str, list[dict]]:
        """执行一个讨论轮次（供 MsgHub 调用）。

        与 run() 不同，execute_turn() 专为 MsgHub 多 Agent 场景设计：
        1. 保存外部事件处理器（如 MsgHub 的广播 handler）
        2. 调用 _setup_execution_logging() 重置日志收集器
        3. 恢复外部事件处理器（因为 _setup_execution_logging 会 clear 所有 handler）
        4. 临时修改 max_steps 限制单轮执行步数
        5. 执行 AgentLoop.run() 完成一轮对话

        这种 save-restore 机制确保 MsgHub 的 COMPLETION 事件广播
        不会被 _setup_execution_logging 的 clear() 操作破坏。

        Args:
            max_steps: 本轮最大执行步数，默认 10

        Returns:
            (response, execution_logs) 元组
        """
        # 保存当前所有外部注册的事件处理器
        saved_handlers: dict[EventType, list[EventHandler]] = {}
        for etype, handlers in self._events._handlers.items():
            saved_handlers[etype] = list(handlers)
        saved_global = list(self._events._global_handlers)

        # _setup_execution_logging 会 clear() 所有 handler 后重新注册日志收集器
        self._setup_execution_logging()

        # 恢复之前保存的外部 handler（如 MsgHub 的广播处理器）
        for etype, handlers in saved_handlers.items():
            for h in handlers:
                if h not in self._events._handlers.get(etype, []):
                    self._events.on(etype, h)
        for h in saved_global:
            if h not in self._events._global_handlers:
                self._events.on_all(h)

        # 临时限制步数，执行完后恢复
        original_max_steps = self._loop._config.max_steps
        self._loop._config.max_steps = max_steps
        try:
            result = await self._loop.run(self._state, self._get_llm_metadata())
        finally:
            self._loop._config.max_steps = original_max_steps
        return result, self.execution_logs
