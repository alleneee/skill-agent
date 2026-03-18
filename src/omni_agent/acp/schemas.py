"""ACP（Agent 客户端协议）数据模式。

基于 Zed 的 Agent 客户端协议：
- 协议规范：https://agentclientprotocol.com/
- Schema：https://github.com/zed-industries/agent-client-protocol/blob/main/schema/schema.json
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JsonRpcError | None = None


class FsCapabilities(BaseModel):
    read_text_file: bool = Field(False, alias="readTextFile")
    write_text_file: bool = Field(False, alias="writeTextFile")

    class Config:
        populate_by_name = True


class ClientCapabilities(BaseModel):
    fs: FsCapabilities | None = None
    terminal: bool = False


class PromptCapabilities(BaseModel):
    image: bool = False
    audio: bool = False
    embedded_context: bool = Field(False, alias="embeddedContext")

    class Config:
        populate_by_name = True


class McpCapabilities(BaseModel):
    http: bool = False
    sse: bool = False
    stdio: bool = False


class AgentCapabilities(BaseModel):
    load_session: bool = Field(False, alias="loadSession")
    prompt_capabilities: PromptCapabilities | None = Field(None, alias="promptCapabilities")
    mcp: McpCapabilities | None = None

    class Config:
        populate_by_name = True


class AgentInfo(BaseModel):
    name: str
    title: str | None = None
    version: str | None = None


class InitializeRequest(BaseModel):
    protocol_version: str = Field(..., alias="protocolVersion")
    client_info: dict[str, str] | None = Field(None, alias="clientInfo")
    client_capabilities: ClientCapabilities | None = Field(None, alias="clientCapabilities")

    class Config:
        populate_by_name = True


class InitializeResponse(BaseModel):
    protocol_version: int = Field(1, alias="protocolVersion")
    agent_capabilities: AgentCapabilities = Field(
        default_factory=lambda: AgentCapabilities(), alias="agentCapabilities"
    )
    agent_info: AgentInfo = Field(..., alias="agentInfo")
    auth_methods: list[str] = Field(default_factory=list, alias="authMethods")

    class Config:
        populate_by_name = True


class McpServer(BaseModel):
    url: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None


class SessionNewRequest(BaseModel):
    cwd: str
    mcp_servers: list[McpServer] = Field(default_factory=list, alias="mcpServers")

    class Config:
        populate_by_name = True


class SessionMode(BaseModel):
    id: str
    name: str
    description: str | None = None


class SessionModeState(BaseModel):
    current_mode_id: str = Field(..., alias="currentModeId")
    available_modes: list[SessionMode] = Field(default_factory=list, alias="availableModes")

    class Config:
        populate_by_name = True


class SessionNewResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    modes: SessionModeState | None = None

    class Config:
        populate_by_name = True


class ContentBlockType(str, Enum):
    TEXT = "text"
    RESOURCE = "resource"
    RESOURCE_LINK = "resourceLink"
    IMAGE = "image"


class TextContent(BaseModel):
    type: str = "text"
    text: str
    annotations: Any | None = None


class ResourceContent(BaseModel):
    uri: str
    text: str | None = None
    mime_type: str | None = Field(None, alias="mimeType")

    class Config:
        populate_by_name = True


class ResourceBlock(BaseModel):
    type: str = "resource"
    resource: ResourceContent


class ResourceLinkBlock(BaseModel):
    type: str = "resourceLink"
    uri: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = Field(None, alias="mimeType")

    class Config:
        populate_by_name = True


ContentBlock = TextContent | ResourceBlock | ResourceLinkBlock


class SessionPromptRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    prompt: list[ContentBlock]

    class Config:
        populate_by_name = True


class StopReason(str, Enum):
    END_TURN = "endoftext"
    END_OF_TEXT = "endoftext"
    STOP_SEQUENCE = "stopsequence"
    TOOL_ERROR = "tool_error"
    CANCELLED = "cancelled"
    ERROR = "error"


class SessionPromptResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    response: dict[str, Any] = Field(default_factory=lambda: {"stopReason": "endoftext"})

    class Config:
        populate_by_name = True


class ToolKind(str, Enum):
    READ = "read"
    EDIT = "edit"
    DELETE = "delete"
    MOVE = "move"
    SEARCH = "search"
    EXECUTE = "execute"
    THINK = "think"
    FETCH = "fetch"
    OTHER = "other"


class ToolCallStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ERROR = "error"


class ToolCallLocation(BaseModel):
    path: str
    line: int | None = None


class DiffContent(BaseModel):
    type: str = "diff"
    path: str
    old_text: str | None = Field(None, alias="oldText")
    new_text: str = Field(..., alias="newText")

    class Config:
        populate_by_name = True


class ToolCallContent(BaseModel):
    type: str = "content"
    content: ContentBlock


class ToolCall(BaseModel):
    tool_call_id: str = Field(..., alias="toolCallId")
    title: str
    kind: ToolKind | None = None
    status: ToolCallStatus | None = None
    content: list[ToolCallContent | DiffContent] = Field(default_factory=list)
    locations: list[ToolCallLocation] = Field(default_factory=list)
    raw_input: dict[str, Any] | None = Field(None, alias="rawInput")
    raw_output: Any | None = Field(None, alias="rawOutput")

    class Config:
        populate_by_name = True


class ToolCallUpdate(BaseModel):
    tool_call_id: str = Field(..., alias="toolCallId")
    status: ToolCallStatus | None = None
    content: list[ToolCallContent | DiffContent] | None = None
    title: str | None = None
    kind: ToolKind | None = None
    locations: list[ToolCallLocation] | None = None
    raw_input: dict[str, Any] | None = Field(None, alias="rawInput")
    raw_output: Any | None = Field(None, alias="rawOutput")

    class Config:
        populate_by_name = True


class PlanEntryStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanEntryPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PlanEntry(BaseModel):
    content: str
    status: PlanEntryStatus = PlanEntryStatus.PENDING
    priority: PlanEntryPriority = PlanEntryPriority.MEDIUM


class Plan(BaseModel):
    entries: list[PlanEntry] = Field(default_factory=list)


class ContentChunk(BaseModel):
    content: ContentBlock


class SessionUpdateType(str, Enum):
    AGENT_THOUGHT_CHUNK = "agent_thought_chunk"
    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_CALL_UPDATE = "tool_call_update"


class SessionUpdate(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    update: dict[str, Any]

    class Config:
        populate_by_name = True

    @classmethod
    def thought_chunk(cls, session_id: str, text: str) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.AGENT_THOUGHT_CHUNK.value,
                "content": {"type": "text", "text": text},
            },
        )

    @classmethod
    def message_chunk(cls, session_id: str, text: str) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.AGENT_MESSAGE_CHUNK.value,
                "content": {"type": "text", "text": text},
            },
        )

    @classmethod
    def plan(cls, session_id: str, plan: Plan) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.PLAN.value,
                "entries": [e.model_dump() for e in plan.entries],
            },
        )

    @classmethod
    def tool_call(cls, session_id: str, tool: ToolCall) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.TOOL_CALL.value,
                **tool.model_dump(by_alias=True, exclude_none=True),
            },
        )

    @classmethod
    def tool_call_update(cls, session_id: str, update: ToolCallUpdate) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.TOOL_CALL_UPDATE.value,
                **update.model_dump(by_alias=True, exclude_none=True),
            },
        )
