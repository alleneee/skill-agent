"""Message and response schemas."""

from typing import Any, Optional, List
from pydantic import BaseModel, Field


class FunctionCall(BaseModel):
    """Function call within a tool call."""
    name: str
    arguments: dict[str, Any]


class ToolCall(BaseModel):
    """Tool call from LLM."""
    id: str
    type: str = "function"
    function: FunctionCall


class Message(BaseModel):
    """Message in conversation history."""
    role: str  # system, user, assistant, tool
    content: str | list[dict[str, Any]]
    thinking: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class TokenUsage(BaseModel):
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    """Response from LLM."""
    content: str
    thinking: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"
    usage: Optional[TokenUsage] = None


class AgentConfig(BaseModel):
    """Dynamic agent configuration."""
    workspace_dir: Optional[str] = Field(None, description="Workspace directory path")
    max_steps: Optional[int] = Field(None, description="Maximum execution steps")
    system_prompt: Optional[str] = Field(None, description="Custom system prompt")
    token_limit: Optional[int] = Field(None, description="Token limit for context management")
    enable_summarization: Optional[bool] = Field(None, description="Enable auto summarization")

    # Tool selection (None = use defaults from settings)
    enable_base_tools: Optional[bool] = Field(None, description="Enable base tools (Read/Write/Edit/Bash)")
    enable_mcp_tools: Optional[bool] = Field(None, description="Enable MCP tools")
    enable_skills: Optional[bool] = Field(None, description="Enable skills system")
    enable_rag: Optional[bool] = Field(None, description="Enable RAG tool")

    # Custom tool lists
    base_tools_filter: Optional[List[str]] = Field(
        None,
        description="Specific base tools to enable (e.g., ['read', 'write']). If None, all are enabled."
    )
    mcp_tools_filter: Optional[List[str]] = Field(
        None,
        description="Specific MCP tools to enable by name. If None, all are enabled."
    )

    # MCP configuration override
    mcp_config_path: Optional[str] = Field(None, description="Custom MCP config file path")

    # Spawn Agent configuration
    enable_spawn_agent: Optional[bool] = Field(
        None,
        description="Enable spawn_agent tool for creating sub-agents"
    )
    spawn_agent_max_depth: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Maximum nesting depth for spawned agents (1-5)"
    )


class AgentRequest(BaseModel):
    """Request to agent endpoint."""
    message: str = Field(..., description="User message/task")

    # Team mode
    use_team: Optional[bool] = Field(
        False,
        description="Use builtin web research team (with web_search and web_spider agents)"
    )

    # Session management
    session_id: Optional[str] = Field(
        None,
        description="Session ID for multi-turn conversation. If provided, history context will be loaded."
    )
    num_history_runs: Optional[int] = Field(
        3,
        ge=1,
        le=20,
        description="Number of recent runs to include in history context"
    )

    # Dynamic configuration (overrides defaults)
    config: Optional[AgentConfig] = Field(
        None,
        description="Dynamic agent configuration. If not provided, uses settings defaults."
    )

    # Backward compatibility
    workspace_dir: Optional[str] = Field(None, description="DEPRECATED: Use config.workspace_dir instead")
    max_steps: Optional[int] = Field(None, description="DEPRECATED: Use config.max_steps instead")


class AgentResponse(BaseModel):
    """Response from agent endpoint."""
    success: bool
    message: str
    steps: int
    logs: List[dict[str, Any]] = []
    session_id: Optional[str] = Field(None, description="Session ID if session was used")
    run_id: Optional[str] = Field(None, description="Unique ID for this run")
