"""正确的 Team 使用方式示例

演示如何正确使用 Team API，不需要手动创建 RunContext。
"""

import os
from dotenv import load_dotenv

from fastapi_agent.core.team import Team
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig
from fastapi_agent.tools.base_tools import WriteTool

load_dotenv()


async def correct_usage_example():
    """✅ 正确用法：使用独立参数"""
    print("=" * 60)
    print("✅ 正确用法：使用独立参数")
    print("=" * 60)

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE")
    )

    # 创建团队配置
    config = TeamConfig(
        name="Research Team",
        description="A team for research and documentation",
        members=[
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="Research Specialist",
                instructions="Find and summarize information",
                tools=[]
            ),
            TeamMemberConfig(
                id="writer",
                name="Writer",
                role="Technical Writer",
                instructions="Create clear documentation",
                tools=["write_file"]
            )
        ]
    )

    # 创建 Team
    team = Team(
        config=config,
        llm_client=llm_client,
        available_tools=[WriteTool()],
        workspace_dir="./workspace"
    )

    # ✅ 正确：使用独立参数（框架会自动创建 RunContext）
    response = await team.run(
        message="Research Python asyncio and create documentation",
        session_id="user-session-123",  # 用户会话 ID
        user_id="user-456",              # 用户 ID
        max_steps=50
    )

    print(f"\n✓ Team: {response.team_name}")
    print(f"✓ Success: {response.success}")
    print(f"✓ Message: {response.message[:100]}...")
    print(f"✓ Session ID (from metadata): {response.metadata.get('session_id')}")

    print("\n说明：")
    print("- 用户只需传递 session_id 和 user_id")
    print("- 框架内部自动创建 RunContext")
    print("- RunContext 用于内部上下文传递")
    print("- 所有 member agents 共享同一个 session_id")
    print("\n" + "=" * 60 + "\n")


async def multi_turn_conversation_example():
    """✅ 多轮对话示例"""
    print("=" * 60)
    print("✅ 多轮对话示例")
    print("=" * 60)

    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE")
    )

    config = TeamConfig(
        name="Research Team",
        members=[
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="Research Specialist",
                tools=[]
            )
        ]
    )

    team = Team(config=config, llm_client=llm_client)

    # 第一轮对话
    print("\n--- 第一轮对话 ---")
    response1 = await team.run(
        message="What is Python asyncio?",
        session_id="conversation-abc",  # 同一个 session_id
        user_id="user-123",
        max_steps=20
    )
    print(f"Response 1: {response1.message[:80]}...")

    # 第二轮对话（有上下文）
    print("\n--- 第二轮对话（基于上一轮的上下文） ---")
    response2 = await team.run(
        message="Give me a code example",
        session_id="conversation-abc",  # 同一个 session_id，会加载历史
        user_id="user-123",
        num_history_runs=3,  # 包含最近 3 轮历史
        max_steps=20
    )
    print(f"Response 2: {response2.message[:80]}...")

    print("\n说明：")
    print("- 使用相同的 session_id 实现多轮对话")
    print("- 框架自动管理会话历史")
    print("- 每轮对话都会创建新的 run_id")
    print("- RunContext 确保上下文一致性")
    print("\n" + "=" * 60 + "\n")


def incorrect_usage_example():
    """❌ 错误用法：手动创建 RunContext（不推荐）"""
    print("=" * 60)
    print("❌ 错误用法：手动创建 RunContext（不推荐）")
    print("=" * 60)

    from fastapi_agent.core.run_context import RunContext
    from uuid import uuid4

    # ❌ 不要这样做！
    run_context = RunContext(
        run_id=str(uuid4()),
        session_id="user-session-123",
        user_id="user-456"
    )

    print("\n这种方式虽然可以工作，但不推荐：")
    print("- 用户不应该关心 RunContext 的细节")
    print("- run_id 应该由框架自动生成")
    print("- 增加了不必要的复杂性")
    print("\n应该使用独立参数的方式（见上面的正确示例）")
    print("\n" + "=" * 60 + "\n")


async def main():
    """运行所有示例"""
    print("\n")
    print("=" * 60)
    print("Team API 正确使用方式")
    print("=" * 60)
    print("\n")

    # 正确用法
    await correct_usage_example()

    # 多轮对话
    await multi_turn_conversation_example()

    # 错误用法说明
    incorrect_usage_example()

    print("\n总结：")
    print("- ✅ 使用 session_id, user_id 等独立参数")
    print("- ❌ 不要手动创建 RunContext")
    print("- RunContext 是框架内部实现细节")
    print("- 参考 agno 的设计理念")
    print("\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
