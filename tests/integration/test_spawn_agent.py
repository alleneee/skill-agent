"""Integration tests for SpawnAgentTool functionality."""

import asyncio
import os
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    class pytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.config import settings
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.message import AgentConfig, LLMResponse, ToolCall, FunctionCall
from fastapi_agent.tools.base import Tool, ToolResult
from fastapi_agent.tools.spawn_agent_tool import SpawnAgentTool
from fastapi_agent.tools.file_tools import ReadTool
from fastapi_agent.api.deps import AgentFactory


class MockReadTool(Tool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read file content"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"Content of {path}: mock file content")


class MockWriteTool(Tool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write file content"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"Written to {path}")


def create_mock_llm_client(responses: List[LLMResponse] = None):
    """Create a mock LLM client with predefined responses."""
    mock_client = MagicMock(spec=LLMClient)

    if responses is None:
        responses = [
            LLMResponse(content="Task completed successfully.", tool_calls=None)
        ]

    response_iter = iter(responses)

    async def mock_generate(*args, **kwargs):
        try:
            return next(response_iter)
        except StopIteration:
            return LLMResponse(content="No more responses", tool_calls=None)

    mock_client.generate = mock_generate
    return mock_client


class TestSpawnAgentToolBasic:
    """Basic SpawnAgentTool tests."""

    def test_tool_properties(self):
        """Test SpawnAgentTool has correct properties."""
        mock_llm = MagicMock()
        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        assert tool.name == "spawn_agent"
        assert "spawn" in tool.description.lower()
        assert "task" in tool.parameters["properties"]
        assert "role" in tool.parameters["properties"]
        assert "context" in tool.parameters["properties"]
        assert "tools" in tool.parameters["properties"]
        assert "max_steps" in tool.parameters["properties"]
        assert tool.add_instructions_to_prompt is True
        assert tool.instructions is not None

    def test_depth_tracking(self):
        """Test depth is correctly tracked."""
        mock_llm = MagicMock()

        tool_d0 = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )
        assert tool_d0._current_depth == 0
        assert "0/3" in tool_d0.description

        tool_d2 = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=2,
            max_depth=3
        )
        assert tool_d2._current_depth == 2
        assert "2/3" in tool_d2.description


class TestSpawnAgentToolDepthLimit:
    """Test recursive depth limiting."""

    @pytest.mark.asyncio
    async def test_depth_limit_blocks_spawn(self):
        """Test that spawning is blocked at max depth."""
        mock_llm = MagicMock()

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=3,
            max_depth=3
        )

        result = await tool.execute(task="test task")

        assert result.success is False
        assert "Maximum agent nesting depth" in result.error
        assert "(3)" in result.error

    @pytest.mark.asyncio
    async def test_depth_limit_allows_spawn_below_max(self):
        """Test that spawning is allowed below max depth."""
        responses = [
            LLMResponse(content="Sub-agent completed the task.", tool_calls=None)
        ]
        mock_llm = create_mock_llm_client(responses)

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={"read_file": MockReadTool()},
            workspace_dir="/tmp/test",
            current_depth=1,
            max_depth=3
        )

        result = await tool.execute(task="test task", role="tester")

        assert result.success is True
        assert "Sub-Agent Execution Result" in result.content


class TestSpawnAgentToolInheritance:
    """Test tool inheritance behavior."""

    def test_inherit_all_tools(self):
        """Test that sub-agent inherits all parent tools by default."""
        mock_llm = MagicMock()
        parent_tools = {
            "read_file": MockReadTool(),
            "write_file": MockWriteTool(),
        }

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools=parent_tools,
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        sub_tools = tool._build_sub_agent_tools(None)
        sub_tool_names = [t.name for t in sub_tools]

        assert "read_file" in sub_tool_names
        assert "write_file" in sub_tool_names

    def test_filter_specific_tools(self):
        """Test filtering to specific tools."""
        mock_llm = MagicMock()
        parent_tools = {
            "read_file": MockReadTool(),
            "write_file": MockWriteTool(),
        }

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools=parent_tools,
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        sub_tools = tool._build_sub_agent_tools(["read_file"])
        sub_tool_names = [t.name for t in sub_tools]

        assert "read_file" in sub_tool_names
        assert "write_file" not in sub_tool_names

    def test_spawn_agent_depth_increment(self):
        """Test that inherited spawn_agent has incremented depth."""
        mock_llm = MagicMock()

        parent_spawn = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        parent_tools = {
            "spawn_agent": parent_spawn,
            "read_file": MockReadTool(),
        }

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools=parent_tools,
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        sub_tools = tool._build_sub_agent_tools(None)
        spawn_tools = [t for t in sub_tools if t.name == "spawn_agent"]

        assert len(spawn_tools) == 1
        assert spawn_tools[0]._current_depth == 1

    def test_spawn_agent_excluded_at_max_depth(self):
        """Test that spawn_agent is excluded when at max depth - 1."""
        mock_llm = MagicMock()

        parent_spawn = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        parent_tools = {
            "spawn_agent": parent_spawn,
            "read_file": MockReadTool(),
        }

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools=parent_tools,
            workspace_dir="/tmp/test",
            current_depth=2,  # At depth 2, sub-agent would be depth 3 (max)
            max_depth=3
        )

        sub_tools = tool._build_sub_agent_tools(None)
        spawn_tools = [t for t in sub_tools if t.name == "spawn_agent"]

        assert len(spawn_tools) == 0  # spawn_agent should not be included


