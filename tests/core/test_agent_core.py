import asyncio
from unittest.mock import AsyncMock, MagicMock

from omni_agent.core.agent import (
    AgentEvent,
    AgentLoop,
    AgentState,
    EventEmitter,
    EventType,
    HookManager,
    LoopConfig,
    StepResult,
)
from omni_agent.core.agent_base import AgentStatus
from omni_agent.core.hooks import AgentHook, HookContext
from omni_agent.schemas.message import (
    FunctionCall,
    Message,
    ToolCall,
    UserInputRequest,
)


class TestEventType:
    def test_all_types_exist(self) -> None:
        expected = [
            "step_start",
            "step_end",
            "llm_request",
            "llm_response",
            "tool_start",
            "tool_end",
            "user_input_required",
            "completion",
            "cancelled",
            "error",
            "token_summary",
        ]
        values = [e.value for e in EventType]
        for exp in expected:
            assert exp in values


class TestAgentEvent:
    def test_creation(self) -> None:
        event = AgentEvent(type=EventType.STEP_START, data={"step": 1}, step=1)
        assert event.type == EventType.STEP_START
        assert event.data == {"step": 1}
        assert event.step == 1
        assert event.timestamp > 0

    def test_default_step(self) -> None:
        event = AgentEvent(type=EventType.COMPLETION, data={})
        assert event.step == 0


class TestEventEmitter:
    async def test_emit_to_typed_handler(self) -> None:
        emitter = EventEmitter()
        received = []

        async def handler(event: AgentEvent) -> None:
            received.append(event)

        emitter.on(EventType.STEP_START, handler)
        await emitter.emit(AgentEvent(type=EventType.STEP_START, data={"x": 1}))
        assert len(received) == 1
        assert received[0].data == {"x": 1}

    async def test_emit_to_global_handler(self) -> None:
        emitter = EventEmitter()
        received = []

        async def handler(event: AgentEvent) -> None:
            received.append(event)

        emitter.on_all(handler)
        await emitter.emit(AgentEvent(type=EventType.STEP_START, data={}))
        await emitter.emit(AgentEvent(type=EventType.COMPLETION, data={}))
        assert len(received) == 2

    async def test_off_removes_handler(self) -> None:
        emitter = EventEmitter()
        received = []

        async def handler(event: AgentEvent) -> None:
            received.append(event)

        emitter.on(EventType.STEP_START, handler)
        emitter.off(EventType.STEP_START, handler)
        await emitter.emit(AgentEvent(type=EventType.STEP_START, data={}))
        assert len(received) == 0

    async def test_off_all_removes_global(self) -> None:
        emitter = EventEmitter()
        received = []

        async def handler(event: AgentEvent) -> None:
            received.append(event)

        emitter.on_all(handler)
        emitter.off_all(handler)
        await emitter.emit(AgentEvent(type=EventType.STEP_START, data={}))
        assert len(received) == 0

    async def test_clear(self) -> None:
        emitter = EventEmitter()

        async def handler(event: AgentEvent) -> None:
            pass

        emitter.on(EventType.STEP_START, handler)
        emitter.on_all(handler)
        emitter.clear()
        assert emitter._handlers == {}
        assert emitter._global_handlers == []

    async def test_unregistered_event_type_no_error(self) -> None:
        emitter = EventEmitter()
        await emitter.emit(AgentEvent(type=EventType.ERROR, data={}))


