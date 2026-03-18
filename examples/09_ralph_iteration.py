"""
Ralph 迭代模式示例

展示如何使用 Ralph Loop 进行迭代开发。
Ralph 通过重复执行相同的 prompt，让 AI 看到自己之前的工作并逐步改进。

核心特性:
- 多轮迭代执行
- 工具结果缓存与摘要
- 结构化工作记忆 (Working Memory)
- 多条件完成检测 (Promise/MaxIterations/Idle)
- 文件修改跟踪

运行方式:
    uv run python examples/09_ralph_iteration.py
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from omni_agent.core import Agent, LLMClient, RalphConfig, WorkspaceManager
from omni_agent.tools.bash_tool import BashTool
from omni_agent.tools.file_tools import EditTool, ReadTool, WriteTool


async def main():
    llm_client = LLMClient(
        api_key="api_key",
        model="deepseek/deepseek-chat",
    )

    session_id = f"ralph_{uuid4().hex[:8]}"

    workspace_manager = WorkspaceManager(base_dir="./workspace")
    workspace_path = workspace_manager.get_session_workspace(session_id)

    print(f"Session ID: {session_id}")
    print(f"Workspace: {workspace_path}")
    print("-" * 50)

    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        EditTool(workspace_dir=str(workspace_path)),
        BashTool(),
    ]

    ralph_config = RalphConfig(
        enabled=True,
        max_iterations=5,
        idle_threshold=2,
        completion_promise="TASK COMPLETE",
    )

    agent = Agent(
        llm_client=llm_client,
        system_prompt="你是一个专业的 Python 开发者，擅长编写高质量代码和测试。",
        tools=tools,
        ralph=ralph_config,
        max_steps=10,
        workspace_dir=str(workspace_path),
    )

    task = """创建一个 Python 计算器模块:

1. 创建 calc.py，包含 add, subtract, multiply, divide 四个函数
2. 创建 test_calc.py，使用 unittest 测试这四个函数
3. 运行测试确保全部通过
4. 完成后输出 <promise>TASK COMPLETE</promise>"""

    print(f"任务: {task[:100]}...")
    print("-" * 50)

    result, logs = await agent.run(task)

    print(f"\n结果:\n{result[:500]}")
    print(f"\n执行日志数: {len(logs)}")

    status = agent.get_ralph_status()
    if status:
        print("\n--- Ralph 状态 ---")
        print(f"迭代次数: {status['state']['iteration']}")
        print(f"是否完成: {status['state']['completed']}")
        print(f"完成原因: {status['state']['completion_reason']}")
        print(f"修改文件数: {status['memory_summary']['files_modified_count']}")
        if status["memory_summary"]["recent_progress"]:
            print(f"进度记录: {status['memory_summary']['recent_progress']}")

    print("\n--- 生成的文件 ---")
    for f in workspace_path.iterdir():
        if f.is_file() and f.suffix == ".py":
            print(f"\n[{f.name}]")
            content = f.read_text()
            print(content[:300] if len(content) > 300 else content)

    print(f"\n文件已保存在: {workspace_path}")


if __name__ == "__main__":
    asyncio.run(main())
