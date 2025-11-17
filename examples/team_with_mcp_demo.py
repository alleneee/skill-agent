"""
AgentTeam 使用 MCP 工具演示

展示如何创建带有 MCP 工具的子 agent（desktop-commander 和 exa 网络搜索）
并通过 AgentTeam 协调完成复杂任务。
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.config import settings
from fastapi_agent.api.deps import get_tools


def demo_mcp_team_sequential():
    """演示使用 MCP 工具的顺序执行策略"""
    print("\n" + "=" * 60)
    print("演示: 使用 MCP 工具的 Sequential 策略")
    print("=" * 60)

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )

    # 获取所有可用工具（包括 MCP 工具）
    all_tools = get_tools()

    # 过滤出 exa 网络搜索工具
    exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower() or 'search' in tool.name.lower()]

    # 过滤出 desktop-commander 工具
    desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower() or 'commander' in tool.name.lower()]

    print(f"\n找到 {len(exa_tools)} 个 Exa 工具")
    print(f"找到 {len(desktop_tools)} 个 Desktop Commander 工具")

    # 创建网络搜索 agent（使用 exa MCP 工具）
    search_agent = Agent(
        llm_client=llm_client,
        name="WebSearcher",
        system_prompt="""你是网络搜索专家，负责使用 exa 搜索工具查找信息。
请使用 web_search_exa 工具搜索相关内容，并整理搜索结果。
保持回答简洁明了。""",
        tools=exa_tools,
        max_steps=5
    )

    # 创建桌面操作 agent（使用 desktop-commander MCP 工具）
    desktop_agent = Agent(
        llm_client=llm_client,
        name="DesktopOperator",
        system_prompt="""你是桌面操作专家，负责使用 desktop-commander 工具执行系统操作。
根据前一个 agent 提供的信息，执行相应的桌面操作。
保持回答简洁明了。""",
        tools=desktop_tools,
        max_steps=5
    )

    # 创建团队（顺序策略：先搜索，再操作）
    team = AgentTeam(
        members=[search_agent, desktop_agent],
        strategy=CoordinationStrategy.SEQUENTIAL,
        name="Search-and-Execute Team",
        share_interactions=True,
        enable_logging=True
    )

    # 执行任务
    result = team.run(message="搜索 Python FastAPI 最新教程，然后查看当前系统信息")

    print(f"\n✅ 任务完成!")
    print(f"执行步数: {result.steps}")
    print(f"\n最终输出:\n{result.final_output}")
    print(f"\n成员输出:")
    for member, output in result.member_outputs.items():
        print(f"\n  {member}:")
        print(f"  {output[:300]}...")


def demo_mcp_team_broadcast():
    """演示使用 MCP 工具的广播策略"""
    print("\n" + "=" * 60)
    print("演示: 使用 MCP 工具的 Broadcast 策略")
    print("=" * 60)

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )

    all_tools = get_tools()

    exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower() or 'search' in tool.name.lower()]
    desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower() or 'commander' in tool.name.lower()]

    # 创建两个专门的搜索 agent（使用 exa）
    tech_searcher = Agent(
        llm_client=llm_client,
        name="TechSearcher",
        system_prompt="""你是技术信息搜索专家。
使用 web_search_exa 工具搜索技术相关内容。
专注于找到权威、最新的技术资料。""",
        tools=exa_tools,
        max_steps=3
    )

    news_searcher = Agent(
        llm_client=llm_client,
        name="NewsSearcher",
        system_prompt="""你是新闻信息搜索专家。
使用 web_search_exa 工具搜索新闻和趋势。
专注于找到最新的行业动态和新闻。""",
        tools=exa_tools,
        max_steps=3
    )

    # 创建团队（广播策略：两个 agent 并行搜索）
    team = AgentTeam(
        members=[tech_searcher, news_searcher],
        strategy=CoordinationStrategy.BROADCAST,
        name="Multi-Search Team",
        enable_logging=True
    )

    # 执行任务
    result = team.run(message="搜索 AI Agent 相关的技术和新闻")

    print(f"\n✅ 任务完成!")
    print(f"执行步数: {result.steps}")
    print(f"\n成员输出:")
    for member, output in result.member_outputs.items():
        print(f"\n  {member}:")
        print(f"  {output[:200]}...")


def demo_mcp_team_leader_worker():
    """演示使用 MCP 工具的 Leader-Worker 策略"""
    print("\n" + "=" * 60)
    print("演示: 使用 MCP 工具的 Leader-Worker 策略")
    print("=" * 60)

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )

    all_tools = get_tools()

    exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower() or 'search' in tool.name.lower()]
    desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower() or 'commander' in tool.name.lower()]

    # 创建协调者（不需要工具）
    coordinator = Agent(
        llm_client=llm_client,
        name="Coordinator",
        system_prompt="""你是团队协调者。分析任务并制定执行计划。

可用成员:
- WebSearcher: 负责网络搜索（有 exa 搜索工具）
- DesktopOperator: 负责桌面操作（有 desktop-commander 工具）

返回 JSON 格式的计划:
{
    "analysis": "任务分析",
    "plan": [
        {"member": "成员名称", "task": "具体任务", "dependencies": []}
    ],
    "final_synthesis": "如何汇总"
}
""",
        max_steps=5
    )

    # 创建工作者
    search_agent = Agent(
        llm_client=llm_client,
        name="WebSearcher",
        system_prompt="你是网络搜索专家，使用 exa 工具搜索信息。简洁回答。",
        tools=exa_tools,
        max_steps=5
    )

    desktop_agent = Agent(
        llm_client=llm_client,
        name="DesktopOperator",
        system_prompt="你是桌面操作专家，使用 desktop-commander 工具执行系统操作。简洁回答。",
        tools=desktop_tools,
        max_steps=5
    )

    # 创建团队
    team = AgentTeam(
        members=[search_agent, desktop_agent],
        coordinator=coordinator,
        strategy=CoordinationStrategy.LEADER_WORKER,
        name="Coordinated MCP Team",
        share_interactions=True,
        enable_logging=True
    )

    # 执行任务
    result = team.run(message="搜索 Python 开发最佳实践，并检查系统环境是否满足要求")

    print(f"\n✅ 任务完成!")
    print(f"执行步数: {result.steps}")
    print(f"\n最终输出:\n{result.final_output[:500]}...")
    print(f"\n成员输出:")
    for member, output in result.member_outputs.items():
        print(f"\n  {member}:")
        print(f"  {output[:150]}...")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("AgentTeam 使用 MCP 工具演示")
    print("=" * 60)

    try:
        # 检查 MCP 是否启用
        if not settings.ENABLE_MCP:
            print("\n⚠️  警告: MCP 未启用，请在 .env 中设置 ENABLE_MCP=true")
            return

        # 运行各个演示
        print("\n正在运行演示...")

        # 演示 1: Sequential 策略
        demo_mcp_team_sequential()

        # 演示 2: Broadcast 策略
        demo_mcp_team_broadcast()

        # 演示 3: Leader-Worker 策略
        demo_mcp_team_leader_worker()

        print("\n" + "=" * 60)
        print("✅ 所有演示完成!")
        print("=" * 60)
        print("\n日志文件位置: ~/.fastapi-agent/log/team_run_*.log")

    except KeyboardInterrupt:
        print("\n\n⚠️  演示被用户中断")
    except Exception as e:
        print(f"\n\n❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
