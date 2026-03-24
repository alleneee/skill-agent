"""Self-improvement hook integration tests.

Tests the full SelfImprovementHook lifecycle within a real Agent run,
using AsyncMock for LLM but exercising the actual hook machinery.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from omni_agent.core import Agent
from omni_agent.core.self_improvement_hook import REMINDER_SENTINEL, SelfImprovementHook
from omni_agent.schemas.message import FunctionCall, LLMResponse, ToolCall
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
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    async def execute(self, value: str) -> ToolResult:
        return ToolResult(success=False, error=f"boom: {value}")


def _make_tool_call_response(tool_name: str, args: dict, call_id: str) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            ToolCall(
                id=call_id,
                function=FunctionCall(name=tool_name, arguments=args),
            )
        ],
    )


def _make_final_response(text: str = "done") -> LLMResponse:
    return LLMResponse(content=text)


def _build_agent(tmp_path, llm_client, tools=None, max_steps=10):
    return Agent(
        llm_client=llm_client,
        system_prompt="test prompt",
        tools=tools or [],
        workspace_dir=str(tmp_path),
        enable_logging=False,
        enable_self_improvement=True,
        max_steps=max_steps,
    )


def _errors_md(tmp_path) -> str:
    return (tmp_path / ".learnings" / "ERRORS.md").read_text(encoding="utf-8")


def _learnings_md(tmp_path) -> str:
    return (tmp_path / ".learnings" / "LEARNINGS.md").read_text(encoding="utf-8")


def _features_md(tmp_path) -> str:
    return (tmp_path / ".learnings" / "FEATURE_REQUESTS.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_scenario_a_tool_failure_auto_logged(tmp_path):
    llm = AsyncMock()
    llm.generate = AsyncMock(
        side_effect=[
            _make_tool_call_response("failing_tool", {"value": "x"}, "tc_a1"),
            _make_final_response(),
        ]
    )

    agent = _build_agent(tmp_path, llm, tools=[FailingTool()])
    agent.add_user_message("run failing tool")
    result, _ = await agent.run()

    assert result == "done"
    content = _errors_md(tmp_path)
    assert "failing_tool" in content
    assert "boom: x" in content
    assert "Pattern-Key: tool_error.failing_tool" in content
    assert "Recurrence-Count: 1" in content


@pytest.mark.asyncio
async def test_scenario_b_recurring_failures_bump_priority(tmp_path):
    llm = AsyncMock()
    responses = []
    for i in range(4):
        responses.append(_make_tool_call_response("failing_tool", {"value": f"v{i}"}, f"tc_b{i}"))
    responses.append(_make_final_response())
    llm.generate = AsyncMock(side_effect=responses)

    agent = _build_agent(tmp_path, llm, tools=[FailingTool()])
    agent.add_user_message("keep trying")
    result, _ = await agent.run()

    assert result == "done"
    content = _errors_md(tmp_path)
    assert "Priority**: high" in content
    assert "Recurrence-Count: 4" in content


@pytest.mark.asyncio
async def test_scenario_c_agent_max_steps_failure(tmp_path):
    llm = AsyncMock()
    llm.generate = AsyncMock(
        side_effect=[
            _make_tool_call_response("failing_tool", {"value": "loop"}, f"tc_c{i}")
            for i in range(5)
        ]
    )

    agent = _build_agent(tmp_path, llm, tools=[FailingTool()], max_steps=3)
    agent.add_user_message("do something")
    result, _ = await agent.run()

    assert "couldn't be completed" in result.lower() or "3 steps" in result
    content = _errors_md(tmp_path)
    assert "Agent 运行未正常完成" in content


@pytest.mark.asyncio
async def test_scenario_d_reminder_injection(tmp_path):
    llm = AsyncMock()
    llm.generate = AsyncMock(side_effect=[_make_final_response("first run done")])

    agent = _build_agent(tmp_path, llm)
    agent.add_user_message("hello")
    await agent.run()

    sentinel_count = sum(
        1
        for msg in agent._state.messages
        if isinstance(msg.content, str) and REMINDER_SENTINEL in msg.content
    )
    assert sentinel_count == 1

    llm.generate = AsyncMock(side_effect=[_make_final_response("second run done")])
    agent.add_user_message("hello again")
    await agent.run()

    sentinel_count_after = sum(
        1
        for msg in agent._state.messages
        if isinstance(msg.content, str) and REMINDER_SENTINEL in msg.content
    )
    assert sentinel_count_after == 1


@pytest.mark.asyncio
async def test_scenario_e_record_learning_and_feature_request(tmp_path):
    hook = SelfImprovementHook(str(tmp_path))
    hook._ensure_learning_files()

    hook.record_learning(
        category="best_practice",
        summary="Always use uv",
        details="pip fails in CI",
        pattern_key="tooling.pkg",
    )
    content = _learnings_md(tmp_path)
    assert "Always use uv" in content
    assert "Pattern-Key: tooling.pkg" in content

    hook.record_feature_request(capability="Export to PDF")
    content = _features_md(tmp_path)
    assert "Export to PDF" in content


@pytest.mark.asyncio
async def test_scenario_f_is_feature_request():
    assert SelfImprovementHook.is_feature_request("能不能帮我生成报告")
    assert SelfImprovementHook.is_feature_request("有没有办法导出 PDF")
    assert SelfImprovementHook.is_feature_request("Can you add PDF export?")
    assert SelfImprovementHook.is_feature_request("I wish this could handle images")

    assert not SelfImprovementHook.is_feature_request("帮我修复 bug")
    assert not SelfImprovementHook.is_feature_request("Fix the typo")


@pytest.mark.asyncio
async def test_scenario_g_all_files_created_and_feature_format(tmp_path):
    llm = AsyncMock()
    llm.generate = AsyncMock(side_effect=[_make_final_response()])

    agent = _build_agent(tmp_path, llm)
    agent.add_user_message("init")
    await agent.run()

    learnings_dir = tmp_path / ".learnings"
    assert (learnings_dir / "LEARNINGS.md").exists()
    assert (learnings_dir / "ERRORS.md").exists()
    assert (learnings_dir / "FEATURE_REQUESTS.md").exists()

    hook = agent._self_improvement_hook
    assert hook is not None
    hook.record_feature_request(capability="Batch processing support")

    content = _features_md(tmp_path)
    assert "Batch processing support" in content
    assert "Requested Capability" in content
    assert "Status**: pending" in content
