"""
测试 Team 会话管理功能

演示如何使用会话记录实现多轮对话上下文保持。
"""

import os
from dotenv import load_dotenv

from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.team import Team
from fastapi_agent.core.session import TeamSessionManager
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig
from fastapi_agent.tools.bash_tool import BashTool
from fastapi_agent.tools.file_tools import ReadTool, WriteTool

load_dotenv()


def test_basic_team_without_session():
    """测试 1: 基础 Team 使用 (无会话)."""
    print("=" * 80)
    print("测试 1: 基础 Team 使用 (无会话)")
    print("=" * 80)

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # 创建团队配置
    team_config = TeamConfig(
        name="Research Team",
        description="A team of specialists for research and analysis",
        members=[
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="Research Specialist",
                instructions="Conduct thorough research on given topics",
                tools=["bash"]
            ),
            TeamMemberConfig(
                id="analyst",
                name="Analyst",
                role="Data Analyst",
                instructions="Analyze data and provide insights",
                tools=[]
            ),
        ],
        delegate_to_all=False,
    )

    # 创建 Team (不传 session_manager)
    team = Team(
        config=team_config,
        llm_client=llm_client,
        available_tools=[BashTool(), ReadTool(), WriteTool()],
    )

    # 运行任务 (不传 session_id)
    response = team.run(
        message="What is Python asyncio? Keep it brief.",
        max_steps=20
    )

    print(f"\n✓ Team: {response.team_name}")
    print(f"✓ Success: {response.success}")
    print(f"✓ Total steps: {response.total_steps}")
    print(f"✓ Member interactions: {response.iterations}")
    print(f"\nResponse:\n{response.message}\n")
    print("=" * 80 + "\n")


def test_team_with_session():
    """测试 2: 使用会话的多轮对话."""
    print("=" * 80)
    print("测试 2: 使用会话的多轮对话")
    print("=" * 80)

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # 创建团队配置
    team_config = TeamConfig(
        name="Research Team",
        description="A team of specialists for research and writing",
        members=[
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="Research Specialist",
                instructions="Conduct thorough research on given topics",
                tools=["bash"]
            ),
            TeamMemberConfig(
                id="writer",
                name="Writer",
                role="Technical Writer",
                instructions="Write clear, concise documentation",
                tools=[]
            ),
        ],
        delegate_to_all=False,
    )

    # 创建会话管理器 (可选: 传 storage_path 持久化到文件)
    session_manager = TeamSessionManager(
        storage_path="~/.fastapi-agent/team_sessions.json"
    )

    # 创建 Team (传入 session_manager)
    team = Team(
        config=team_config,
        llm_client=llm_client,
        available_tools=[BashTool(), ReadTool(), WriteTool()],
        session_manager=session_manager,
    )

    # 第一轮对话
    print("\n--- Round 1: 研究 Python asyncio ---")
    response1 = team.run(
        message="Research Python asyncio and explain its core concepts briefly",
        max_steps=20,
        session_id="user-123",  # 指定会话 ID
        user_id="test-user"
    )
    print(f"✓ Success: {response1.success}")
    print(f"Response:\n{response1.message}\n")

    # 第二轮对话 (有历史上下文)
    print("--- Round 2: 基于上一轮研究写教程 ---")
    response2 = team.run(
        message="Based on the previous research, write a short tutorial on asyncio",
        max_steps=20,
        session_id="user-123",  # 同一个会话 ID
        num_history_runs=3  # 包含最近 3 轮历史
    )
    print(f"✓ Success: {response2.success}")
    print(f"Response:\n{response2.message}\n")

    # 第三轮对话 (继续上下文)
    print("--- Round 3: 补充示例代码 ---")
    response3 = team.run(
        message="Add a simple code example to the tutorial you just wrote",
        max_steps=20,
        session_id="user-123",
    )
    print(f"✓ Success: {response3.success}")
    print(f"Response:\n{response3.message}\n")

    print("=" * 80 + "\n")


