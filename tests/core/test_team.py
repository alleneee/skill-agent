"""Tests for Team functionality."""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from fastapi_agent.core.team import Team
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig, TaskWithDependencies
from fastapi_agent.tools.file_tools import ReadTool, WriteTool


@pytest.fixture
def llm_client():
    """Create a mock LLM client."""
    client = Mock(spec=LLMClient)
    return client


@pytest.fixture
def sample_team_config():
    """Create a sample team configuration."""
    return TeamConfig(
        name="Research Team",
        description="A team for research tasks",
        members=[
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="Information gathering specialist",
                instructions="Find and summarize information",
                tools=[]
            ),
            TeamMemberConfig(
                id="writer",
                name="Writer",
                role="Documentation specialist",
                instructions="Create clear documentation",
                tools=["write_file"]
            )
        ],
        model="openai:gpt-4o-mini"
    )


@pytest.fixture
def available_tools():
    """Create list of available tools."""
    return [
        ReadTool(),
        WriteTool()
    ]


def test_team_initialization(llm_client, sample_team_config, available_tools):
    """Test team initialization."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    assert team.config.name == "Research Team"
    assert len(team.config.members) == 2
    assert team.team_id is not None
    assert team.member_runs == []
    assert team.iteration_count == 0


# NOTE: Tests for DelegateTaskTool and DelegateToAllTool have been removed
# The delegation mechanism now uses dynamic closure functions created at runtime
# in Team.run(), inspired by agno's implementation. See test_dynamic_tools.py
# for tests of the new mechanism.


def test_build_leader_system_prompt(llm_client, sample_team_config, available_tools):
    """Test building leader system prompt."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    prompt = team._build_leader_system_prompt()

    # Check key sections
    assert "Research Team" in prompt
    assert "Researcher" in prompt
    assert "Writer" in prompt
    assert "delegate_task_to_member" in prompt
    assert "Information gathering specialist" in prompt
    assert "Documentation specialist" in prompt


def test_build_leader_system_prompt_delegate_all(llm_client, available_tools):
    """Test building leader system prompt for delegate-to-all mode."""
    config = TeamConfig(
        name="Creative Team",
        description="Creative brainstorming",
        members=[
            TeamMemberConfig(id="creative", name="Member1", role="Creative"),
            TeamMemberConfig(id="analytical", name="Member2", role="Analytical")
        ],
        delegate_to_all=True,
        leader_instructions="Focus on innovative solutions"
    )

    team = Team(
        config=config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    prompt = team._build_leader_system_prompt()

    assert "delegate_task_to_all_members" in prompt
    assert "ALL team members" in prompt.lower()
    assert "Focus on innovative solutions" in prompt


def test_run_member_success(llm_client, sample_team_config, available_tools):
    """Test running a team member successfully."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    # Mock agent run
    mock_response = {
        "success": True,
        "message": "Research completed",
        "steps": 3
    }

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = mock_response
        MockAgent.return_value = mock_agent_instance

        member_config = sample_team_config.members[0]
        result = team._run_member(member_config, "Find information about Python")

        assert result.success is True
        assert result.member_name == "Researcher"
        assert result.response == "Research completed"
        assert result.steps == 3
        assert len(team.member_runs) == 1


def test_run_member_with_tools(llm_client, sample_team_config, available_tools):
    """Test running a team member with specific tools."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    mock_response = {
        "success": True,
        "message": "File written",
        "steps": 2
    }

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = mock_response
        MockAgent.return_value = mock_agent_instance

        # Writer has write_file tool
        member_config = sample_team_config.members[1]
        result = team._run_member(member_config, "Write documentation")

        # Check that agent was created with write_file tool
        call_args = MockAgent.call_args
        agent_tools = call_args[1]["tools"]

        assert result.success is True
        assert result.member_name == "Writer"


