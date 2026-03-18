"""ACP 适配器，用于在 ACP 和内部消息格式之间转换。"""

from typing import Any

from omni_agent.acp.schemas import (
    AgentCapabilities,
    AgentInfo,
    InitializeResponse,
    JsonRpcResponse,
    McpCapabilities,
    Plan,
    PlanEntry,
    PlanEntryStatus,
    PromptCapabilities,
    SessionNewResponse,
    SessionPromptResponse,
    SessionUpdate,
    TextContent,
    ToolCall,
    ToolCallLocation,
    ToolCallStatus,
    ToolCallUpdate,
    ToolKind,
)
from omni_agent.schemas.message import Message

TOOL_NAME_TO_KIND: dict[str, ToolKind] = {
    "read_file": ToolKind.READ,
    "write_file": ToolKind.EDIT,
    "edit_file": ToolKind.EDIT,
    "bash": ToolKind.EXECUTE,
    "web_search": ToolKind.FETCH,
    "search_knowledge": ToolKind.SEARCH,
}


class ACPAdapter:
    """用于在 ACP 协议和内部格式之间转换的适配器。"""

    @staticmethod
    def create_initialize_response(
        name: str = "omni-agents",
        version: str = "1.0.0",
        title: str | None = None,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocolVersion=1,
            agentCapabilities=AgentCapabilities(
                loadSession=True,
                promptCapabilities=PromptCapabilities(
                    image=False,
                    audio=False,
                    embeddedContext=True,
                ),
                mcp=McpCapabilities(
                    http=True,
                    sse=True,
                    stdio=False,
                ),
            ),
            agentInfo=AgentInfo(
                name=name,
                title=title or name,
                version=version,
            ),
            authMethods=[],
        )

    @staticmethod
    def create_session_response(session_id: str) -> SessionNewResponse:
        return SessionNewResponse(sessionId=session_id)

    @staticmethod
    def create_prompt_response(
        session_id: str,
        stop_reason: str = "endoftext",
    ) -> SessionPromptResponse:
        return SessionPromptResponse(
            sessionId=session_id,
            response={"stopReason": stop_reason},
        )

    @staticmethod
    def prompt_to_internal_message(prompt: list) -> str:
        parts = []
        for block in prompt:
            if isinstance(block, TextContent):
                parts.append(block.text)
            elif isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(block["text"])
            elif hasattr(block, "type") and block.type == "text":
                parts.append(block.text)
        return " ".join(parts)

    @staticmethod
    def internal_to_content_block(msg: Message) -> TextContent:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        return TextContent(type="text", text=content)

    @staticmethod
    def create_thought_update(session_id: str, text: str) -> SessionUpdate:
        return SessionUpdate.thought_chunk(session_id, text)

    @staticmethod
    def create_message_update(session_id: str, text: str) -> SessionUpdate:
        return SessionUpdate.message_chunk(session_id, text)

    @staticmethod
    def create_tool_call_update(
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        status: ToolCallStatus = ToolCallStatus.PENDING,
    ) -> SessionUpdate:
        kind = TOOL_NAME_TO_KIND.get(tool_name, ToolKind.OTHER)

        locations = []
        if "file_path" in arguments or "path" in arguments:
            path = arguments.get("file_path") or arguments.get("path", "")
            line = arguments.get("line") or arguments.get("offset")
            locations.append(ToolCallLocation(path=path, line=line))

        tool_call = ToolCall(
            toolCallId=tool_call_id,
            title=f"Executing {tool_name}",
            kind=kind,
            status=status,
            locations=locations,
            rawInput=arguments,
        )
        return SessionUpdate.tool_call(session_id, tool_call)

    @staticmethod
    def create_tool_result_update(
        session_id: str,
        tool_call_id: str,
        success: bool,
        content: str | None = None,
        error: str | None = None,
    ) -> SessionUpdate:
        status = ToolCallStatus.DONE if success else ToolCallStatus.ERROR
        update = ToolCallUpdate(
            toolCallId=tool_call_id,
            status=status,
            rawOutput=content if success else error,
        )
        return SessionUpdate.tool_call_update(session_id, update)

    @staticmethod
    def create_plan_update(
        session_id: str,
        entries: list[tuple[str, str]],
    ) -> SessionUpdate:
        plan_entries = []
        for content, status_str in entries:
            if status_str == "completed":
                status = PlanEntryStatus.COMPLETED
            elif status_str == "in_progress":
                status = PlanEntryStatus.IN_PROGRESS
            elif status_str == "failed":
                status = PlanEntryStatus.FAILED
            else:
                status = PlanEntryStatus.PENDING
            plan_entries.append(PlanEntry(content=content, status=status))
        return SessionUpdate.plan(session_id, Plan(entries=plan_entries))

    @staticmethod
    def wrap_jsonrpc_response(
        request_id: int | str | None,
        result: Any,
    ) -> JsonRpcResponse:
        return JsonRpcResponse(
            jsonrpc="2.0",
            id=request_id,
            result=result,
        )

    @staticmethod
    def wrap_jsonrpc_error(
        request_id: int | str | None,
        code: int,
        message: str,
        data: Any | None = None,
    ) -> JsonRpcResponse:
        from omni_agent.acp.schemas import JsonRpcError

        return JsonRpcResponse(
            jsonrpc="2.0",
            id=request_id,
            error=JsonRpcError(code=code, message=message, data=data),
        )
