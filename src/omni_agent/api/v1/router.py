"""API v1 路由器，聚合所有 v1 端点。"""

from fastapi import APIRouter, Depends

from omni_agent.api.deps import verify_api_key
from omni_agent.api.v1.endpoints import (
    acp,
    agent,
    feedback,
    health,
    knowledge,
    memory,
    team,
    tools,
    trace,
)
from omni_agent.core.config import settings

api_router = APIRouter(dependencies=[Depends(verify_api_key)])

api_router.include_router(agent.router, prefix="/agents", tags=["agents"])
api_router.include_router(team.router, tags=["team"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(trace.router, prefix="/trace", tags=["trace"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(feedback.router, prefix="/agents", tags=["feedback"])

if settings.ENABLE_ACP:
    api_router.include_router(acp.router, tags=["acp"])

health_router = APIRouter()
health_router.include_router(health.router, tags=["health"])
