"""
AgentTeam 多 Agent 协调系统演示

展示如何使用 AgentTeam 实现多个 Agent 协作完成复杂任务。
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.config import settings


def demo_sequential_strategy():
    """演示顺序执行策略"""
    print("\n" + "=" * 60)
    print("演示 1: Sequential 策略 (顺序执行)")
    print("=" * 60)

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )

    # 创建团队成员
    researcher = Agent(
        llm_client=llm_client,
        name="Researcher",
        system_prompt="你是研究员,负责收集和分析信息。请简洁回答。",
        max_steps=3
    )

    writer = Agent(
        llm_client=llm_client,
        name="Writer",
        system_prompt="你是写作专家,负责将信息整理成文档。请简洁回答。",
        max_steps=3
    )

    # 创建团队(顺序策略)
    team = AgentTeam(
        members=[researcher, writer],
        strategy=CoordinationStrategy.SEQUENTIAL,
        name="Research-Writing Team",
        share_interactions=True,
        enable_logging=True
    )

    # 执行任务
    result = team.run(message="简要介绍 Python 异步编程的核心概念")

    print(f"\n✅ 任务完成!")
    print(f"执行步数: {result.steps}")
    print(f"\n最终输出:\n{result.final_output}")
    print(f"\n成员输出:")
    for member, output in result.member_outputs.items():
        print(f"\n  {member}:\n  {output[:200]}...")


def demo_broadcast_strategy():
    """演示广播策略"""
    print("\n" + "=" * 60)
    print("演示 2: Broadcast 策略 (并行执行)")
    print("=" * 60)

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )

    # 创建多个分析师
    analyst1 = Agent(
        llm_client=llm_client,
        name="Performance Analyst",
        system_prompt="你是性能分析专家,从性能角度分析问题。请简洁回答。",
        max_steps=3
    )

    analyst2 = Agent(
        llm_client=llm_client,
        name="Security Analyst",
        system_prompt="你是安全分析专家,从安全角度分析问题。请简洁回答。",
        max_steps=3
    )

    # 创建团队(广播策略)
    team = AgentTeam(
        members=[analyst1, analyst2],
        strategy=CoordinationStrategy.BROADCAST,
        name="Analysis Team",
        enable_logging=True
    )

    # 执行任务
    result = team.run(message="分析使用 Python asyncio 的注意事项")

    print(f"\n✅ 任务完成!")
    print(f"执行步数: {result.steps}")
    print(f"\n成员输出:")
    for member, output in result.member_outputs.items():
        print(f"\n  {member}:\n  {output[:200]}...")


def demo_leader_worker_strategy():
    """演示领导者-工作者策略"""
    print("\n" + "=" * 60)
    print("演示 3: Leader-Worker 策略 (智能协调)")
    print("=" * 60)

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )

    # 创建协调者
    coordinator = Agent(
        llm_client=llm_client,
        name="Coordinator",
        system_prompt="""你是团队协调者。分析任务并制定执行计划。

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

    # 创建团队成员
    researcher = Agent(
        llm_client=llm_client,
        name="Researcher",
        system_prompt="你是研究员,负责收集信息。请简洁回答。",
        max_steps=3
    )

    writer = Agent(
        llm_client=llm_client,
        name="Writer",
        system_prompt="你是写作专家,负责撰写文档。请简洁回答。",
        max_steps=3
    )

    reviewer = Agent(
        llm_client=llm_client,
        name="Reviewer",
        system_prompt="你是审阅专家,负责检查质量。请简洁回答。",
        max_steps=3
    )

    # 创建团队(领导者-工作者策略)
    team = AgentTeam(
        members=[researcher, writer, reviewer],
        coordinator=coordinator,
        strategy=CoordinationStrategy.LEADER_WORKER,
        name="Coordinated Team",
        share_interactions=True,
        enable_logging=True
    )

    # 执行任务
    result = team.run(message="研究 FastAPI 框架并写一篇简短介绍,然后审阅")

    print(f"\n✅ 任务完成!")
    print(f"执行步数: {result.steps}")
    print(f"\n最终输出:\n{result.final_output[:500]}...")
    print(f"\n成员输出:")
    for member, output in result.member_outputs.items():
        print(f"\n  {member}:\n  {output[:150]}...")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("AgentTeam 多 Agent 协调系统演示")
    print("=" * 60)

    try:
        # 运行各个演示
        demo_sequential_strategy()
        demo_broadcast_strategy()
        demo_leader_worker_strategy()

        print("\n" + "=" * 60)
        print("✅ 所有演示完成!")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n⚠️  演示被用户中断")
    except Exception as e:
        print(f"\n\n❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
