"""消息和响应模式。"""

from typing import Any

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


class UserInputField(BaseModel):
    """Schema for a single user input field request."""

    field_name: str = Field(..., description="The name of the field")
    field_type: str = Field(
        default="str", description="Expected type (str, int, float, bool, list, dict)"
    )
    field_description: str = Field(..., description="Description of what information is needed")
    value: Any | None = Field(
        default=None, description="Value provided by user (filled after input)"
    )


class UserInputRequest(BaseModel):
    """Request for user input - sent when agent needs additional information."""

    tool_call_id: str = Field(..., description="ID of the tool call that triggered this request")
    fields: list[UserInputField] = Field(
        default_factory=list, description="Fields requiring user input"
    )
    context: str | None = Field(default=None, description="Context explaining why input is needed")


class UserInputResponse(BaseModel):
    """User's response to an input request."""

    tool_call_id: str = Field(..., description="ID of the original tool call")
    field_values: dict[str, Any] = Field(
        default_factory=dict, description="Map of field_name to provided value"
    )


class Message(BaseModel):
    """Message in conversation history."""

    role: str  # system, user, assistant, tool
    content: str | list[dict[str, Any]]
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


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
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str = "stop"
    usage: TokenUsage | None = None


class AgentConfig(BaseModel):
    """Dynamic agent configuration."""

    workspace_dir: str | None = Field(None, description="Workspace directory path")
    max_steps: int | None = Field(None, description="Maximum execution steps")
    system_prompt: str | None = Field(None, description="Custom system prompt")
    token_limit: int | None = Field(None, description="Token limit for context management")
    enable_summarization: bool | None = Field(None, description="Enable auto summarization")

    # Tool selection (None = use defaults from settings)
    enable_base_tools: bool | None = Field(
        None, description="Enable base tools (Read/Write/Edit/Bash)"
    )
    enable_mcp_tools: bool | None = Field(None, description="Enable MCP tools")
    enable_skills: bool | None = Field(None, description="Enable skills system")
    enable_rag: bool | None = Field(None, description="Enable RAG tool")

    # Custom tool lists
    base_tools_filter: list[str] | None = Field(
        None,
        description="Specific base tools to enable (e.g., ['read', 'write']). If None, all are enabled.",
    )
    mcp_tools_filter: list[str] | None = Field(
        None, description="Specific MCP tools to enable by name. If None, all are enabled."
    )

    # MCP configuration override
    mcp_config_path: str | None = Field(None, description="Custom MCP config file path")

    # Spawn Agent configuration
    enable_spawn_agent: bool | None = Field(
        None, description="Enable spawn_agent tool for creating sub-agents"
    )
    spawn_agent_max_depth: int | None = Field(
        None, ge=1, le=5, description="Maximum nesting depth for spawned agents (1-5)"
    )


class AgentRequest(BaseModel):
    """Request to agent endpoint."""

    message: str = Field(..., description="User message/task")
    session_id: str | None = Field(None, description="Session ID for multi-turn conversation")
    user_id: str | None = Field("default", description="User ID for memory isolation")


class AgentResponse(BaseModel):
    """Response from agent endpoint."""

    success: bool
    message: str
    steps: int
    logs: list[dict[str, Any]] = []
    session_id: str | None = Field(None, description="Session ID if session was used")
    run_id: str | None = Field(None, description="Unique ID for this run")

    # Human-in-the-loop support
    requires_input: bool = Field(
        default=False, description="Whether agent is waiting for user input"
    )
    input_request: UserInputRequest | None = Field(
        default=None, description="Details of required user input (when requires_input=True)"
    )