class TestAgentState:
    def test_default_state(self) -> None:
        state = AgentState()
        assert state.status == AgentStatus.IDLE
        assert state.current_step == 0
        assert state.max_steps == 50
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0
        assert state.messages == []

    def test_reset_for_run(self) -> None:
        state = AgentState()
        state.current_step = 5
        state.total_input_tokens = 1000
        state.status = AgentStatus.COMPLETED
        state.reset_for_run()
        assert state.status == AgentStatus.RUNNING
        assert state.current_step == 0
        assert state.total_input_tokens == 0

    def test_increment_step(self) -> None:
        state = AgentState()
        assert state.increment_step() == 1
        assert state.increment_step() == 2
        assert state.current_step == 2

    def test_add_tokens(self) -> None:
        state = AgentState()
        state.add_tokens(100, 50)
        assert state.total_input_tokens == 100
        assert state.total_output_tokens == 50
        state.add_tokens(200, 100)
        assert state.total_tokens == 450

    def test_mark_completed(self) -> None:
        state = AgentState()
        state.status = AgentStatus.RUNNING
        state.mark_completed()
        assert state.is_completed

    def test_mark_error(self) -> None:
        state = AgentState()
        state.mark_error("something broke")
        assert state.is_error
        assert state.error_message == "something broke"

    def test_mark_cancelled(self) -> None:
        state = AgentState()
        state.mark_cancelled()
        assert state.is_cancelled
        assert state.error_message == "Task cancelled by user"

    def test_mark_waiting_input(self) -> None:
        state = AgentState()
        req = UserInputRequest(tool_call_id="tc_1", fields=[], context="need info")
        state.mark_waiting_input(req, "tc_1")
        assert state.is_waiting_input
        assert state.pending_user_input is req
        assert state.paused_tool_call_id == "tc_1"

    def test_resume_from_input(self) -> None:
        state = AgentState()
        state.status = AgentStatus.WAITING_INPUT
        state.resume_from_input()
        assert state.is_running

    def test_can_continue(self) -> None:
        state = AgentState(max_steps=10)
        state.status = AgentStatus.RUNNING
        state.current_step = 5
        assert state.can_continue is True
        state.current_step = 10
        assert state.can_continue is False

    def test_to_checkpoint_data(self) -> None:
        state = AgentState()
        state.current_step = 3
        state.status = AgentStatus.RUNNING
        data = state.to_checkpoint_data()
        assert data["step"] == 3
        assert data["status"] == "running"


class TestHookManager:
    async def test_add_and_trigger(self) -> None:
        manager = HookManager()
        triggered = []

        class TestHook(AgentHook):
            async def before_run(self, ctx: HookContext) -> None:
                triggered.append("before")

            async def on_step(self, ctx: HookContext, step_data: dict) -> None:
                triggered.append("step")

            async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
                triggered.append("after")

        hook = TestHook()
        manager.add(hook)

        ctx = HookContext(state=AgentState(), step=0)
        await manager.trigger_before_run(ctx)
        await manager.trigger_on_step(ctx, {})
        await manager.trigger_after_run(ctx, "done", True)
        assert triggered == ["before", "step", "after"]

    async def test_remove_hook(self) -> None:
        manager = HookManager()

        class TestHook(AgentHook):
            pass

        hook = TestHook()
        manager.add(hook)
        manager.remove(hook)
        assert len(manager._hooks) == 0

    async def test_clear(self) -> None:
        manager = HookManager()

        class TestHook(AgentHook):
            pass

        manager.add(TestHook())
        manager.add(TestHook())
        manager.clear()
        assert len(manager._hooks) == 0


class TestStepResult:
    def test_default(self) -> None:
        result = StepResult()
        assert result.completed is False
        assert result.waiting_input is False
        assert result.cancelled is False
        assert result.content == ""
        assert result.error is None

    def test_completed(self) -> None:
        result = StepResult(completed=True, content="done")
        assert result.completed is True
        assert result.content == "done"


class TestLoopConfig:
    def test_defaults(self) -> None:
        config = LoopConfig()
        assert config.max_steps == 50
        assert config.parallel_tools is False
        assert config.checkpoint is None
        assert config.cancel_event is None

    def test_custom(self) -> None:
        event = asyncio.Event()
        config = LoopConfig(max_steps=10, cancel_event=event)
        assert config.max_steps == 10
        assert config.cancel_event is event


