"""Self-improvement hook tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from omni_agent.core import Agent
from omni_agent.core.agent import AgentState
from omni_agent.core.hooks import HookContext
from omni_agent.core.self_improvement_hook import REMINDER_SENTINEL, SelfImprovementHook
from omni_agent.schemas.message import FunctionCall, LLMResponse, Message, ToolCall
from omni_agent.tools.base import Tool, ToolResult


class FailingTool(Tool):
    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "Always fails for testing."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
            "required": ["value"],
        }

    async def execute(self, value: str) -> ToolResult:
        return ToolResult(success=False, error=f"boom: {value}")


@pytest.mark.asyncio
async def test_before_run_creates_learning_files_and_injects_reminder(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[
            Message(role="system", content="base system prompt"),
            Message(role="user", content="帮我调试这个错误"),
        ]
    )

    await hook.before_run(HookContext(state=state))

    learnings_dir = tmp_path / ".learnings"
    assert learnings_dir.exists()
    assert (learnings_dir / "LEARNINGS.md").exists()
    assert (learnings_dir / "ERRORS.md").exists()
    assert (learnings_dir / "FEATURE_REQUESTS.md").exists()
    assert any(
        isinstance(msg.content, str) and REMINDER_SENTINEL in msg.content for msg in state.messages
    )


@pytest.mark.asyncio
async def test_on_step_logs_tool_error_once(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[
            Message(role="system", content="base system prompt"),
            Message(role="user", content="运行命令并修复问题"),
        ]
    )
    ctx = HookContext(state=state, step=1)

    await hook.before_run(ctx)

    state.messages.append(
        Message(
            role="tool",
            content="Error: command not found",
            tool_call_id="tc_1",
            name="bash",
        )
    )
    await hook.on_step(ctx, {"completed": False, "content": "", "error": None})
    await hook.on_step(ctx, {"completed": False, "content": "", "error": None})

    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "工具 `bash` 执行失败" in content
    assert content.count("command not found") == 1


@pytest.mark.asyncio
async def test_after_run_logs_terminal_failure(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[Message(role="system", content="base"), Message(role="user", content="任务")]
    )
    ctx = HookContext(state=state, step=3)

    await hook.before_run(ctx)
    await hook.after_run(ctx, "Task couldn't be completed after 3 steps.", False)

    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "Agent 运行未正常完成" in content
    assert "Task couldn't be completed after 3 steps." in content


@pytest.mark.asyncio
async def test_after_run_skips_cancellation(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[Message(role="system", content="base"), Message(role="user", content="任务")]
    )
    ctx = HookContext(state=state, step=2)

    await hook.before_run(ctx)
    await hook.after_run(ctx, "Task cancelled by user", False)

    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "Agent 运行未正常完成" not in content


@pytest.mark.asyncio
async def test_after_run_skips_success(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[Message(role="system", content="base"), Message(role="user", content="任务")]
    )
    ctx = HookContext(state=state, step=2)

    await hook.before_run(ctx)
    await hook.after_run(ctx, "任务完成", True)

    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "Agent 运行未正常完成" not in content


@pytest.mark.asyncio
async def test_on_step_logs_step_error(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[Message(role="system", content="base"), Message(role="user", content="任务")]
    )
    ctx = HookContext(state=state, step=1)

    await hook.before_run(ctx)
    await hook.on_step(
        ctx, {"completed": False, "content": "", "error": "LLM call failed: timeout"}
    )

    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "Agent 单步执行失败" in content
    assert "LLM call failed: timeout" in content


@pytest.mark.asyncio
async def test_reminder_not_injected_twice_across_runs(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[
            Message(role="system", content="base system prompt"),
            Message(role="user", content="任务"),
        ]
    )
    ctx = HookContext(state=state)

    await hook.before_run(ctx)
    await hook.before_run(ctx)

    sentinel_count = sum(
        1
        for msg in state.messages
        if isinstance(msg.content, str) and REMINDER_SENTINEL in msg.content
    )
    assert sentinel_count == 1


@pytest.mark.asyncio
async def test_record_correction_writes_to_learnings(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    hook.record_correction(feedback_type="reject", reason="输出格式错误", task="生成报告")

    content = (tmp_path / ".learnings" / "LEARNINGS.md").read_text(encoding="utf-8")
    assert "收到用户反馈：输出格式错误" in content
    assert "Feedback Type: `reject`" in content
    assert "Task: 生成报告" in content


@pytest.mark.asyncio
async def test_on_feedback_delegates_to_record_correction(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[
            Message(role="system", content="base"),
            Message(role="user", content="帮我生成报告"),
        ]
    )
    ctx = HookContext(state=state)
    await hook.before_run(ctx)
    await hook.on_feedback(ctx, "edit", {"reason": "格式不对"})

    content = (tmp_path / ".learnings" / "LEARNINGS.md").read_text(encoding="utf-8")
    assert "收到用户反馈：格式不对" in content


@pytest.mark.asyncio
async def test_on_feedback_deduplicates_within_run(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(messages=[Message(role="user", content="任务")])
    ctx = HookContext(state=state)
    await hook.before_run(ctx)

    await hook.on_feedback(ctx, "reject", {"reason": "答案错误"})
    await hook.on_feedback(ctx, "reject", {"reason": "答案错误"})

    content = (tmp_path / ".learnings" / "LEARNINGS.md").read_text(encoding="utf-8")
    assert content.count("答案错误") == 1


@pytest.mark.asyncio
async def test_on_feedback_skips_unknown_type(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(messages=[Message(role="user", content="任务")])
    ctx = HookContext(state=state)
    await hook.before_run(ctx)

    await hook.on_feedback(ctx, "approve", {"reason": "好的"})

    content = (tmp_path / ".learnings" / "LEARNINGS.md").read_text(encoding="utf-8")
    assert "好的" not in content


@pytest.mark.asyncio
async def test_record_feature_request(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    hook.record_feature_request(capability="支持导出 PDF 格式")

    content = (tmp_path / ".learnings" / "FEATURE_REQUESTS.md").read_text(encoding="utf-8")
    assert "支持导出 PDF 格式" in content
    assert "Frequency: first_time" in content


@pytest.mark.asyncio
async def test_on_feedback_feature_request(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(messages=[Message(role="user", content="能不能帮我导出 PDF")])
    ctx = HookContext(state=state)
    await hook.before_run(ctx)

    await hook.on_feedback(ctx, "feature_request", {"capability": "导出 PDF"})

    content = (tmp_path / ".learnings" / "FEATURE_REQUESTS.md").read_text(encoding="utf-8")
    assert "导出 PDF" in content


@pytest.mark.asyncio
async def test_record_learning_with_pattern_key(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    hook.record_learning(
        category="best_practice",
        summary="使用 uv 代替 pip 安装依赖",
        details="pip 在 CI 中经常因为缓存问题失败",
        suggested_action="项目中统一使用 uv",
        pattern_key="tooling.package_manager",
    )

    content = (tmp_path / ".learnings" / "LEARNINGS.md").read_text(encoding="utf-8")
    assert "best_practice" in content
    assert "使用 uv 代替 pip 安装依赖" in content
    assert "Pattern-Key: tooling.package_manager" in content


@pytest.mark.asyncio
async def test_recurring_tool_error_bumps_priority(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(
        messages=[
            Message(role="system", content="base"),
            Message(role="user", content="任务"),
        ]
    )
    ctx = HookContext(state=state, step=1)
    await hook.before_run(ctx)

    for i in range(4):
        state.messages.append(
            Message(
                role="tool",
                content=f"Error: connection refused attempt {i}",
                tool_call_id=f"tc_{i}",
                name="http_request",
            )
        )
        ctx.step = i + 1
        await hook.on_step(ctx, {"completed": False, "content": "", "error": None})

    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "Pattern-Key: tool_error.http_request" in content
    assert "Priority**: high" in content
    assert "Recurrence-Count: 4" in content


@pytest.mark.asyncio
async def test_extract_latest_user_message_returns_na(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    state = AgentState(messages=[Message(role="system", content="base")])
    ctx = HookContext(state=state)

    result = hook._extract_latest_user_message(ctx)
    assert result == "N/A"


@pytest.mark.asyncio
async def test_is_feature_request_patterns():
    assert SelfImprovementHook.is_feature_request("能不能帮我生成报告")
    assert SelfImprovementHook.is_feature_request("Can you add PDF export?")
    assert SelfImprovementHook.is_feature_request("I wish this could handle images")
    assert not SelfImprovementHook.is_feature_request("帮我修复这个 bug")
    assert not SelfImprovementHook.is_feature_request("Fix the typo in README")


@pytest.mark.asyncio
async def test_entry_id_has_six_hex_chars(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    entry_id = hook._build_entry_id("LRN")
    suffix = entry_id.split("-")[-1]
    assert len(suffix) == 6
    assert all(c in "0123456789ABCDEF" for c in suffix)


@pytest.mark.asyncio
async def test_agent_integration_logs_failed_tool_to_learnings(tmp_path):
    llm_client = AsyncMock()
    llm_client.generate = AsyncMock(
        side_effect=[
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        function=FunctionCall(
                            name="failing_tool",
                            arguments={"value": "demo"},
                        ),
                    )
                ],
            ),
            LLMResponse(content="done"),
        ]
    )

    agent = Agent(
        llm_client=llm_client,
        system_prompt="test prompt",
        tools=[FailingTool()],
        workspace_dir=str(tmp_path),
        enable_logging=False,
        enable_self_improvement=True,
    )
    agent.add_user_message("请运行测试工具")

    result, _ = await agent.run()

    assert result == "done"
    content = (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")
    assert "工具 `failing_tool` 执行失败" in content
    assert "boom: demo" in content
