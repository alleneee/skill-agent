"""Agent execution endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from fastapi_agent.api.deps import get_agent, get_settings
from fastapi_agent.core import Agent
from fastapi_agent.core.config import Settings
from fastapi_agent.schemas.message import AgentRequest, AgentResponse

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    agent: Agent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    """Run agent with a task.

    Args:
        request: Agent request with message and optional parameters
        agent: Agent instance from dependency injection
        settings: Application settings

    Returns:
        Agent response with result and execution logs
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    try:
        # Add user message and run
        agent.add_user_message(request.message)
        result, logs = await agent.run()

        return AgentResponse(
            success=True,
            message=result,
            steps=len([log for log in logs if log.get("type") == "step"]),
            logs=logs,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Agent execution failed: {str(e)}"
        ) from e


@router.post("/run/stream")
async def run_agent_stream(
    request: AgentRequest,
    agent: Agent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
):
    """Run agent with streaming output using Server-Sent Events.

    Args:
        request: Agent request with message and optional parameters
        agent: Agent instance from dependency injection
        settings: Application settings

    Returns:
        StreamingResponse with SSE events
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    async def event_generator():
        """Generate SSE events from agent stream."""
        try:
            # Add user message
            agent.add_user_message(request.message)

            # Stream agent execution
            async for event in agent.run_stream():
                event_type = event.get("type")
                event_data = event.get("data", {})

                # Format as SSE
                sse_data = json.dumps({
                    "type": event_type,
                    "data": event_data,
                }, ensure_ascii=False)

                yield f"data: {sse_data}\n\n"

            # Send final done event
            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            # Send error event
            error_data = json.dumps({
                "type": "error",
                "data": {"message": str(e)},
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
