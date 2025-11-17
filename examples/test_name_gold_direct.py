"""
直接测试 Team Agent：
1. 使用 desktop-commander MCP 工具读取 name.txt 文件获取用户名
2. 使用 exa MCP 工具搜索最新黄金价格
3. 汇总结果

直接在 main 函数调用，不使用 API 接口
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.config import settings
from fastapi_agent.tools import ReadTool, BashTool
from fastapi_agent.api.deps import initialize_mcp_tools, get_tools


async def main():
    """直接调用 Team Agent 测试（使用 MCP 工具）"""
    print("\n" + "=" * 70)
    print("Team Agent 直接调用测试：读取用户名 + 黄金价格查询")
    print("=" * 70)

    # 1. 初始化 MCP 工具
    print("\n📦 步骤 1: 初始化 MCP 工具...")
    try:
        await initialize_mcp_tools()
        print("✅ MCP 工具初始化成功")
    except Exception as e:
        print(f"⚠️  MCP 工具初始化失败: {e}")
        print("将使用基础工具继续...")

    # 2. 获取所有工具
    print("\n📦 步骤 2: 加载工具...")
    workspace_dir = "/Users/niko/skill-agent"
    all_tools = get_tools(workspace_dir=workspace_dir)
    print(f"总共加载了 {len(all_tools)} 个工具")

    # 筛选 MCP 工具
    desktop_tools = [tool for tool in all_tools if 'desktop' in tool.name.lower() or 'commander' in tool.name.lower() or 'read' in tool.name.lower() or 'bash' in tool.name.lower()]
    exa_tools = [tool for tool in all_tools if 'exa' in tool.name.lower() or 'web_search' in tool.name.lower()]

    print(f"  - Desktop/文件工具: {len(desktop_tools)} 个")
    if desktop_tools:
        for tool in desktop_tools[:5]:
            print(f"    • {tool.name}")

    print(f"  - Exa 搜索工具: {len(exa_tools)} 个")
    if exa_tools:
        for tool in exa_tools[:3]:
            print(f"    • {tool.name}")

    # 3. 创建 LLM 客户端
    print("\n📦 步骤 3: 创建 LLM 客户端...")

    # 检查 API key
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.strip() == "":
        print("❌ 错误: LLM_API_KEY 未设置或为空")
        print("请在 .env 文件中设置 LLM_API_KEY")
        return None

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
- FileReader: 负责读取文件（有 read 和 bash 工具）
- WebSearcher: 负责网络搜索（有 exa 搜索工具）

请返回 JSON 格式的执行计划:
{
    "analysis": "任务分析",
    "plan": [
        {"member": "FileReader", "task": "读取 /Users/niko/skill-agent/name.txt 文件获取用户名", "dependencies": []},
        {"member": "WebSearcher", "task": "搜索当前黄金价格信息", "dependencies": []}
    ],
    "final_synthesis": "汇总用户名和黄金价格信息"
}
""",
        tools=[],
        max_steps=3
    )
    print(f"✅ 协调者创建成功: {coordinator.name}")

    # 5. 创建文件读取 Agent（使用 desktop-commander 或 read 工具）
    print("\n📦 步骤 5: 创建文件读取 Agent...")
    file_reader = Agent(
        llm_client=llm_client,
        name="FileReader",
        system_prompt="""你是文件读取专家。请使用可用的工具读取文件内容。

任务：读取文件 /Users/niko/skill-agent/name.txt 并报告其中的用户名。

当前项目根目录: /Users/niko/skill-agent/
目标文件: name.txt（在项目根目录下）

请读取文件内容并报告用户名称。""",
        tools=desktop_tools if desktop_tools else [ReadTool(workspace_dir=workspace_dir), BashTool()],
        max_steps=5
    )
    print(f"✅ 文件读取 Agent 创建成功: {file_reader.name}")
    print(f"   工具数量: {len(desktop_tools) if desktop_tools else 2}")

    # 6. 创建网络搜索 Agent（使用 exa 工具或 LLM 知识）
    print("\n📦 步骤 6: 创建网络搜索 Agent...")
    info_provider = Agent(
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
    print(f"✅ 网络搜索 Agent 创建成功: {info_provider.name}")
    print(f"   工具数量: {len(exa_tools)}")

    # 7. 创建 Team（使用 Leader-Worker 策略）
    print("\n📦 步骤 7: 创建 Agent Team...")
    team = AgentTeam(
        members=[file_reader, info_provider],
        coordinator=coordinator,
        strategy=CoordinationStrategy.LEADER_WORKER,
        name="Name-Gold Team",
        share_interactions=True,
        enable_logging=True,
        workspace_dir=workspace_dir
    )
    print(f"✅ Team 创建成功: {team.name}")
    print(f"   策略: {team.strategy.value}")
    print(f"   成员数: {len(team.members)}")
    print(f"   协调者: {team.coordinator.name}")

    # 8. 执行任务
    print("\n" + "=" * 70)
    print("🚀 开始执行任务...")
    print("=" * 70)

    task = """请完成以下两个任务并汇总结果：

任务 1: 读取项目根目录 /Users/niko/skill-agent/name.txt 文件，获取用户名称
任务 2: 提供当前最新的黄金价格信息（国际金价和国内金价）

最后请汇总成一段话：告诉我用户是谁，以及当前黄金价格是多少。
"""

    try:
        print(f"\n📋 任务描述:\n{task}\n")
        print("-" * 70)

        result = await team.run(
            message=task,
            workspace_dir=workspace_dir
        )

        # 9. 显示结果
        print("\n" + "=" * 70)
        print("📊 任务执行结果")
        print("=" * 70)

        print(f"\n✅ 执行状态: {'成功' if result.success else '失败'}")
        print(f"📝 执行步数: {result.steps}")
        print(f"🔍 交互次数: {len(result.interactions)}")

        print("\n" + "-" * 70)
        print("📄 各成员输出:")
        print("-" * 70)
        for member_name, output in result.member_outputs.items():
            print(f"\n🤖 {member_name}:")
            print(f"{output}")

        print("\n" + "-" * 70)
        print("🎯 最终汇总结果:")
        print("-" * 70)
        print(f"\n{result.final_output}\n")

        print("-" * 70)
        print("📋 详细交互历史:")
        print("-" * 70)
        for i, interaction in enumerate(result.interactions, 1):
            print(f"\n[交互 {i}] {interaction.member_name} - 步骤 {interaction.step}")
            print(f"时间: {interaction.timestamp}")
            print(f"\n输入 (前200字符):")
            print(f"  {interaction.input_message[:200]}...")
            print(f"\n输出 (前200字符):")
            print(f"  {interaction.output_message[:200]}...")

        # 10. 保存结果到文件
        output_file = os.path.join(workspace_dir, "workspace", "team_result.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("Team Agent 执行结果\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"执行时间: {result.interactions[0].timestamp if result.interactions else 'N/A'}\n")
            f.write(f"策略: {team.strategy.value}\n")
            f.write(f"执行步数: {result.steps}\n\n")

            f.write("=" * 70 + "\n")
            f.write("任务描述\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"{task}\n\n")

            f.write("=" * 70 + "\n")
            f.write("各成员输出\n")
            f.write("=" * 70 + "\n\n")
            for member_name, output in result.member_outputs.items():
                f.write(f"【{member_name}】\n")
                f.write(f"{output}\n\n")
                f.write("-" * 70 + "\n\n")

            f.write("=" * 70 + "\n")
            f.write("最终汇总结果\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"{result.final_output}\n\n")

            f.write("=" * 70 + "\n")
            f.write("交互历史\n")
            f.write("=" * 70 + "\n\n")
            for i, interaction in enumerate(result.interactions, 1):
                f.write(f"[{i}] {interaction.member_name} - {interaction.timestamp}\n")
                f.write(f"输入: {interaction.input_message}\n")
                f.write(f"输出: {interaction.output_message}\n")
                f.write("-" * 70 + "\n\n")

        print(f"\n💾 详细结果已保存到: {output_file}")

        # 11. 总结
        print("\n" + "=" * 70)
        print("🎉 测试完成！")
        print("=" * 70)
        print("\n📌 关键信息:")
        print(f"   • 用户名: {result.final_output.split('叫')[1].split(',')[0] if '叫' in result.final_output else '未找到'}")
        print(f"   • 执行策略: {team.strategy.value}")
        print(f"   • 总步数: {result.steps}")
        print(f"   • 成功: {'是' if result.success else '否'}")

        if result.logs:
            print(f"\n📝 日志文件: ~/.fastapi-agent/log/team_run_*.log")

        return result

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    import warnings

    # 抑制 MCP 客户端关闭时的 asyncio 警告（Python 3.13 已知问题）
    warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*coroutine.*was never awaited")

    try:
        result = asyncio.run(main())

        if result and result.success:
            print("\n✨ 所有任务成功完成！")
            sys.exit(0)
        else:
            print("\n⚠️  任务执行遇到问题，请查看上面的输出")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        # 排除 MCP 客户端清理时的异常
        if "cancel scope" not in str(e) and "GeneratorExit" not in str(e):
            print(f"\n\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        else:
            # MCP 清理异常，忽略并正常退出
            if result and result.success:
                print("\n✨ 所有任务成功完成！")
                sys.exit(0)
