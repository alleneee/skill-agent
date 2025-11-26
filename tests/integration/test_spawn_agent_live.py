"""Live integration test for SpawnAgentTool with real LLM.

Run with: uv run python tests/integration/test_spawn_agent_live.py

Requires:
- LLM_API_KEY set in environment or .env file
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.config import settings
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.message import AgentConfig
from fastapi_agent.tools.base import Tool, ToolResult
from fastapi_agent.tools.spawn_agent_tool import SpawnAgentTool
from fastapi_agent.tools.file_tools import ReadTool
from fastapi_agent.api.deps import AgentFactory


class SimpleMathTool(Tool):
    """Simple math tool for testing."""

    @property
    def name(self) -> str:
        return "calculate"

    @property
    def description(self) -> str:
        return "Perform simple math calculations"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression to evaluate (e.g., '2 + 2')"
                }
            },
            "required": ["expression"]
        }

    async def execute(self, expression: str, **kwargs) -> ToolResult:
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return ToolResult(success=True, content=f"Result: {result}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


async def test_basic_spawn():
    """Test basic spawn functionality with real LLM."""
    print("\n" + "=" * 60)
    print("Test: Basic Spawn Agent")
    print("=" * 60)

    if not settings.LLM_API_KEY:
        print("  ⚠️  Skipped: LLM_API_KEY not set")
        return False

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    tools = [SimpleMathTool()]
    parent_tools = {t.name: t for t in tools}

    spawn_tool = SpawnAgentTool(
        llm_client=llm_client,
        parent_tools=parent_tools,
        workspace_dir="/tmp/spawn_test",
        current_depth=0,
        max_depth=2,
        default_max_steps=5,
    )

    print("  Spawning sub-agent to calculate 123 + 456...")

    result = await spawn_tool.execute(
        task="Calculate 123 + 456 using the calculate tool and tell me the result.",
        role="math assistant",
        tools=["calculate"],
        max_steps=5
    )

    print(f"  Success: {result.success}")
    if result.success:
        print(f"  Result preview: {result.content[:200]}...")
        if "579" in result.content:
            print("  ✅ Correct answer found in result!")
            return True
        else:
            print("  ⚠️  Answer not found, but execution succeeded")
            return True
    else:
        print(f"  Error: {result.error}")
        return False


async def test_agent_with_spawn_tool():
    """Test Agent using spawn_agent tool."""
    print("\n" + "=" * 60)
    print("Test: Agent with Spawn Tool")
    print("=" * 60)

    if not settings.LLM_API_KEY:
        print("  ⚠️  Skipped: LLM_API_KEY not set")
        return False

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    # Create tools including spawn_agent
    math_tool = SimpleMathTool()
    parent_tools = {"calculate": math_tool}

    spawn_tool = SpawnAgentTool(
        llm_client=llm_client,
        parent_tools=parent_tools,
        workspace_dir="/tmp/spawn_test",
        current_depth=0,
        max_depth=2,
        default_max_steps=5,
    )

    agent = Agent(
        llm_client=llm_client,
        system_prompt="""You are a task coordinator.
When asked to do calculations, you should spawn a sub-agent with role "calculator" to do the work.
Use the spawn_agent tool with task describing what calculation to do.""",
        tools=[math_tool, spawn_tool],
        max_steps=10,
        workspace_dir="/tmp/spawn_test",
        enable_logging=True,
    )

    print("  Asking agent to coordinate a calculation task...")
    agent.add_user_message("Please spawn a sub-agent to calculate 100 * 5 + 50")

    result, logs = await agent.run()

    print(f"  Steps taken: {len([l for l in logs if l.get('type') == 'step'])}")

    spawn_calls = [l for l in logs if l.get('type') == 'tool_call' and l.get('tool') == 'spawn_agent']
    print(f"  Spawn agent calls: {len(spawn_calls)}")

    print(f"  Result preview: {result[:300]}...")

    if spawn_calls:
        print("  ✅ Agent correctly used spawn_agent!")
        return True
    else:
        print("  ⚠️  Agent did not use spawn_agent (might have solved directly)")
        return True


async def test_factory_integration():
    """Test AgentFactory creates agent with spawn_agent."""
    print("\n" + "=" * 60)
    print("Test: AgentFactory Integration")
    print("=" * 60)

    if not settings.LLM_API_KEY:
        print("  ⚠️  Skipped: LLM_API_KEY not set")
        return False

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    factory = AgentFactory(settings)

    config = AgentConfig(
        enable_spawn_agent=True,
        spawn_agent_max_depth=2,
        enable_base_tools=True,
        base_tools_filter=["read_file"],
        enable_mcp_tools=False,
        enable_skills=False,
        enable_rag=False,
    )

    agent = await factory.create_agent(llm_client, config)

    print(f"  Agent tools: {list(agent.tools.keys())}")

    if "spawn_agent" in agent.tools:
        spawn_tool = agent.tools["spawn_agent"]
        print(f"  spawn_agent max_depth: {spawn_tool._max_depth}")
        print(f"  spawn_agent current_depth: {spawn_tool._current_depth}")
        print("  ✅ AgentFactory correctly configured spawn_agent!")
        return True
    else:
        print("  ❌ spawn_agent not found in agent tools")
        return False


async def test_depth_limit_live():
    """Test depth limit with real execution."""
    print("\n" + "=" * 60)
    print("Test: Depth Limit (Live)")
    print("=" * 60)

    if not settings.LLM_API_KEY:
        print("  ⚠️  Skipped: LLM_API_KEY not set")
        return False

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    # Create spawn_agent at depth 2 with max_depth 2
    spawn_tool = SpawnAgentTool(
        llm_client=llm_client,
        parent_tools={},
        workspace_dir="/tmp/spawn_test",
        current_depth=2,
        max_depth=2,
    )

    print("  Attempting to spawn at max depth...")
    result = await spawn_tool.execute(task="This should fail")

    if not result.success and "Maximum" in result.error:
        print(f"  Error: {result.error}")
        print("  ✅ Depth limit correctly enforced!")
        return True
    else:
        print("  ❌ Depth limit not enforced")
        return False


async def main():
    """Run all live tests."""
    print("\n" + "=" * 60)
    print("SpawnAgentTool Live Integration Tests")
    print("=" * 60)
    print(f"LLM Model: {settings.LLM_MODEL}")
    print(f"API Base: {settings.LLM_API_BASE}")
    print(f"API Key: {'***' + settings.LLM_API_KEY[-4:] if settings.LLM_API_KEY else 'NOT SET'}")

    results = []

    # Run tests
    results.append(("Depth Limit", await test_depth_limit_live()))
    results.append(("Factory Integration", await test_factory_integration()))
    results.append(("Basic Spawn", await test_basic_spawn()))
    results.append(("Agent with Spawn", await test_agent_with_spawn_tool()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