def test_run_member_error(llm_client, sample_team_config, available_tools):
    """Test handling member run error."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        MockAgent.side_effect = Exception("Agent failed")

        member_config = sample_team_config.members[0]
        result = team._run_member(member_config, "Some task")

        assert result.success is False
        assert result.error == "Agent failed"
        assert len(team.member_runs) == 1


def test_team_run_integration(llm_client, sample_team_config, available_tools):
    """Test full team run integration."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    # Mock leader agent run
    mock_leader_response = {
        "success": True,
        "message": "Task completed by delegating to team members",
        "steps": 5
    }

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = mock_leader_response
        MockAgent.return_value = mock_agent_instance

        response = team.run("Research Python and create documentation")

        assert response.success is True
        assert response.team_name == "Research Team"
        assert response.message == "Task completed by delegating to team members"
        assert "leader_response" in response.metadata
        assert "team_config" in response.metadata


def test_resolve_dependencies_simple_chain(llm_client, sample_team_config, available_tools):
    """Test resolving dependencies for a simple linear chain."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="task1", task="First", assigned_to="Researcher"),
        TaskWithDependencies(id="task2", task="Second", assigned_to="Writer", depends_on=["task1"]),
        TaskWithDependencies(id="task3", task="Third", assigned_to="Researcher", depends_on=["task2"])
    ]

    layers = team._resolve_dependencies(tasks)

    assert len(layers) == 3
    assert len(layers[0]) == 1
    assert layers[0][0].id == "task1"
    assert len(layers[1]) == 1
    assert layers[1][0].id == "task2"
    assert len(layers[2]) == 1
    assert layers[2][0].id == "task3"


def test_resolve_dependencies_parallel(llm_client, sample_team_config, available_tools):
    """Test resolving dependencies with parallel tasks."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="task1", task="Root", assigned_to="Researcher"),
        TaskWithDependencies(id="task2", task="Branch1", assigned_to="Writer", depends_on=["task1"]),
        TaskWithDependencies(id="task3", task="Branch2", assigned_to="Researcher", depends_on=["task1"])
    ]

    layers = team._resolve_dependencies(tasks)

    assert len(layers) == 2
    assert len(layers[0]) == 1
    assert layers[0][0].id == "task1"
    assert len(layers[1]) == 2
    task_ids = {task.id for task in layers[1]}
    assert task_ids == {"task2", "task3"}


def test_resolve_dependencies_complex_dag(llm_client, sample_team_config, available_tools):
    """Test resolving dependencies for a complex DAG."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="t1", task="Research", assigned_to="Researcher"),
        TaskWithDependencies(id="t2", task="Analyze", assigned_to="Researcher", depends_on=["t1"]),
        TaskWithDependencies(id="t3", task="Write", assigned_to="Writer", depends_on=["t2"]),
        TaskWithDependencies(id="t4", task="Code", assigned_to="Researcher", depends_on=["t2"]),
        TaskWithDependencies(id="t5", task="Review", assigned_to="Writer", depends_on=["t3", "t4"])
    ]

    layers = team._resolve_dependencies(tasks)

    assert len(layers) == 4
    assert layers[0][0].id == "t1"
    assert layers[1][0].id == "t2"
    assert {task.id for task in layers[2]} == {"t3", "t4"}
    assert layers[3][0].id == "t5"


def test_resolve_dependencies_circular_error(llm_client, sample_team_config, available_tools):
    """Test that circular dependencies are detected."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="task1", task="First", assigned_to="Researcher", depends_on=["task2"]),
        TaskWithDependencies(id="task2", task="Second", assigned_to="Writer", depends_on=["task1"])
    ]

    with pytest.raises(ValueError, match="Circular dependency"):
        team._resolve_dependencies(tasks)


