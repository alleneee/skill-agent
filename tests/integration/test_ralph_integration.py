"""Ralph 集成测试 - 使用真实 LLM."""

import asyncio
import tempfile
from pathlib import Path

from omni_agent.core import Agent, LLMClient, RalphConfig
from omni_agent.core.config import Settings
from omni_agent.tools.bash_tool import BashTool
from omni_agent.tools.file_tools import EditTool, ReadTool, WriteTool


async def test_ralph_complex_task():
    settings = Settings()

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        tools = [
            ReadTool(str(workspace)),
            WriteTool(str(workspace)),
            EditTool(str(workspace)),
            BashTool(),
        ]

        ralph_config = RalphConfig(
            enabled=True,
            max_iterations=5,
            idle_threshold=2,
        )

        agent = Agent(
            llm_client=llm_client,
            tools=tools,
            ralph=ralph_config,
            workspace_dir=str(workspace),
            max_steps=10,
            enable_logging=False,
        )

        task = """创建一个 Python 计算器模块:

1. 创建 calc.py，包含 add, subtract, multiply, divide 四个函数
2. 创建 test_calc.py，测试这四个函数
3. 运行测试确保通过
4. 完成后输出 <promise>TASK COMPLETE</promise>"""

        print(f"Model: {settings.LLM_MODEL}")
        print(f"Task: {task[:100]}...")
        print(f"Workspace: {workspace}")
        print("-" * 50)

        result, logs = await agent.run(task)

        print(f"\nResult:\n{result[:800]}")
        print(f"\nLogs count: {len(logs)}")

        status = agent.get_ralph_status()
        if status:
            print("\n--- Ralph Status ---")
            print(f"Iterations: {status['state']['iteration']}")
            print(f"Completed: {status['state']['completed']}")
            print(f"Reason: {status['state']['completion_reason']}")
            print(f"Files modified: {status['memory_summary']['files_modified_count']}")
            print(f"Progress: {status['memory_summary']['recent_progress']}")

        print("\n--- Created Files ---")
        for f in workspace.iterdir():
            if f.is_file():
                print(f"\n[{f.name}]")
                content = f.read_text()
                print(content[:500] if len(content) > 500 else content)

        return result, logs


if __name__ == "__main__":
    asyncio.run(test_ralph_complex_task())