class TestSpawnAgentToolSystemPrompt:
    """Test system prompt building."""

    def test_prompt_with_role(self):
        """Test prompt includes role when specified."""
        mock_llm = MagicMock()
        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        prompt = tool._build_sub_agent_prompt(role="security auditor", context=None)

        assert "security auditor" in prompt
        assert "specialized" in prompt.lower()

    def test_prompt_with_context(self):
        """Test prompt includes context when provided."""
        mock_llm = MagicMock()
        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        context = "This is a FastAPI project using SQLAlchemy"
        prompt = tool._build_sub_agent_prompt(role=None, context=context)

        assert context in prompt
        assert "Context from Parent" in prompt

    def test_prompt_includes_workspace(self):
        """Test prompt includes workspace directory."""
        mock_llm = MagicMock()
        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/custom/workspace",
            current_depth=0,
            max_depth=3
        )

        prompt = tool._build_sub_agent_prompt(role=None, context=None)

        assert "/custom/workspace" in prompt


class TestSpawnAgentToolExecution:
    """Test actual execution flow."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful sub-agent execution."""
        responses = [
            LLMResponse(
                content="I have analyzed the code and found no security issues.",
                tool_calls=None
            )
        ]
        mock_llm = create_mock_llm_client(responses)

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={"read_file": MockReadTool()},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3,
            default_max_steps=10
        )

        result = await tool.execute(
            task="Analyze code for security issues",
            role="security auditor",
            context="Check the /src directory"
        )

        assert result.success is True
        assert "Sub-Agent Execution Result" in result.content
        assert "security auditor" in result.content
        assert "analyzed the code" in result.content

    @pytest.mark.asyncio
    async def test_execution_with_tool_usage(self):
        """Test sub-agent that uses tools."""
        responses = [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        type="function",
                        function=FunctionCall(
                            name="read_file",
                            arguments={"path": "/src/main.py"}
                        )
                    )
                ]
            ),
            LLMResponse(
                content="File analyzed. No issues found.",
                tool_calls=None
            )
        ]
        mock_llm = create_mock_llm_client(responses)

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={"read_file": MockReadTool()},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        result = await tool.execute(
            task="Read and analyze main.py",
            tools=["read_file"]
        )

        assert result.success is True
        assert "File analyzed" in result.content

    @pytest.mark.asyncio
    async def test_max_steps_respected(self):
        """Test that max_steps parameter is respected."""
        responses = [
            LLMResponse(content="Done", tool_calls=None)
        ]
        mock_llm = create_mock_llm_client(responses)

        tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3,
            default_max_steps=15
        )

        # Request 25 steps but should be capped at 30
        result = await tool.execute(task="test", max_steps=25)

        assert result.success is True
        # The result should show execution stats
        assert "steps" in result.content.lower()


class TestAgentFactoryIntegration:
    """Test integration with AgentFactory."""

    @pytest.mark.asyncio
    async def test_factory_adds_spawn_agent_tool(self):
        """Test that AgentFactory adds SpawnAgentTool when enabled."""
        factory = AgentFactory(settings)
        mock_llm = MagicMock(spec=LLMClient)

        config = AgentConfig(
            enable_spawn_agent=True,
            enable_base_tools=True,
            enable_mcp_tools=False,
            enable_skills=False,
            enable_rag=False,
            base_tools_filter=["read_file"]
        )

        agent = await factory.create_agent(mock_llm, config)

        tool_names = list(agent.tools.keys())
        assert "spawn_agent" in tool_names

    @pytest.mark.asyncio
    async def test_factory_respects_disable_spawn_agent(self):
        """Test that SpawnAgentTool is not added when disabled."""
        factory = AgentFactory(settings)
        mock_llm = MagicMock(spec=LLMClient)

        config = AgentConfig(
            enable_spawn_agent=False,
            enable_base_tools=True,
            enable_mcp_tools=False,
            enable_skills=False,
            enable_rag=False,
            base_tools_filter=["read_file"]
        )

        agent = await factory.create_agent(mock_llm, config)

        tool_names = list(agent.tools.keys())
        assert "spawn_agent" not in tool_names

    @pytest.mark.asyncio
    async def test_factory_respects_max_depth_config(self):
        """Test that AgentFactory respects spawn_agent_max_depth config."""
        factory = AgentFactory(settings)
        mock_llm = MagicMock(spec=LLMClient)

        config = AgentConfig(
            enable_spawn_agent=True,
            spawn_agent_max_depth=2,
            enable_base_tools=False,
            enable_mcp_tools=False,
            enable_skills=False,
            enable_rag=False
        )

        agent = await factory.create_agent(mock_llm, config)

        spawn_tool = agent.tools.get("spawn_agent")
        assert spawn_tool is not None
        assert spawn_tool._max_depth == 2


