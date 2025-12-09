"""
Team Demo - Multi-Agent Collaboration Example

This demo shows how to use the Team feature to coordinate multiple specialized agents.

Usage:
    # Run all demos
    uv run python examples/team_demo.py
    
    # Run specific demo
    uv run python examples/team_demo.py 1  # Research team
    uv run python examples/team_demo.py 2  # Development team
    uv run python examples/team_demo.py 3  # Brainstorm team
"""

import os
from dotenv import load_dotenv

from fastapi_agent.core.team import Team
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig
from fastapi_agent.tools.base_tools import ReadTool, WriteTool, EditTool, BashTool

# Load environment variables
load_dotenv()


def create_research_team() -> TeamConfig:
    """Create a research team configuration."""
    return TeamConfig(
        name="Research & Analysis Team",
        description="A team specialized in research, analysis, and documentation",
        members=[
            TeamMemberConfig(
                id="web_researcher",
                name="Web Researcher",
                role="Information gathering specialist",
                instructions="Your job is to find relevant information. Provide comprehensive summaries.",
                tools=[]
            ),
            TeamMemberConfig(
                id="technical_writer",
                name="Technical Writer",
                role="Documentation specialist",
                instructions="Create clear, well-structured documentation using markdown.",
                tools=["write_file"]
            )
        ],
        model="openai:gpt-4o-mini",
        leader_instructions="Delegate research to Web Researcher and documentation to Technical Writer."
    )


def main():
    """Run team demo."""
    print("=" * 80)
    print("Team Collaboration Demo")
    print("=" * 80)

    # Create LLM client
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE")
    )

    # Create team
    config = create_research_team()
    team = Team(
        config=config,
        llm_client=llm_client,
        available_tools=[WriteTool()],
        workspace_dir="./workspace"
    )

    # Run task
    task = "Research Python asyncio and create a summary document."
    print(f"\nTask: {task}\n")

    response = team.run(task)

    print(f"\nTeam: {response.team_name}")
    print(f"Success: {response.success}")
    print(f"Iterations: {response.iterations}\n")

    print("Member Contributions:")
    for run in response.member_runs:
        print(f"  - {run.member_name}: {run.task[:80]}...")

    print(f"\nFinal Response:\n{response.message}\n")


if __name__ == "__main__":
    main()
