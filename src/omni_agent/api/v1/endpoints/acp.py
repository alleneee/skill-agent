"""ACP (Agent Client Protocol) 端点模块。

实现 Zed 编辑器的 Agent Client Protocol，用于代码编辑器与 AI Agent 之间的标准化通信。
该协议基于 JSON-RPC 2.0，支持会话管理、同步/流式消息处理、工具调用等功能。

协议规范: https://agentclientprotocol.com/

主要端点:
    - POST /agents/initialize: 初始化连接，协商能力
    - POST /session/new: 创建新会话
    - POST /session/prompt: 同步处理用户提示
    - POST /session/prompt/stream: 流式处理用户提示 (SSE)
    - POST /session/cancel: 取消会话操作
    - DELETE /session/{session_id}: 删除会话
"""

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from omni_agent.acp.adapter import ACPAdapter
from omni_agent.acp.schemas import (
    JsonRpcRequest,
    JsonRpcResponse,
    ToolCallStatus,
)
from omni_agent.api.deps import (
    AgentFactory,
    get_agent_factory,
    get_llm_client,
    get_settings,
)
from omni_agent.core import LLMClient
from omni_agent.core.config import Settings
from omni_agent.schemas.message import AgentConfig, Message

router = APIRouter(prefix="/acp", tags=["ACP"])

# 会话存储: 使用内存字典存储活跃会话
# 键为 session_id，值包含 cwd(工作目录)、mcp_servers(MCP服务器列表)、messages(消息历史)
_sessions: dict[str, dict] = {}


@router.post("/agent/initialize")
async def initialize(
    request: JsonRpcRequest,
    settings: Settings = Depends(get_settings),
) -> JsonRpcResponse:
    """初始化 ACP 连接并协商能力。

    ACP 端点: POST /agents/initialize

    该端点是 ACP 协议的第一步，客户端通过此端点：
    1. 建立与 Agent 服务的连接
    2. 获取 Agent 的基本信息（名称、版本、标题）
    3. 协商双方支持的能力（capabilities）

    Args:
        request: JSON-RPC 请求对象
        settings: 应用配置

    Returns:
        包含 Agent 信息和能力的 JSON-RPC 响应
    """
    init_response = ACPAdapter.create_initialize_response(
        name="omni-agents",
        version=settings.VERSION,
        title=settings.PROJECT_NAME,
    )
    return ACPAdapter.wrap_jsonrpc_response(
        request.id,
        init_response.model_dump(by_alias=True),
    )


@router.post("/session/new")
async def create_session(
    request: JsonRpcRequest,
    settings: Settings = Depends(get_settings),
) -> JsonRpcResponse:
    """创建新的 Agent 会话。

    ACP 端点: POST /session/new

    会话是 Agent 与客户端交互的上下文容器，包含：
    - 工作目录 (cwd): Agent 文件操作的根目录
    - MCP 服务器列表: 会话可用的 MCP 工具服务
    - 消息历史: 保存对话上下文以支持多轮对话

    Args:
        request: JSON-RPC 请求，params 可包含 cwd 和 mcpServers
        settings: 应用配置

    Returns:
        包含新创建的 session_id 的 JSON-RPC 响应
    """
    params = request.params or {}
    session_id = f"sess_{uuid4().hex[:12]}"

    _sessions[session_id] = {
        "cwd": params.get("cwd", settings.AGENT_WORKSPACE_DIR),
        "mcp_servers": params.get("mcpServers", []),
        "messages": [],
    }

    response = ACPAdapter.create_session_response(session_id)
    return ACPAdapter.wrap_jsonrpc_response(
        request.id,
        response.model_dump(by_alias=True),
    )


@router.post("/session/prompt")
async def session_prompt(
    request: JsonRpcRequest,
    agent_factory: AgentFactory = Depends(get_agent_factory),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> JsonRpcResponse:
    """同步处理用户提示。

    ACP 端点: POST /session/prompt

    在指定会话中处理用户消息，等待 Agent 完成所有工具调用和响应生成后返回。
    适用于不需要实时反馈的场景。如需流式输出，请使用 /session/prompt/stream。

    处理流程:
    1. 验证 API Key 和会话有效性
    2. 将 ACP 格式的 prompt 转换为内部消息格式
    3. 创建 Agent 实例并加载会话历史
    4. 执行 Agent.run() 完成任务
    5. 更新会话消息历史并返回结果

    Args:
        request: JSON-RPC 请求，params 需包含 sessionId 和 prompt
        agent_factory: Agent 工厂，用于创建 Agent 实例
        llm_client: LLM 客户端
        settings: 应用配置

    Returns:
        包含 Agent 响应的 JSON-RPC 响应

    Errors:
        -32000: API Key 未配置
        -32001: 无效的会话 ID
        -32002: 空提示
        -32603: 内部执行错误
    """
    if not settings.LLM_API_KEY:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32000,
            message="API key not configured",
        )

    params = request.params or {}
    session_id = params.get("sessionId")
    prompt = params.get("prompt", [])

    if not session_id or session_id not in _sessions:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32001,
            message="Invalid or missing session ID",
        )

    user_message = ACPAdapter.prompt_to_internal_message(prompt)
    if not user_message:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32002,
            message="Empty prompt",
        )

    try:
        session = _sessions[session_id]
        config = AgentConfig(workspace_dir=session["cwd"])
        agent = await agent_factory.create_agent(llm_client, config, session_id=session_id)

        for msg in session["messages"]:
            agent.messages.append(Message(role=msg["role"], content=msg["content"]))

        agent.add_user_message(user_message)
        result, _ = await agent.run()

        session["messages"].append({"role": "user", "content": user_message})
        session["messages"].append({"role": "assistant", "content": result})

        response = ACPAdapter.create_prompt_response(session_id, stop_reason="endoftext")
        return ACPAdapter.wrap_jsonrpc_response(
            request.id,
            response.model_dump(by_alias=True),
        )

    except Exception as e:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32603,
            message=str(e),
        )