class TestEndToEndScenario:
    """End-to-end scenario tests."""

    @pytest.mark.asyncio
    async def test_agent_spawns_subagent(self):
        """Test complete flow: Agent decides to spawn sub-agent."""
        # Main agent decides to use spawn_agent
        main_responses = [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_spawn",
                        type="function",
                        function=FunctionCall(
                            name="spawn_agent",
                            arguments={
                                "task": "Analyze security vulnerabilities",
                                "role": "security expert",
                                "tools": ["read_file"]
                            }
                        )
                    )
                ]
            ),
            LLMResponse(
                content="Based on the security analysis, the code is secure.",
                tool_calls=None
            )
        ]

        # Sub-agent response
        sub_responses = [
            LLMResponse(
                content="Security analysis complete. No vulnerabilities found.",
                tool_calls=None
            )
        ]

        # Create mock LLM that returns different responses
        call_count = [0]
        all_responses = main_responses + sub_responses

        async def mock_generate(*args, **kwargs):
            idx = min(call_count[0], len(all_responses) - 1)
            call_count[0] += 1
            return all_responses[idx]

        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.generate = mock_generate

        # Create main agent with spawn_agent tool
        parent_tools = {"read_file": MockReadTool()}
        spawn_tool = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools=parent_tools,
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )

        all_tools = [MockReadTool(), spawn_tool]

        agent = Agent(
            llm_client=mock_llm,
            system_prompt="You are a helpful assistant.",
            tools=all_tools,
            max_steps=10,
            workspace_dir="/tmp/test",
            enable_logging=False
        )

        agent.add_user_message("Check this project for security issues")
        result, logs = await agent.run()

        # Verify the flow
        assert "secure" in result.lower() or "security" in result.lower()

        # Check that spawn_agent was called
        tool_calls = [log for log in logs if log.get("type") == "tool_call"]
        spawn_calls = [tc for tc in tool_calls if tc.get("tool") == "spawn_agent"]
        assert len(spawn_calls) > 0


def run_quick_test():
    """Run a quick sanity test."""
    print("=" * 60)
    print("SpawnAgentTool Integration Test")
    print("=" * 60)

    # Test 1: Basic properties
    print("\n[Test 1] Basic properties...")
    mock_llm = MagicMock()
    tool = SpawnAgentTool(
        llm_client=mock_llm,
        parent_tools={},
        workspace_dir="/tmp/test",
        current_depth=0,
        max_depth=3
    )
    assert tool.name == "spawn_agent"
    print("  ✅ Tool name correct")
    assert "task" in tool.parameters["properties"]
    print("  ✅ Parameters include task")

    # Test 2: Depth limit
    print("\n[Test 2] Depth limit...")

    async def test_depth():
        tool_at_max = SpawnAgentTool(
            llm_client=mock_llm,
            parent_tools={},
            workspace_dir="/tmp/test",
            current_depth=3,
            max_depth=3
        )
        result = await tool_at_max.execute(task="test")
        assert result.success is False
        assert "Maximum" in result.error
        print("  ✅ Depth limit enforced")

    asyncio.run(test_depth())

    # Test 3: Tool inheritance
    print("\n[Test 3] Tool inheritance...")
    parent_tools = {
        "read_file": MockReadTool(),
        "write_file": MockWriteTool(),
    }
    tool = SpawnAgentTool(
        llm_client=mock_llm,
        parent_tools=parent_tools,
        workspace_dir="/tmp/test",
        current_depth=0,
        max_depth=3
    )
    sub_tools = tool._build_sub_agent_tools(None)
    sub_names = [t.name for t in sub_tools]
    assert "read_file" in sub_names
    assert "write_file" in sub_names
    print("  ✅ Tools inherited correctly")

    # Test 4: AgentFactory integration
    print("\n[Test 4] AgentFactory integration...")

    async def test_factory():
        factory = AgentFactory(settings)
        mock_llm_client = MagicMock(spec=LLMClient)
        config = AgentConfig(
            enable_spawn_agent=True,
            enable_base_tools=False,
            enable_mcp_tools=False,
            enable_skills=False,
            enable_rag=False
        )
        agent = await factory.create_agent(mock_llm_client, config)
        assert "spawn_agent" in agent.tools
        print("  ✅ AgentFactory adds spawn_agent")

    asyncio.run(test_factory())

    # Test 5: Execution
    print("\n[Test 5] Sub-agent execution...")

    async def test_execution():
        responses = [
            LLMResponse(content="Task completed.", tool_calls=None)
        ]
        llm = create_mock_llm_client(responses)
        tool = SpawnAgentTool(
            llm_client=llm,
            parent_tools={"read_file": MockReadTool()},
            workspace_dir="/tmp/test",
            current_depth=0,
            max_depth=3
        )
        result = await tool.execute(task="Analyze code", role="reviewer")
        assert result.success is True
        assert "Sub-Agent Execution Result" in result.content
        print("  ✅ Sub-agent execution works")

    asyncio.run(test_execution())

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_quick_test()
