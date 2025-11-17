"""
Tests for AgentTeam multi-agent coordination
"""

import pytest
from unittest.mock import Mock, patch

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import (
    AgentTeam,
    CoordinationStrategy,
    TeamRunResult,
    MemberInteraction
)


class MockLLMClient:
    """Mock LLM client for testing"""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    def chat_completion(self, messages, **kwargs):
        """Mock chat completion"""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response
                    }
                }]
            }
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Default response"
                }
            }]
        }


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client"""
    return MockLLMClient()


@pytest.fixture
def sample_agents(mock_llm_client):
    """Create sample agents for testing"""
    researcher = Agent(
        llm_client=mock_llm_client,
        name="Researcher",
        system_prompt="You are a researcher",
        max_steps=5
    )

    writer = Agent(
        llm_client=mock_llm_client,
        name="Writer",
        system_prompt="You are a writer",
        max_steps=5
    )

    return [researcher, writer]


@pytest.fixture
def coordinator_agent(mock_llm_client):
    """Create a coordinator agent"""
    return Agent(
        llm_client=mock_llm_client,
        name="Coordinator",
        system_prompt="You are a coordinator",
        max_steps=5
    )


def test_agent_team_initialization(sample_agents, coordinator_agent):
    """Test AgentTeam initialization"""
    team = AgentTeam(
        members=sample_agents,
        strategy=CoordinationStrategy.LEADER_WORKER,
        coordinator=coordinator_agent,
        name="TestTeam",
        share_interactions=True,
        max_steps=20,
        enable_logging=False
    )

    assert team.name == "TestTeam"
    assert len(team.members) == 2
    assert team.strategy == CoordinationStrategy.LEADER_WORKER
    assert team.coordinator is not None
    assert team.share_interactions is True
    assert team.max_steps == 20


def test_agent_team_requires_members():
    """Test that AgentTeam requires at least one member"""
    with pytest.raises(ValueError, match="at least one member"):
        AgentTeam(members=[], strategy=CoordinationStrategy.BROADCAST)


def test_leader_worker_requires_coordinator(sample_agents):
    """Test that LEADER_WORKER strategy requires a coordinator"""
    with pytest.raises(ValueError, match="requires a coordinator"):
        AgentTeam(
            members=sample_agents,
            strategy=CoordinationStrategy.LEADER_WORKER,
            coordinator=None
        )


def test_sequential_strategy(sample_agents):
    """Test SEQUENTIAL coordination strategy"""
    # Set up mock responses
    mock_client = MockLLMClient(responses=[
        "Research result: Python is great",
        "Article: Python is an excellent language"
    ])

    # Recreate agents with the new mock client
    agents = [
        Agent(llm_client=mock_client, name="Researcher", max_steps=5),
        Agent(llm_client=mock_client, name="Writer", max_steps=5)
    ]

    team = AgentTeam(
        members=agents,
        strategy=CoordinationStrategy.SEQUENTIAL,
        enable_logging=False
    )

    result = team.run(message="Write about Python", workspace_dir="./test_workspace")

    assert result.success is True
    assert len(result.member_outputs) == 2
    assert "Researcher" in result.member_outputs
    assert "Writer" in result.member_outputs
    assert result.steps == 2


def test_broadcast_strategy(sample_agents):
    """Test BROADCAST coordination strategy"""
    # Set up mock responses
    mock_client = MockLLMClient(responses=[
        "Perspective 1: Python is dynamically typed",
        "Perspective 2: Python has great libraries"
    ])

    agents = [
        Agent(llm_client=mock_client, name="Agent1", max_steps=5),
        Agent(llm_client=mock_client, name="Agent2", max_steps=5)
    ]

    team = AgentTeam(
        members=agents,
        strategy=CoordinationStrategy.BROADCAST,
        enable_logging=False
    )

    result = team.run(message="Analyze Python", workspace_dir="./test_workspace")

    assert result.success is True
    assert len(result.member_outputs) == 2
    assert "Agent1" in result.member_outputs
    assert "Agent2" in result.member_outputs


def test_member_interaction_recording(sample_agents):
    """Test that member interactions are recorded"""
    mock_client = MockLLMClient(responses=[
        "Result 1",
        "Result 2"
    ])

    agents = [
        Agent(llm_client=mock_client, name="Agent1", max_steps=5),
        Agent(llm_client=mock_client, name="Agent2", max_steps=5)
    ]

    team = AgentTeam(
        members=agents,
        strategy=CoordinationStrategy.SEQUENTIAL,
        share_interactions=True,
        enable_logging=False
    )

    result = team.run(message="Test task", workspace_dir="./test_workspace")

    assert len(result.interactions) == 2
    assert isinstance(result.interactions[0], MemberInteraction)
    assert result.interactions[0].member_name == "Agent1"
    assert result.interactions[1].member_name == "Agent2"


def test_interaction_sharing(sample_agents):
    """Test that interactions are shared between members when enabled"""
    team = AgentTeam(
        members=sample_agents,
        strategy=CoordinationStrategy.SEQUENTIAL,
        share_interactions=True,
        enable_logging=False
    )

    # Add some interactions
    team._log_interaction("Agent1", "input1", "output1", 1)
    team._log_interaction("Agent2", "input2", "output2", 2)

    # Get interaction context
    context = team._get_interaction_context()

    assert "Agent1" in context
    assert "Agent2" in context
    assert "团队成员交互历史" in context


def test_leader_worker_plan_parsing():
    """Test coordination plan parsing"""
    mock_client = MockLLMClient(responses=[
        '''```json
        {
            "analysis": "Task analysis",
            "plan": [
                {"member": "Researcher", "task": "Research topic", "dependencies": []},
                {"member": "Writer", "task": "Write article", "dependencies": ["Researcher"]}
            ],
            "final_synthesis": "Combine outputs"
        }
        ```''',
        "Research completed",
        "Article written",
        "Final summary"
    ])

    agents = [
        Agent(llm_client=mock_client, name="Researcher", max_steps=5),
        Agent(llm_client=mock_client, name="Writer", max_steps=5)
    ]

    coordinator = Agent(llm_client=mock_client, name="Coordinator", max_steps=5)

    team = AgentTeam(
        members=agents,
        strategy=CoordinationStrategy.LEADER_WORKER,
        coordinator=coordinator,
        enable_logging=False
    )

    result = team.run(message="Create article", workspace_dir="./test_workspace")

    assert result.success is True
    assert "plan" in result.metadata
    assert len(result.metadata["plan"]["plan"]) == 2


def test_team_run_result_to_dict():
    """Test TeamRunResult serialization"""
    interaction = MemberInteraction(
        member_name="TestAgent",
        input_message="test input",
        output_message="test output",
        timestamp="2024-01-01 00:00:00",
        step=1
    )

    result = TeamRunResult(
        success=True,
        final_output="Final result",
        member_outputs={"Agent1": "output1"},
        interactions=[interaction],
        steps=3,
        logs=[],
        shared_state={"key": "value"}
    )

    result_dict = result.to_dict()

    assert result_dict["success"] is True
    assert result_dict["final_output"] == "Final result"
    assert "Agent1" in result_dict["member_outputs"]
    assert len(result_dict["interactions"]) == 1
    assert result_dict["steps"] == 3
    assert result_dict["shared_state"]["key"] == "value"


def test_member_info_formatting(sample_agents):
    """Test formatting of member information"""
    team = AgentTeam(
        members=sample_agents,
        strategy=CoordinationStrategy.BROADCAST,
        enable_logging=False
    )

    info = team._format_member_info()

    assert "Researcher" in info
    assert "Writer" in info


def test_max_steps_limit():
    """Test that max_steps limit is enforced"""
    mock_client = MockLLMClient(responses=["Response"] * 100)

    agents = [Agent(llm_client=mock_client, name=f"Agent{i}", max_steps=5) for i in range(10)]

    team = AgentTeam(
        members=agents,
        strategy=CoordinationStrategy.SEQUENTIAL,
        max_steps=3,  # Limit to 3 steps
        enable_logging=False
    )

    result = team.run(message="Test task", workspace_dir="./test_workspace")

    # Should stop at max_steps, not process all agents
    assert result.steps <= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
