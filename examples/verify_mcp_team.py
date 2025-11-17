"""
验证 MCP Team Agent 实现的简单脚本

不依赖 pytest，直接验证功能
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.config import settings
from fastapi_agent.api.deps import get_tools


def verify_mcp_enabled():
    """验证 MCP 是否启用"""
    print("\n=== 验证 MCP 配置 ===")
    print(f"ENABLE_MCP: {settings.ENABLE_MCP}")
    print(f"MCP_CONFIG_PATH: {settings.MCP_CONFIG_PATH}")

    if not settings.ENABLE_MCP:
        print("⚠️  MCP 未启用，请在 .env 中设置 ENABLE_MCP=true")
        return False

    print("✅ MCP 已启用")
    return True


def verify_mcp_tools():
    """验证 MCP 工具是否加载"""
    print("\n=== 验证 MCP 工具 ===")

    try:
        all_tools = get_tools()
        print(f"总工具数: {len(all_tools)}")

        # 查找 exa 工具
        exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower() or 'search' in tool.name.lower()]
        print(f"\nExa 搜索工具数: {len(exa_tools)}")
        for tool in exa_tools:
            print(f"  - {tool.name}: {tool.description[:50]}...")

        # 查找 desktop-commander 工具
        desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower() or 'commander' in tool.name.lower()]
        print(f"\nDesktop Commander 工具数: {len(desktop_tools)}")
        for tool in desktop_tools:
            print(f"  - {tool.name}: {tool.description[:50]}...")

        if len(exa_tools) == 0:
            print("⚠️  未找到 exa 工具")
        else:
            print("✅ Exa 工具加载成功")

        if len(desktop_tools) == 0:
            print("⚠️  未找到 desktop-commander 工具")
        else:
            print("✅ Desktop Commander 工具加载成功")

        return len(exa_tools) > 0 or len(desktop_tools) > 0

    except Exception as e:
        print(f"❌ 工具加载失败: {e}")
        return False


def verify_agent_creation():
    """验证带有 MCP 工具的 agent 创建"""
    print("\n=== 验证 Agent 创建 ===")

    try:
        llm_client = LLMClient(
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE,
            model=settings.LLM_MODEL
        )

        all_tools = get_tools()
        exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower()]
        desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower()]

        # 创建搜索 agent
        search_agent = Agent(
            llm_client=llm_client,
            name="WebSearcher",
            system_prompt="你是网络搜索专家",
            tools=exa_tools[:1] if exa_tools else [],  # 只取第一个工具
            max_steps=3
        )

        print(f"✅ 搜索 Agent 创建成功: {search_agent.name}")
        print(f"   工具数: {len(search_agent.tools)}")

        # 创建桌面操作 agent
        desktop_agent = Agent(
            llm_client=llm_client,
            name="DesktopOperator",
            system_prompt="你是桌面操作专家",
            tools=desktop_tools[:1] if desktop_tools else [],  # 只取第一个工具
            max_steps=3
        )

        print(f"✅ 桌面 Agent 创建成功: {desktop_agent.name}")
        print(f"   工具数: {len(desktop_agent.tools)}")

        return search_agent, desktop_agent

    except Exception as e:
        print(f"❌ Agent 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def verify_team_creation(search_agent, desktop_agent):
    """验证 AgentTeam 创建"""
    print("\n=== 验证 AgentTeam 创建 ===")

    if not search_agent or not desktop_agent:
        print("❌ Agent 未创建，跳过团队验证")
        return None

    try:
        # 测试 Sequential 策略
        team_sequential = AgentTeam(
            members=[search_agent, desktop_agent],
            strategy=CoordinationStrategy.SEQUENTIAL,
            name="Sequential Team",
            enable_logging=False
        )
        print(f"✅ Sequential Team 创建成功: {team_sequential.name}")
        print(f"   成员数: {len(team_sequential.members)}")
        print(f"   策略: {team_sequential.strategy.value}")

        # 测试 Broadcast 策略
        team_broadcast = AgentTeam(
            members=[search_agent, desktop_agent],
            strategy=CoordinationStrategy.BROADCAST,
            name="Broadcast Team",
            enable_logging=False
        )
        print(f"✅ Broadcast Team 创建成功: {team_broadcast.name}")

        # 测试 Leader-Worker 策略
        llm_client = LLMClient(
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE,
            model=settings.LLM_MODEL
        )

        coordinator = Agent(
            llm_client=llm_client,
            name="Coordinator",
            system_prompt="你是团队协调者",
            max_steps=5
        )

        team_leader = AgentTeam(
            members=[search_agent, desktop_agent],
            coordinator=coordinator,
            strategy=CoordinationStrategy.LEADER_WORKER,
            name="Leader-Worker Team",
            share_interactions=True,
            enable_logging=False
        )
        print(f"✅ Leader-Worker Team 创建成功: {team_leader.name}")
        print(f"   协调者: {team_leader.coordinator.name}")
        print(f"   成员交互共享: {team_leader.share_interactions}")

        return team_sequential

    except Exception as e:
        print(f"❌ AgentTeam 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def verify_team_strategies():
    """验证所有协调策略"""
    print("\n=== 验证协调策略枚举 ===")

    strategies = [
        CoordinationStrategy.LEADER_WORKER,
        CoordinationStrategy.BROADCAST,
        CoordinationStrategy.SEQUENTIAL,
        CoordinationStrategy.ROUND_ROBIN
    ]

    for strategy in strategies:
        print(f"✅ {strategy.name}: {strategy.value}")

    return True


def main():
    """主验证流程"""
    print("\n" + "=" * 60)
    print("MCP Team Agent 实现验证")
    print("=" * 60)

    results = {
        "mcp_enabled": False,
        "tools_loaded": False,
        "agents_created": False,
        "teams_created": False,
        "strategies_verified": False
    }

    # 1. 验证 MCP 启用
    results["mcp_enabled"] = verify_mcp_enabled()

    # 2. 验证 MCP 工具加载
    if results["mcp_enabled"]:
        results["tools_loaded"] = verify_mcp_tools()

    # 3. 验证 Agent 创建
    search_agent, desktop_agent = verify_agent_creation()
    results["agents_created"] = (search_agent is not None and desktop_agent is not None)

    # 4. 验证 Team 创建
    if results["agents_created"]:
        team = verify_team_creation(search_agent, desktop_agent)
        results["teams_created"] = (team is not None)

    # 5. 验证策略
    results["strategies_verified"] = verify_team_strategies()

    # 总结
    print("\n" + "=" * 60)
    print("验证结果总结")
    print("=" * 60)

    for key, value in results.items():
        status = "✅ 通过" if value else "❌ 失败"
        print(f"{key.replace('_', ' ').title()}: {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有验证通过！MCP Team Agent 实现正确。")
    else:
        print("⚠️  部分验证失败，请检查配置和依赖。")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  验证被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
