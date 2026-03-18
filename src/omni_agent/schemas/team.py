"""多 Agent 协作的团队模式。"""

from typing import Any

from pydantic import BaseModel, Field


class TeamMemberConfig(BaseModel):
    """Configuration for a team member."""

    id: str = Field(
        ..., description="Unique member identifier (e.g., 'hn_researcher', 'article_reader')"
    )
    name: str = Field(..., description="Team member name")
    role: str = Field(..., description="Team member role/specialty")
    instructions: str | None = Field(None, description="Specific instructions for this member")
    tools: list[str] | None = Field(
        default_factory=list, description="Tools available to this member"
    )
    model: str | None = Field(
        None, description="LLM model for this member (defaults to team model)"
    )


class TeamConfig(BaseModel):
    """Configuration for a team of agents."""

    name: str = Field(..., description="Team name")
    description: str | None = Field(None, description="Team description")
    members: list[TeamMemberConfig] = Field(..., description="Team members")
    model: str | None = Field("openai:gpt-4o-mini", description="Default model for the team")
    leader_instructions: str | None = Field(
        None, description="Instructions for the team leader on how to delegate tasks"
    )
    delegate_to_all: bool = Field(
        False,
        description="If True, delegate tasks to all members instead of selecting specific ones",
    )
    max_iterations: int = Field(10, description="Maximum number of delegation iterations")


class TeamRunRequest(BaseModel):
    """Request to run a team."""

    message: str = Field(..., description="User message/task")
    team_config: TeamConfig | None = Field(
        None, description="Team configuration (if creating new team)"
    )
    team_id: str | None = Field(None, description="Existing team ID to use")
    workspace_dir: str | None = Field("./workspace", description="Workspace directory")
    max_steps: int = Field(50, description="Max steps per agents")
    stream: bool = Field(False, description="Whether to stream responses")


class MemberRunResult(BaseModel):
    """Result from a team member run."""

    member_name: str
    member_role: str
    task: str
    response: str
    success: bool
    error: str | None = None
    steps: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeamRunResponse(BaseModel):
    """Response from team run."""

    success: bool
    team_name: str
    message: str
    member_runs: list[MemberRunResult] = Field(default_factory=list)
    total_steps: int = 0
    iterations: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskWithDependencies(BaseModel):
    """Task with dependency relationships."""

    id: str = Field(..., description="Unique task ID")
    task: str = Field(..., description="Task description")
    assigned_to: str = Field(..., description="Member role to assign this task to")
    depends_on: list[str] = Field(
        default_factory=list, description="List of task IDs this task depends on"
    )
    status: str = Field("pending", description="Task status: pending, running, completed, failed")
    result: str | None = Field(None, description="Task execution result")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional task metadata")


class DependencyRunRequest(BaseModel):
    """Request to run team with dependency-based tasks."""

    tasks: list[TaskWithDependencies] = Field(..., description="List of tasks with dependencies")
    team_config: TeamConfig | None = Field(
        None, description="Team configuration (if creating new team)"
    )
    team_id: str | None = Field(None, description="Existing team ID to use")
    workspace_dir: str | None = Field("./workspace", description="Workspace directory")
    session_id: str | None = Field(None, description="Session ID for context tracking")
    user_id: str | None = Field(None, description="User ID")


class DependencyRunResponse(BaseModel):
    """Response from dependency-based team run."""

    success: bool
    team_name: str
    message: str
    tasks: list[TaskWithDependencies] = Field(
        default_factory=list, description="Task execution results with status"
    )
    execution_order: list[list[str]] = Field(
        default_factory=list, description="Execution layers (for visualization)"
    )
    total_steps: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
