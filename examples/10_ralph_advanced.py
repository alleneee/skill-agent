"""
Ralph 高级用法示例

展示 Ralph 的高级特性:
- 自定义完成条件
- 工作记忆查询
- 流式执行
- 状态重置与复用

运行方式:
    uv run python examples/10_ralph_advanced.py
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from omni_agent.core import Agent, LLMClient, RalphConfig, WorkspaceManager
from omni_agent.core.ralph import CompletionCondition, ContextStrategy
from omni_agent.tools.bash_tool import BashTool
from omni_agent.tools.file_tools import EditTool, ReadTool, WriteTool


async def example_custom_config():
    """自定义 Ralph 配置"""
    print("\n=== 示例 1: 自定义配置 ===\n")

    llm_client = LLMClient(
        api_key="api_key",
        model="deepseek/deepseek-chat",
    )

    session_id = f"ralph_adv_{uuid4().hex[:8]}"
    workspace_manager = WorkspaceManager(base_dir="./workspace")
    workspace_path = workspace_manager.get_session_workspace(session_id)

    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        EditTool(workspace_dir=str(workspace_path)),
        BashTool(),
    ]

    ralph_config = RalphConfig(
        enabled=True,
        max_iterations=10,
        idle_threshold=3,
        completion_promise="DONE",
        context_strategy=ContextStrategy.ALL,
        completion_conditions=[
            CompletionCondition.PROMISE_TAG,
            CompletionCondition.IDLE_THRESHOLD,
        ],
        memory_dir=".ralph_custom",
        summarize_token_threshold=30000,
    )

    agent = Agent(
        llm_client=llm_client,
        tools=tools,
        ralph=ralph_config,
        max_steps=15,
        workspace_dir=str(workspace_path),
    )

    task = """创建一个简单的 TODO 应用:

1. 创建 todo.py，包含 TodoList 类（add, remove, list, complete 方法）
2. 创建 main.py，演示 TodoList 的使用
3. 运行 main.py 验证功能
4. 完成后输出 <promise>DONE</promise>"""

    await agent.run(task)

    status = agent.get_ralph_status()
    if status:
        print(f"完成原因: {status['state']['completion_reason']}")
        print(f"迭代次数: {status['state']['iteration']}")

    return workspace_path


async def example_stream_execution():
    """流式执行 Ralph"""
    print("\n=== 示例 2: 流式执行 ===\n")

    llm_client = LLMClient(
        api_key="api_key",
        model="deepseek/deepseek-chat",
    )

    session_id = f"ralph_stream_{uuid4().hex[:8]}"
    workspace_manager = WorkspaceManager(base_dir="./workspace")
    workspace_path = workspace_manager.get_session_workspace(session_id)

    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        BashTool(),
    ]

    agent = Agent(
        llm_client=llm_client,
        tools=tools,
        ralph=RalphConfig(enabled=True, max_iterations=3),
        max_steps=5,
        workspace_dir=str(workspace_path),
    )

    task = "创建 greeting.py，包含一个 greet 函数。完成后输出 <promise>TASK COMPLETE</promise>"

    print("流式事件:")
    async for event in agent.run_stream(task):
        event_type = event.get("type", "unknown")

        if event_type == "ralph_iteration_start":
            print(f"  [迭代开始] #{event['data']['iteration']}/{event['data']['max_iterations']}")
        elif event_type == "ralph_iteration_end":
            print(f"  [迭代结束] 完成={event['data']['completed']}")
        elif event_type == "ralph_completion":
            print(f"  [Ralph完成] 原因={event['data']['reason']}")
        elif event_type == "tool_result":
            print(
                f"  [工具结果] {event['data']['tool']}: {'成功' if event['data']['success'] else '失败'}"
            )

    status = agent.get_ralph_status()
    if status:
        print(f"\n最终状态: {status['state']}")


async def example_status_and_memory():
    """查询状态和工作记忆"""
    print("\n=== 示例 3: 状态和记忆查询 ===\n")

    llm_client = LLMClient(
        api_key="api_key",
        model="deepseek/deepseek-chat",
    )

    session_id = f"ralph_mem_{uuid4().hex[:8]}"
    workspace_manager = WorkspaceManager(base_dir="./workspace")
    workspace_path = workspace_manager.get_session_workspace(session_id)

    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        BashTool(),
    ]

    agent = Agent(
        llm_client=llm_client,
        tools=tools,
        ralph=True,
        max_steps=5,
        workspace_dir=str(workspace_path),
    )

    task = "创建 hello.txt，内容为 'Hello Ralph'。完成后输出 <promise>TASK COMPLETE</promise>"

    await agent.run(task)

    status = agent.get_ralph_status()
    if not status:
        print("Ralph 未启用")
        return

    print("Ralph 状态:")
    print(f"  启用: {status['enabled']}")
    print(f"  当前迭代: {status['state']['iteration']}")
    print(f"  已完成: {status['state']['completed']}")
    print(f"  完成原因: {status['state']['completion_reason']}")

    print("\n工作记忆摘要:")
    memory = status["memory_summary"]
    print(f"  修改文件数: {memory['files_modified_count']}")
    print(f"  待办事项: {memory['pending_todos']}")
    print(f"  已完成事项: {memory['completed_todos']}")
    if memory["recent_progress"]:
        print(f"  最近进度: {memory['recent_progress']}")

    print("\n配置:")
    config = status["config"]
    print(f"  最大迭代: {config['max_iterations']}")
    print(f"  空闲阈值: {config['idle_threshold']}")
    print(f"  完成标记: {config['completion_promise']}")

    if agent.ralph_loop:
        agent.reset_ralph()
        print("\nRalph 已重置，可以执行新任务")


async def main():
    print("Ralph 高级用法示例")
    print("=" * 50)

    await example_status_and_memory()


if __name__ == "__main__":
    asyncio.run(main())