@router.post("/session/prompt/stream")
async def session_prompt_stream(
    request: JsonRpcRequest,
    agent_factory: AgentFactory = Depends(get_agent_factory),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    """流式处理用户提示。

    ACP 端点: POST /session/prompt/stream

    通过 Server-Sent Events (SSE) 实时推送 Agent 执行过程，包括：
    - thinking: LLM 思考过程（如果模型支持）
    - content: Agent 响应内容的增量更新
    - tool_call: 工具调用开始通知
    - tool_result: 工具执行结果

    事件格式遵循 ACP 的 session/update 规范，每个事件都是完整的 JSON-RPC 通知。

    Args:
        request: JSON-RPC 请求，params 需包含 sessionId 和 prompt
        agent_factory: Agent 工厂
        llm_client: LLM 客户端
        settings: 应用配置

    Returns:
        StreamingResponse: SSE 流，media_type 为 text/event-stream

    Raises:
        HTTPException(500): API Key 未配置
        HTTPException(400): 无效会话 ID 或空提示
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    params = request.params or {}
    session_id = params.get("sessionId")
    prompt = params.get("prompt", [])

    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    user_message = ACPAdapter.prompt_to_internal_message(prompt)
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty prompt")

    async def event_generator():
        """SSE 事件生成器，将 Agent 执行事件转换为 ACP 格式的 session/update 通知。"""
        try:
            session = _sessions[session_id]
            config = AgentConfig(workspace_dir=session["cwd"])
            agent = await agent_factory.create_agent(llm_client, config, session_id=session_id)

            # 恢复会话历史消息
            for msg in session["messages"]:
                agent.messages.append(Message(role=msg["role"], content=msg["content"]))

            agent.add_user_message(user_message)

            # 累积响应内容，用于最终保存到会话历史
            content_buffer = ""
            async for event in agent.run_stream():
                event_type = event.get("type")
                event_data = event.get("data", {})

                # 处理 LLM 思考过程事件（如 Claude 的 extended thinking）
                if event_type == "thinking":
                    update = ACPAdapter.create_thought_update(
                        session_id,
                        event_data.get("delta", ""),
                    )
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                # 处理响应内容增量事件
                elif event_type == "content":
                    delta = event_data.get("delta", "")
                    content_buffer += delta
                    update = ACPAdapter.create_message_update(session_id, delta)
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                # 处理工具调用开始事件
                elif event_type == "tool_call":
                    tool_name = event_data.get("tool", "unknown")
                    arguments = event_data.get("arguments", {})
                    tool_call_id = f"tc_{uuid4().hex[:8]}"
                    update = ACPAdapter.create_tool_call_update(
                        session_id,
                        tool_call_id,
                        tool_name,
                        arguments,
                        status=ToolCallStatus.IN_PROGRESS,
                    )
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                # 处理工具执行结果事件
                elif event_type == "tool_result":
                    tool_call_id = f"tc_{uuid4().hex[:8]}"
                    update = ACPAdapter.create_tool_result_update(
                        session_id,
                        tool_call_id,
                        success=event_data.get("success", True),
                        content=event_data.get("content"),
                        error=event_data.get("error"),
                    )
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                # 处理执行完成事件
                elif event_type == "done":
                    content_buffer = event_data.get("message", content_buffer)

            # 更新会话消息历史
            session["messages"].append({"role": "user", "content": user_message})
            session["messages"].append({"role": "assistant", "content": content_buffer})

            # 发送最终的 JSON-RPC 响应（带 id，表示请求完成）
            response = ACPAdapter.create_prompt_response(session_id, stop_reason="endoftext")
            yield f"data: {json.dumps({'jsonrpc': '2.0', 'id': request.id, 'result': response.model_dump(by_alias=True)})}\n\n"

        except Exception as e:
            error_response = ACPAdapter.wrap_jsonrpc_error(request.id, -32603, str(e))
            yield f"data: {json.dumps(error_response.model_dump())}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/session/cancel")
async def cancel_session(
    request: JsonRpcRequest,
) -> JsonRpcResponse:
    """取消会话中正在进行的操作。

    ACP 端点: POST /session/cancel

    用于中断长时间运行的 Agent 任务。当前实现仅返回取消确认，
    实际的任务中断需要在 Agent 执行循环中配合 CancellationToken 实现。

    Args:
        request: JSON-RPC 请求，params 需包含 sessionId

    Returns:
        包含 cancelled: True 的 JSON-RPC 响应

    Errors:
        -32001: 无效的会话 ID
    """
    params = request.params or {}
    session_id = params.get("sessionId")

    if not session_id or session_id not in _sessions:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32001,
            message="Invalid session ID",
        )

    return ACPAdapter.wrap_jsonrpc_response(
        request.id,
        {"cancelled": True},
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict:
    """删除会话。

    非 ACP 规范端点，用于会话清理。

    从内存中移除指定会话及其所有消息历史，释放资源。
    建议客户端在会话结束后调用此端点进行清理。

    Args:
        session_id: 要删除的会话 ID

    Returns:
        {"deleted": True} 表示删除成功

    Raises:
        HTTPException(404): 会话不存在
    """
    if session_id in _sessions:
        del _sessions[session_id]
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Session not found")
