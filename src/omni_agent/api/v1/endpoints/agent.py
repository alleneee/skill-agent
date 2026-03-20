"""Agent 执行端点。"""

import json
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from omni_agent.api.deps import (
    get_agent_session_manager,
    get_default_team,
    get_llm_client,
    get_settings,
    get_tools,
)
from omni_agent.core import Agent, LLMClient, Memory
from omni_agent.core.config import Settings
from omni_agent.core.session import AgentRunRecord
from omni_agent.core.session_manager import UnifiedAgentSessionManager
from omni_agent.core.team import Team
from omni_agent.schemas.message import AgentRequest, AgentResponse

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    team: Team = Depends(get_default_team),
    settings: Settings = Depends(get_settings),
    session_manager: UnifiedAgentSessionManager | None = Depends(get_agent_session_manager),
) -> AgentResponse:
    """执行 Agent 任务。

    使用默认 Team 执行任务，Team 包含三个专业子 Agent：
    - General: 简单任务、问答、基础文件操作
    - Coder: 代码编写、修改、调试
    - Researcher: 信息搜索、网页内容获取

    Leader 负责分析任务并委派给合适的子 Agent 执行。

    Args:
        request: Agent 请求，包含 message, session_id, user_id

    Returns:
        Agent 响应，包含结果和执行信息

    **请求示例:**
    ```json
    {
        "message": "帮我写一个快速排序算法",
        "session_id": "user-123"
    }
    ```
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    run_id = str(uuid4())

    try:
        response = await team.run(
            message=request.message,
            session_id=request.session_id,
            num_history_runs=settings.SESSION_HISTORY_RUNS,
            max_steps=settings.AGENT_MAX_STEPS,
        )

        success = response.success
        result = response.message
        steps = response.total_steps

        if request.session_id and session_manager:
            run_record = AgentRunRecord(
                run_id=run_id,
                task=request.message,
                response=result,
                success=success,
                steps=steps,
                timestamp=time.time(),
                metadata={},
            )
            await session_manager.add_run(request.session_id, run_record)

        if request.session_id:
            memory = Memory(
                user_id=request.user_id or "default",
                session_id=request.session_id,
            )
            if not memory.exists():
                memory.init_memory(context=f"Task: {request.message}")
            session = (
                await session_manager.get_session(request.session_id, "default")
                if session_manager
                else None
            )
            round_num = len(session.runs) if session else 1
            memory.append_round(round_num, request.message, result)

        return AgentResponse(
            success=success,
            message=result,
            steps=steps,
            logs=[],
            session_id=request.session_id,
            run_id=run_id,
        )

    except Exception as e:
        if request.session_id and session_manager:
            run_record = AgentRunRecord(
                run_id=run_id,
                task=request.message,
                response=f"Error: {str(e)}",
                success=False,
                steps=0,
                timestamp=time.time(),
                metadata={"error": str(e)},
            )
            await session_manager.add_run(request.session_id, run_record)

        raise HTTPException(
            status_code=500, detail="Agent execution failed due to an internal error"
        ) from e


@router.post("/run/stream")
async def run_agent_stream(
    request: AgentRequest,
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """流式执行 Agent 任务。

    使用 SSE (Server-Sent Events) 流式返回 Agent 执行过程。

    Args:
        request: Agent 请求，包含 message, user_id, session_id

    Returns:
        SSE 流，包含执行过程中的各种事件
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    tools = get_tools(settings.AGENT_WORKSPACE_DIR)
    user_id = request.user_id or "default"
    session_id = request.session_id or str(uuid4())
    enable_memory = bool(request.session_id)

    agent = Agent(
        llm_client=llm_client,
        system_prompt=settings.SYSTEM_PROMPT,
        tools=tools,
        max_steps=settings.AGENT_MAX_STEPS,
        workspace_dir=settings.AGENT_WORKSPACE_DIR,
        user_id=user_id,
        session_id=session_id,
        enable_memory=enable_memory,
        memory_base_dir="./.agent_memories",
    )

    agent.add_user_message(request.message)

    async def generate() -> AsyncIterator[str]:
        try:
            async for event in agent.run_stream():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