class TestAgentLoopCancellation:
    def _make_loop(self, cancel_event=None) -> AgentLoop:
        llm = MagicMock()
        tool_executor = MagicMock()
        from omni_agent.core.token_manager import TokenManager

        token_manager = MagicMock(spec=TokenManager)
        token_manager.estimate_tokens = MagicMock(return_value=100)
        token_manager.maybe_summarize_messages = AsyncMock(side_effect=lambda msgs: msgs)

        config = LoopConfig(max_steps=5, cancel_event=cancel_event)
        return AgentLoop(
            llm_client=llm,
            tool_executor=tool_executor,
            token_manager=token_manager,
            event_emitter=EventEmitter(),
            config=config,
        )

    def test_is_cancelled_false_when_no_event(self) -> None:
        loop = self._make_loop()
        assert loop._is_cancelled() is False

    def test_is_cancelled_false_when_not_set(self) -> None:
        event = asyncio.Event()
        loop = self._make_loop(cancel_event=event)
        assert loop._is_cancelled() is False

    def test_is_cancelled_true_when_set(self) -> None:
        event = asyncio.Event()
        event.set()
        loop = self._make_loop(cancel_event=event)
        assert loop._is_cancelled() is True

    def test_set_cancel_event(self) -> None:
        loop = self._make_loop()
        event = asyncio.Event()
        loop.set_cancel_event(event)
        assert loop._config.cancel_event is event


class TestAgentLoopCleanup:
    def test_cleanup_incomplete_messages_empty(self) -> None:
        llm = MagicMock()
        tool_executor = MagicMock()
        token_manager = MagicMock()
        loop = AgentLoop(
            llm_client=llm,
            tool_executor=tool_executor,
            token_manager=token_manager,
            event_emitter=EventEmitter(),
        )
        state = AgentState()
        assert loop._cleanup_incomplete_messages(state) == 0

    def test_cleanup_removes_incomplete_tool_calls(self) -> None:
        llm = MagicMock()
        tool_executor = MagicMock()
        token_manager = MagicMock()
        loop = AgentLoop(
            llm_client=llm,
            tool_executor=tool_executor,
            token_manager=token_manager,
            event_emitter=EventEmitter(),
        )
        state = AgentState()
        state.messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        type="function",
                        function=FunctionCall(name="bash", arguments={"command": "ls"}),
                    )
                ],
            ),
        ]
        removed = loop._cleanup_incomplete_messages(state)
        assert removed > 0
        assert len(state.messages) == 2

    def test_cleanup_keeps_complete_messages(self) -> None:
        llm = MagicMock()
        tool_executor = MagicMock()
        token_manager = MagicMock()
        loop = AgentLoop(
            llm_client=llm,
            tool_executor=tool_executor,
            token_manager=token_manager,
            event_emitter=EventEmitter(),
        )
        state = AgentState()
        state.messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        type="function",
                        function=FunctionCall(name="bash", arguments={"command": "ls"}),
                    )
                ],
            ),
            Message(role="tool", content="output", tool_call_id="call_1"),
        ]
        removed = loop._cleanup_incomplete_messages(state)
        assert removed == 0
        assert len(state.messages) == 4


class TestAgentLoopToolSchemas:
    def test_set_tools(self) -> None:
        from omni_agent.tools.base import Tool

        class DummyTool(Tool):
            @property
            def name(self):
                return "dummy"

            @property
            def description(self):
                return "A dummy"

            @property
            def parameters(self):
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                return MagicMock(success=True, content="ok")

        llm = MagicMock()
        from omni_agent.core.tool_executor import ToolExecutor

        tool_executor = ToolExecutor()
        token_manager = MagicMock()
        loop = AgentLoop(
            llm_client=llm,
            tool_executor=tool_executor,
            token_manager=token_manager,
            event_emitter=EventEmitter(),
        )
        dummy = DummyTool()
        loop.set_tools({"dummy": dummy})
        schemas = loop.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "dummy"

    def test_get_tool_schemas_empty(self) -> None:
        llm = MagicMock()
        tool_executor = MagicMock()
        token_manager = MagicMock()
        loop = AgentLoop(
            llm_client=llm,
            tool_executor=tool_executor,
            token_manager=token_manager,
            event_emitter=EventEmitter(),
        )
        assert loop.get_tool_schemas() == []
