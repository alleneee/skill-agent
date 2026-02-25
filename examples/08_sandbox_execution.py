"""
Sandbox 隔离执行示例

展示如何使用 agents-sandbox 进行代码隔离执行。
每个 session 拥有独立的沙箱环境，互不影响。

前置条件:
    1. 启动 sandbox Docker 容器:
       docker run -d --security-opt seccomp=unconfined -p 8080:8080 ghcr.io/agents-infra/sandbox:latest

    2. 安装 agents-sandbox:
       uv add agents-sandbox

运行方式:
    uv run python examples/08_sandbox_execution.py
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from omni_agent.core import Agent, LLMClient
from omni_agent.sandbox import SandboxManager, SandboxToolkit


async def basic_sandbox_usage():
    """基础沙箱使用 - 直接操作沙箱客户端"""
    print("=" * 50)
    print("1. 基础沙箱使用")
    print("=" * 50)

    manager = SandboxManager(base_url="http://localhost:8080")
    await manager.initialize()

    session_id = f"demo_{uuid4().hex[:8]}"
    sandbox = await manager.get_sandbox(session_id)

    print(f"Session: {session_id}")
    print(f"Home dir: {sandbox.home_dir}")

    result = sandbox.client.shell.exec_command(command="echo 'Hello from Sandbox!' && uname -a")
    print(f"Shell output: {result.output}")

    sandbox.client.filesystem.write_file(path="/tmp/test.txt", content="Sandbox test content")
    content = sandbox.client.filesystem.read_file(path="/tmp/test.txt")
    print(f"File content: {content}")

    result = sandbox.client.jupyter.execute_code(code="print(sum(range(1, 101)))")
    print(f"Python output: {result.output}")

    await manager.remove_sandbox(session_id)
    await manager.shutdown()


async def agent_with_sandbox():
    """Agent + 沙箱工具"""
    print("\n" + "=" * 50)
    print("2. Agent + 沙箱工具")
    print("=" * 50)

    manager = SandboxManager(base_url="http://localhost:8080")
    await manager.initialize()

    session_id = f"agent_{uuid4().hex[:8]}"
    toolkit = SandboxToolkit(manager)
    tools = await toolkit.get_tools(session_id)

    print(f"Session: {session_id}")
    print(f"Available tools: {[t.name for t in tools]}")

    llm_client = LLMClient(
        api_key="api_key",
        model="deepseek/deepseek-chat",
    )

    agent = Agent(
        llm_client=llm_client,
        system_prompt="你是一个代码执行助手，在隔离的沙箱环境中执行代码。",
        tools=tools,
        max_steps=10,
    )

    agent.add_user_message("在沙箱中创建一个 Python 脚本计算斐波那契数列前10项，然后执行它")

    result, logs = await agent.run()

    print(f"\nAgent result: {result}")
    print(f"Steps: {len([l for l in logs if l.get('type') == 'step'])}")

    await toolkit.cleanup_session(session_id)
    await manager.shutdown()


async def multi_session_isolation():
    """多 Session 隔离演示"""
    print("\n" + "=" * 50)
    print("3. 多 Session 隔离")
    print("=" * 50)

    manager = SandboxManager(base_url="http://localhost:8080")
    await manager.initialize()

    session_a = "session_a"
    session_b = "session_b"

    sandbox_a = await manager.get_sandbox(session_a)
    sandbox_b = await manager.get_sandbox(session_b)

    sandbox_a.client.filesystem.write_file(path="/tmp/data.txt", content="Session A data")
    sandbox_b.client.filesystem.write_file(path="/tmp/data.txt", content="Session B data")

    content_a = sandbox_a.client.filesystem.read_file(path="/tmp/data.txt")
    content_b = sandbox_b.client.filesystem.read_file(path="/tmp/data.txt")

    print(f"Session A file: {content_a}")
    print(f"Session B file: {content_b}")
    print(f"Files are isolated: {content_a != content_b}")

    print(f"Active sandboxes: {manager.active_sandboxes}")

    await manager.shutdown()


async def main():
    try:
        await basic_sandbox_usage()
    except Exception as e:
        print(f"Basic usage failed: {e}")
        print("Ensure sandbox container is running:")
        print("  docker run -d --security-opt seccomp=unconfined -p 8080:8080 ghcr.io/agents-infra/sandbox:latest")
        return

    try:
        await agent_with_sandbox()
    except Exception as e:
        print(f"Agent example failed: {e}")

    try:
        await multi_session_isolation()
    except Exception as e:
        print(f"Multi-session example failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
