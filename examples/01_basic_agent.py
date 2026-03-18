"""
基础 Agent 使用示例

展示如何创建和运行一个简单的 Agent。
workspace 会自动基于 session_id 创建隔离的子目录。

运行方式:
    uv run python examples/01_basic_agent.py
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from omni_agent.core import Agent, LLMClient, WorkspaceManager
from omni_agent.tools.bash_tool import BashTool
from omni_agent.tools.file_tools import ReadTool, WriteTool


async def main():
    llm_client = LLMClient(
        api_key="api_key",
        model="deepseek/deepseek-chat",
    )

    session_id = f"demo_{uuid4().hex[:8]}"

    workspace_manager = WorkspaceManager(base_dir="./workspace")
    workspace_path = workspace_manager.get_session_workspace(session_id)

    print(f"Session ID: {session_id}")
    print(f"Workspace: {workspace_path}")

    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        BashTool(),
    ]

    agent = Agent(
        llm_client=llm_client,
        system_prompt="你是一个有帮助的助手，可以读写文件和执行命令。",
        tools=tools,
        max_steps=10,
        workspace_dir=str(workspace_path),
    )

    agent.add_user_message("创建一个 hello.py 文件，内容是打印 Hello World")

    result, logs = await agent.run()

    print(f"\n结果: {result}")
    print(f"执行日志数: {len(logs)}")
    print(f"\n文件已保存在: {workspace_path}")


if __name__ == "__main__":
    asyncio.run(main())