def test_resolve_dependencies_missing_dependency(llm_client, sample_team_config, available_tools):
    """Test that missing dependencies are detected."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="task1", task="First", assigned_to="Researcher", depends_on=["nonexistent"])
    ]

    with pytest.raises(ValueError, match="non-existent"):
        team._resolve_dependencies(tasks)


@pytest.mark.asyncio
async def test_execute_task_with_context(llm_client, sample_team_config, available_tools):
    """Test executing a task with dependency context."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    task = TaskWithDependencies(
        id="task2",
        task="Analyze results",
        assigned_to="Information gathering specialist",
        depends_on=["task1"]
    )

    completed_results = {
        "task1": "Research findings: Python is great"
    }

    with patch.object(team, '_run_member', new_callable=AsyncMock) as mock_run_member:
        from fastapi_agent.schemas.team import MemberRunResult
        mock_run_member.return_value = MemberRunResult(
            member_name="Researcher",
            member_role="Information gathering specialist",
            task="Analyze results",
            response="Analysis complete",
            success=True,
            steps=2
        )

        result = await team._execute_task_with_context(task, completed_results)

        assert result.status == "completed"
        assert result.result == "Analysis complete"
        assert "task1" in mock_run_member.call_args[0][1]


@pytest.mark.asyncio
async def test_execute_task_member_not_found(llm_client, sample_team_config, available_tools):
    """Test executing a task with non-existent member role."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    task = TaskWithDependencies(
        id="task1",
        task="Do something",
        assigned_to="NonExistentRole"
    )

    result = await team._execute_task_with_context(task, {})

    assert result.status == "failed"
    assert "NonExistentRole" in result.result


@pytest.mark.asyncio
async def test_run_with_dependencies_success(llm_client, sample_team_config, available_tools):
    """Test successful execution of dependency-based workflow."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="research", task="Research topic", assigned_to="Information gathering specialist"),
        TaskWithDependencies(id="write", task="Write article", assigned_to="Documentation specialist", depends_on=["research"])
    ]

    with patch.object(team, '_run_member', new_callable=AsyncMock) as mock_run_member:
        from fastapi_agent.schemas.team import MemberRunResult

        async def mock_run_side_effect(member_config, task_desc, session_id=None):
            if "Research" in task_desc:
                return MemberRunResult(
                    member_name="Researcher",
                    member_role="Information gathering specialist",
                    task=task_desc,
                    response="Research complete: Findings here",
                    success=True,
                    steps=3
                )
            else:
                return MemberRunResult(
                    member_name="Writer",
                    member_role="Documentation specialist",
                    task=task_desc,
                    response="Article written",
                    success=True,
                    steps=2
                )

        mock_run_member.side_effect = mock_run_side_effect

        result = await team.run_with_dependencies(tasks)

        assert result.success is True
        assert len(result.tasks) == 2
        assert result.tasks[0].status == "completed"
        assert result.tasks[1].status == "completed"
        assert len(result.execution_order) == 2
        assert result.execution_order[0] == ["research"]
        assert result.execution_order[1] == ["write"]


@pytest.mark.asyncio
async def test_run_with_dependencies_failure_stops_dependents(llm_client, sample_team_config, available_tools):
    """Test that task failure stops dependent tasks."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tasks = [
        TaskWithDependencies(id="t1", task="Task 1", assigned_to="Information gathering specialist"),
        TaskWithDependencies(id="t2", task="Task 2", assigned_to="Documentation specialist", depends_on=["t1"])
    ]

    with patch.object(team, '_run_member', new_callable=AsyncMock) as mock_run_member:
        from fastapi_agent.schemas.team import MemberRunResult
        mock_run_member.return_value = MemberRunResult(
            member_name="Researcher",
            member_role="Information gathering specialist",
            task="Task 1",
            response="",
            success=False,
            error="Task failed",
            steps=1
        )

        result = await team.run_with_dependencies(tasks)

        assert result.success is False
        assert tasks[0].status == "failed"
        assert tasks[1].status == "skipped"
        assert "dependency failure" in tasks[1].result.lower()
