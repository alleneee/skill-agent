"""Real task integration test for SpawnAgentTool.

Task: Multi-perspective code quality analysis
- Security Auditor: Check for security issues
- Code Reviewer: Check code style and best practices
- Main Agent: Synthesize findings into a report

Run with: uv run python tests/integration/test_real_task.py
"""

import asyncio
import sys
from pathlib import Path

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.config import settings
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.tools.file_tools import ReadTool
from fastapi_agent.tools.spawn_agent_tool import SpawnAgentTool


SYSTEM_PROMPT = """你是一个代码质量分析协调员。

当用户要求分析代码时，你应该：
1. 使用 spawn_agent 工具创建专门的子Agent来分析不同方面
2. 每个子Agent专注于一个分析角度
3. 收集所有子Agent的分析结果
4. 综合生成最终的代码质量报告

可用的分析角色：
- security_auditor: 安全审计员，检查安全漏洞
- code_reviewer: 代码评审员，检查代码风格和最佳实践

重要：你必须使用 spawn_agent 来委派分析任务，不要自己直接分析代码。"""


async def run_real_task():
    """Run real code analysis task."""
    print("=" * 70)
    print("Real Task: Multi-perspective Code Quality Analysis")
    print("=" * 70)

    if not settings.LLM_API_KEY:
        print("ERROR: LLM_API_KEY not set")
        return False

    # Target file to analyze
    target_file = Path(__file__).parent.parent.parent / "src/fastapi_agent/tools/spawn_agent_tool.py"
    if not target_file.exists():
        print(f"ERROR: Target file not found: {target_file}")
        return False

    print(f"\nTarget file: {target_file}")
    print(f"File size: {target_file.stat().st_size} bytes")

    # Create LLM client
    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    # Create tools
    workspace_dir = str(target_file.parent.parent.parent.parent)
    read_tool = ReadTool(workspace_dir=workspace_dir)

    parent_tools = {"read_file": read_tool}

    spawn_tool = SpawnAgentTool(
        llm_client=llm_client,
        parent_tools=parent_tools,
        workspace_dir=workspace_dir,
        current_depth=0,
        max_depth=2,
        default_max_steps=10,
        default_token_limit=50000,
    )

    # Create main agent
    agent = Agent(
        llm_client=llm_client,
        system_prompt=SYSTEM_PROMPT,
        tools=[read_tool, spawn_tool],
        max_steps=15,
        workspace_dir=workspace_dir,
        enable_logging=True,
    )

    # The task
    task = f"""请分析这个Python文件的代码质量：
{target_file}

要求：
1. 派遣一个 security_auditor 角色的子Agent检查安全问题
2. 派遣一个 code_reviewer 角色的子Agent检查代码风格
3. 综合两个子Agent的分析结果，生成一份简洁的代码质量报告

注意：每个子Agent需要先用 read_file 工具读取文件内容，然后进行分析。"""

    print(f"\n{'=' * 70}")
    print("Task:")
    print(task)
    print("=" * 70)

    agent.add_user_message(task)

    print("\nExecuting...")
    print("-" * 70)

    result, logs = await agent.run()

    # Analyze execution
    print("\n" + "=" * 70)
    print("Execution Analysis")
    print("=" * 70)

    steps = [l for l in logs if l.get("type") == "step"]
    tool_calls = [l for l in logs if l.get("type") == "tool_call"]
    spawn_calls = [l for l in tool_calls if l.get("tool") == "spawn_agent"]
    read_calls = [l for l in tool_calls if l.get("tool") == "read_file"]

    print(f"Total steps: {len(steps)}")
    print(f"Tool calls: {len(tool_calls)}")
    print(f"  - spawn_agent: {len(spawn_calls)}")
    print(f"  - read_file: {len(read_calls)}")

    # Show spawn_agent calls details
    if spawn_calls:
        print("\nSpawn Agent Calls:")
        for i, call in enumerate(spawn_calls, 1):
            args = call.get("arguments", {})
            print(f"  {i}. Role: {args.get('role', 'N/A')}")
            print(f"     Task: {args.get('task', 'N/A')[:80]}...")

    print("\n" + "=" * 70)
    print("Final Report")
    print("=" * 70)
    print(result)

    # Determine success
    success = len(spawn_calls) >= 2
    if success:
        print("\n" + "=" * 70)
        print("✅ SUCCESS: Agent correctly used spawn_agent for multi-perspective analysis")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print(f"⚠️  Agent used {len(spawn_calls)} spawn_agent calls (expected >= 2)")
        print("=" * 70)

    return success


async def run_simple_task():
    """Run a simpler single-spawn task for quick validation."""
    print("=" * 70)
    print("Simple Task: Single Sub-Agent Code Analysis")
    print("=" * 70)

    if not settings.LLM_API_KEY:
        print("ERROR: LLM_API_KEY not set")
        return False

    target_file = Path(__file__).parent.parent.parent / "src/fastapi_agent/tools/base.py"

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    workspace_dir = str(target_file.parent.parent.parent.parent)
    read_tool = ReadTool(workspace_dir=workspace_dir)

    spawn_tool = SpawnAgentTool(
        llm_client=llm_client,
        parent_tools={"read_file": read_tool},
        workspace_dir=workspace_dir,
        current_depth=0,
        max_depth=2,
        default_max_steps=8,
    )

    agent = Agent(
        llm_client=llm_client,
        system_prompt="""你是一个代码分析协调员。
当需要分析代码时，使用 spawn_agent 工具创建子Agent来完成分析。
不要自己直接分析，必须委派给子Agent。""",
        tools=[read_tool, spawn_tool],
        max_steps=10,
        workspace_dir=workspace_dir,
        enable_logging=True,
    )

    task = f"请派遣一个 code_analyst 角色的子Agent来分析 {target_file} 文件，总结这个文件定义了什么类和方法。"

    print(f"\nTask: {task}")
    print("-" * 70)

    agent.add_user_message(task)
    result, logs = await agent.run()

    spawn_calls = [l for l in logs if l.get("type") == "tool_call" and l.get("tool") == "spawn_agent"]

    print(f"\nSpawn calls: {len(spawn_calls)}")
    print(f"\nResult:\n{result[:500]}...")

    success = len(spawn_calls) >= 1
    print(f"\n{'✅ SUCCESS' if success else '❌ FAILED'}")
    return success


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--simple", action="store_true", help="Run simple single-spawn test")
    args = parser.parse_args()

    if args.simple:
        success = asyncio.run(run_simple_task())
    else:
        success = asyncio.run(run_real_task())

    sys.exit(0 if success else 1)