def test_session_history_inspection():
    """测试 3: 检查会话历史."""
    print("=" * 80)
    print("测试 3: 检查会话历史")
    print("=" * 80)

    # 创建会话管理器
    session_manager = TeamSessionManager(
        storage_path="~/.fastapi-agent/team_sessions.json"
    )

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # 创建简单团队
    team_config = TeamConfig(
        name="Test Team",
        description="A test team",
        members=[
            TeamMemberConfig(id="helper", name="Helper", role="Assistant", tools=[]),
        ],
    )

    team = Team(
        config=team_config,
        llm_client=llm_client,
        session_manager=session_manager,
    )

    # 运行几轮对话
    session_id = "inspection-test"

    team.run("What is 2+2?", session_id=session_id, max_steps=10)
    team.run("What about 3+3?", session_id=session_id, max_steps=10)
    team.run("And 5*5?", session_id=session_id, max_steps=10)

    # 获取会话并检查
    session = session_manager.get_session(session_id, "Test Team")

    print(f"\n✓ Session ID: {session.session_id}")
    print(f"✓ Team Name: {session.team_name}")
    print(f"✓ Created: {session.created_at}")
    print(f"✓ Updated: {session.updated_at}")

    # 运行统计
    stats = session.get_runs_count()
    print(f"\n运行统计:")
    print(f"  - Total runs: {stats['total']}")
    print(f"  - Leader runs: {stats['leader']}")
    print(f"  - Member runs: {stats['member']}")

    # 查看历史上下文
    history = session.get_history_context(num_runs=3)
    print(f"\n历史上下文 (最近 3 轮):")
    print(history)

    # 查看所有 runs
    print(f"\n所有运行记录:")
    for i, run in enumerate(session.runs, 1):
        print(f"{i}. [{run.runner_type}] {run.runner_name}:")
        print(f"   Task: {run.task}")
        print(f"   Response: {run.response[:100]}...")  # 只显示前 100 字符
        print(f"   Success: {run.success}, Steps: {run.steps}")

    print("\n" + "=" * 80 + "\n")


def test_session_persistence():
    """测试 4: 会话持久化."""
    print("=" * 80)
    print("测试 4: 会话持久化")
    print("=" * 80)

    storage_path = "~/.fastapi-agent/test_persistence.json"

    # 第一阶段: 创建会话并运行
    print("\n--- 阶段 1: 创建会话并保存 ---")

    manager1 = TeamSessionManager(storage_path=storage_path)

    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    team_config = TeamConfig(
        name="Persistent Team",
        members=[TeamMemberConfig(id="helper", name="Helper", role="Assistant", tools=[])],
    )

    team1 = Team(
        config=team_config,
        llm_client=llm_client,
        session_manager=manager1,
    )

    team1.run("Hello, this is a test", session_id="persist-test", max_steps=10)
    print("✓ 会话已保存到文件")

    # 第二阶段: 重新加载会话
    print("\n--- 阶段 2: 从文件重新加载会话 ---")

    manager2 = TeamSessionManager(storage_path=storage_path)

    # 检查会话是否被加载
    if "persist-test" in manager2.sessions:
        session = manager2.sessions["persist-test"]
        print(f"✓ 成功加载会话: {session.session_id}")
        print(f"✓ Team: {session.team_name}")
        print(f"✓ 运行记录数: {len(session.runs)}")

        # 继续在同一会话中运行
        team2 = Team(
            config=team_config,
            llm_client=llm_client,
            session_manager=manager2,
        )

        team2.run("Continue from where we left", session_id="persist-test", max_steps=10)
        print("✓ 在加载的会话中继续运行成功")
    else:
        print("❌ 会话加载失败")

    print("\n" + "=" * 80 + "\n")


def main():
    """运行所有测试."""
    tests = [
        ("基础 Team (无会话)", test_basic_team_without_session),
        ("多轮对话 (有会话)", test_team_with_session),
        ("会话历史检查", test_session_history_inspection),
        ("会话持久化", test_session_persistence),
    ]

    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"❌ 测试失败: {name}")
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
        print("\n")


if __name__ == "__main__":
    main()
