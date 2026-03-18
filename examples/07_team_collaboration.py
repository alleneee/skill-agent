"""
Team 多 Agent 协作示例

展示如何使用 Team 系统实现 Leader-Member 模式的多 Agent 协作。
workspace 会自动基于 session_id 创建隔离的子目录。

运行方式:
    uv run python examples/07_team_collaboration.py

注意: 此示例需要设置 LLM_API_KEY 环境变量
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from omni_agent.core import LLMClient, WorkspaceManager
from omni_agent.core.team import Team
from omni_agent.schemas.team import TeamConfig, TeamMemberConfig
from omni_agent.tools.file_tools import EditTool, ReadTool, WriteTool


async def main():
    llm_client = LLMClient(
        api_key="sk-eb2e45cc436a440bbb606f588ebbc094",
        model="deepseek/deepseek-chat",
    )

    session_id = f"team_{uuid4().hex[:8]}"

    workspace_manager = WorkspaceManager(base_dir="./workspace")
    workspace_path = workspace_manager.get_session_workspace(session_id)

    print(f"Session ID: {session_id}")
    print(f"Workspace: {workspace_path}")

    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        EditTool(workspace_dir=str(workspace_path)),
    ]

    config = TeamConfig(
        name="Research Team",
        description="研究和写作团队",
        members=[
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="Research Specialist",
                instructions="你是研究员，擅长搜索信息、阅读资料并总结要点。回复要简洁。",
                tools=["read_file"],
            ),
            TeamMemberConfig(
                id="writer",
                name="Writer",
                role="Writing Expert",
                instructions="你是写作专家，擅长将信息组织成清晰、结构化的文档。回复要简洁。",
                tools=["write_file", "edit_file"],
            ),
            TeamMemberConfig(
                id="reviewer",
                name="Reviewer",
                role="Quality Reviewer",
                instructions="你是审阅专家，负责检查内容的质量、准确性和完整性。回复要简洁。",
                tools=["read_file"],
            ),
        ],
        leader_instructions="你是团队领导，负责协调成员完成任务。简洁地分配任务并综合结果。",
    )

    team = Team(
        config=config,
        llm_client=llm_client,
        available_tools=tools,
        workspace_dir=str(workspace_path),
    )

    print("\n=== Team 多 Agent 协作 ===\n")
    print(f"团队名称: {config.name}")
    print(f"成员数量: {len(config.members)}")
    for member in config.members:
        print(f"  - {member.name}: {member.role}")
    print()

    task = "简要介绍 Python 的 asyncio 模块的核心概念（100字以内）"
    print(f"任务: {task}\n")
    print("正在执行... (这需要 LLM API 调用)\n")

    result = await team.run(message=task, max_steps=30)

    print("=== 执行结果 ===\n")
    print(f"成功: {result.success}")
    print(f"迭代次数: {result.iterations}")
    print(f"总步骤数: {result.total_steps}")
    print(f"\n最终结果:\n{result.message}")

    if result.member_runs:
        print("\n=== 成员执行记录 ===")
        for run in result.member_runs:
            print(f"\n[{run.member_name}] ({run.member_role})")
            print(f"任务: {run.task}")
            response_preview = (
                run.response[:200] + "..." if len(run.response) > 200 else run.response
            )
            print(f"结果: {response_preview}")

    print(f"\n文件已保存在: {workspace_path}")


if __name__ == "__main__":
    asyncio.run(main())
