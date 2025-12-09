"""Team schemas for multi-agent collaboration."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class TeamMemberConfig(BaseModel):
    """Configuration for a team member."""

    id: str = Field(..., description="Unique member identifier (e.g., 'hn_researcher', 'article_reader')")
    name: str = Field(..., description="Team member name")
    role: str = Field(..., description="Team member role/specialty")
    instructions: Optional[str] = Field(None, description="Specific instructions for this member")
    tools: Optional[List[str]] = Field(default_factory=list, description="Tools available to this member")
    model: Optional[str] = Field(None, description="LLM model for this member (defaults to team model)")


class TeamConfig(BaseModel):
    """Configuration for a team of agents."""

    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    members: List[TeamMemberConfig] = Field(..., description="Team members")
    model: Optional[str] = Field("openai:gpt-4o-mini", description="Default model for the team")
    leader_instructions: Optional[str] = Field(
        None,
        description="Instructions for the team leader on how to delegate tasks"
    )
    delegate_to_all: bool = Field(
        False,
        description="If True, delegate tasks to all members instead of selecting specific ones"
    )
    max_iterations: int = Field(
        10,
        description="Maximum number of delegation iterations"
    )


class TeamRunRequest(BaseModel):
    """Request to run a team."""

    message: str = Field(..., description="User message/task")
    team_config: Optional[TeamConfig] = Field(None, description="Team configuration (if creating new team)")
    team_id: Optional[str] = Field(None, description="Existing team ID to use")
    workspace_dir: Optional[str] = Field("./workspace", description="Workspace directory")
    max_steps: int = Field(50, description="Max steps per agent")
    stream: bool = Field(False, description="Whether to stream responses")


class MemberRunResult(BaseModel):
    """Result from a team member run."""

    member_name: str
    member_role: str
    task: str
    response: str
    success: bool
    error: Optional[str] = None
    steps: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TeamRunResponse(BaseModel):
    """Response from team run."""

    success: bool
    team_name: str
    message: str
    member_runs: List[MemberRunResult] = Field(default_factory=list)
    total_steps: int = 0
    iterations: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskWithDependencies(BaseModel):
    """Task with dependency relationships."""

    id: str = Field(..., description="Unique task ID")
    task: str = Field(..., description="Task description")
    assigned_to: str = Field(..., description="Member role to assign this task to")
    depends_on: List[str] = Field(default_factory=list, description="List of task IDs this task depends on")
    status: str = Field("pending", description="Task status: pending, running, completed, failed")
    result: Optional[str] = Field(None, description="Task execution result")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional task metadata")


class DependencyRunRequest(BaseModel):
    """Request to run team with dependency-based tasks."""

    tasks: List[TaskWithDependencies] = Field(..., description="List of tasks with dependencies")
    team_config: Optional[TeamConfig] = Field(None, description="Team configuration (if creating new team)")
    team_id: Optional[str] = Field(None, description="Existing team ID to use")
    workspace_dir: Optional[str] = Field("./workspace", description="Workspace directory")
    session_id: Optional[str] = Field(None, description="Session ID for context tracking")
    user_id: Optional[str] = Field(None, description="User ID")


class DependencyRunResponse(BaseModel):
    """Response from dependency-based team run."""

    success: bool
    team_name: str
    message: str
    tasks: List[TaskWithDependencies] = Field(default_factory=list, description="Task execution results with status")
    execution_order: List[List[str]] = Field(default_factory=list, description="Execution layers (for visualization)")
    total_steps: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
