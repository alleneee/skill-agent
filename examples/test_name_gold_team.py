"""
测试 Team Agent 实际场景：
1. 使用 desktop-commander 读取 name.txt 文件
2. 使用 exa 搜索最新黄金价格
3. 汇总结果

注意：这个脚本需要在 FastAPI 应用启动后才能使用 MCP 工具
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.config import settings
from fastapi_agent.api.deps import initialize_mcp_tools, get_tools


async def test_name_and_gold_price():
    """测试读取用户名和黄金价格"""
    print("\n" + "=" * 70)
    print("Team Agent 实战测试：读取用户名 + 查询黄金价格")
    print("=" * 70)

    # 1. 初始化 MCP 工具（模拟 FastAPI 启动过程）
    print("\n📦 步骤 1: 初始化 MCP 工具...")
    try:
        await initialize_mcp_tools()
        print("✅ MCP 工具初始化成功")
    except Exception as e:
        print(f"⚠️  MCP 工具初始化失败: {e}")
        print("💡 提示: 某些 MCP 工具可能需要在 FastAPI 环境中运行")

    # 2. 获取所有工具
    print("\n📦 步骤 2: 加载工具...")
    all_tools = get_tools()
    print(f"总共加载了 {len(all_tools)} 个工具")

    # 筛选工具
    desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower() or 'commander' in tool.name.lower() or 'bash' in tool.name.lower() or 'read' in tool.name.lower()]
    exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower() or 'web_search' in tool.name.lower()]

    print(f"  - Desktop/文件工具: {len(desktop_tools)} 个")
    if desktop_tools:
        for tool in desktop_tools[:3]:
            print(f"    • {tool.name}")

    print(f"  - Exa 搜索工具: {len(exa_tools)} 个")
    if exa_tools:
        for tool in exa_tools[:3]:
            print(f"    • {tool.name}")

    # 3. 创建 LLM 客户端
    print("\n📦 步骤 3: 创建 LLM 客户端...")
    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL
    )
    print("✅ LLM 客户端创建成功")

    # 4. 创建协调者
    print("\n📦 步骤 4: 创建协调者 Agent...")
    coordinator = Agent(
        llm_client=llm_client,
        name="Coordinator",
        system_prompt="""你是团队协调者。请分析任务并制定执行计划。

可用成员:
- FileReader: 负责读取文件（有文件操作工具）
- WebSearcher: 负责网络搜索（有 exa 搜索工具）

请返回 JSON 格式的执行计划:
{
    "analysis": "任务分析",
    "plan": [
        {"member": "成员名称", "task": "具体任务描述", "dependencies": []}
    ],
    "final_synthesis": "如何汇总结果"
}
""",
        tools=[],
        max_steps=5
    )
    print(f"✅ 协调者创建成功: {coordinator.name}")

    # 5. 创建文件读取 Agent
    print("\n📦 步骤 5: 创建文件读取 Agent...")
    file_reader = Agent(
        llm_client=llm_client,
        name="FileReader",
        system_prompt="""你是文件读取专家。请使用可用的工具读取文件内容。

当前项目根目录: /Users/niko/skill-agent/
目标文件: name.txt（在项目根目录下）

请读取文件内容并报告用户名称。""",
        tools=desktop_tools,
        max_steps=5
    )
    print(f"✅ 文件读取 Agent 创建成功: {file_reader.name}")
    print(f"   工具数量: {len(desktop_tools)}")

    # 6. 创建网络搜索 Agent
    print("\n📦 步骤 6: 创建网络搜索 Agent...")
    web_searcher = Agent(
        llm_client=llm_client,
        name="WebSearcher",
        system_prompt="""你是网络搜索专家。请使用 exa 搜索工具查找最新的黄金价格信息。

重要提示：
- 如果有 web_search_exa 工具，请使用它搜索"黄金价格 gold price today"
- 如果没有 exa 工具，请直接回答你知道的黄金价格信息
- 请提供当前黄金价格的估算值""",
        tools=exa_tools if exa_tools else [],
        max_steps=5
    )
    print(f"✅ 网络搜索 Agent 创建成功: {web_searcher.name}")
    print(f"   工具数量: {len(exa_tools)}")

    # 7. 创建 Team（使用 Leader-Worker 策略）
    print("\n📦 步骤 7: 创建 Agent Team...")
    team = AgentTeam(
        members=[file_reader, web_searcher],
        coordinator=coordinator,
        strategy=CoordinationStrategy.LEADER_WORKER,
        name="Name-Gold Team",
        share_interactions=True,
        enable_logging=True
    )
    print(f"✅ Team 创建成功: {team.name}")
    print(f"   策略: {team.strategy.value}")
    print(f"   成员数: {len(team.members)}")

    # 8. 执行任务
    print("\n" + "=" * 70)
    print("🚀 开始执行任务...")
    print("=" * 70)

    task = """请完成以下两个任务并汇总结果：

任务 1: 读取项目根目录 /Users/niko/skill-agent/name.txt 文件，获取用户名称
任务 2: 搜索网上最新的黄金价格信息

最后请汇总：用户是谁，以及当前黄金价格是多少。
"""

    try:
        result = team.run(message=task, workspace_dir="/Users/niko/skill-agent/")

        # 9. 显示结果
        print("\n" + "=" * 70)
        print("📊 任务执行结果")
        print("=" * 70)

        print(f"\n✅ 执行状态: {'成功' if result.success else '失败'}")
        print(f"📝 执行步数: {result.steps}")
        print(f"🔍 交互次数: {len(result.interactions)}")

        print("\n" + "-" * 70)
        print("📄 成员输出:")
        print("-" * 70)
        for member_name, output in result.member_outputs.items():
            print(f"\n🤖 {member_name}:")
            print(f"{output}\n")

        print("-" * 70)
        print("🎯 最终汇总结果:")
        print("-" * 70)
        print(f"\n{result.final_output}\n")

        print("-" * 70)
        print("📋 交互历史:")
        print("-" * 70)
        for i, interaction in enumerate(result.interactions, 1):
            print(f"\n[{i}] {interaction.member_name} (步骤 {interaction.step})")
            print(f"    时间: {interaction.timestamp}")
            print(f"    输入: {interaction.input_message[:100]}...")
            print(f"    输出: {interaction.output_message[:100]}...")

        # 保存结果到文件
        output_file = "/Users/niko/skill-agent/workspace/team_result.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("Team Agent 执行结果\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"任务: {task}\n\n")
            f.write("-" * 70 + "\n")
            f.write("成员输出:\n")
            f.write("-" * 70 + "\n\n")
            for member_name, output in result.member_outputs.items():
                f.write(f"{member_name}:\n{output}\n\n")
            f.write("-" * 70 + "\n")
            f.write("最终结果:\n")
            f.write("-" * 70 + "\n\n")
            f.write(result.final_output + "\n")

        print(f"\n💾 结果已保存到: {output_file}")

        return result

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    try:
        result = await test_name_and_gold_price()

        print("\n" + "=" * 70)
        if result and result.success:
            print("🎉 测试完成！")
        else:
            print("⚠️  测试未完全成功，请查看日志")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
