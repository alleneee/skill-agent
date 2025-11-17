"""API v1 router aggregating all v1 endpoints."""

from fastapi import APIRouter

from fastapi_agent.api.v1.endpoints import agent, health, team, tools

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(team.router, tags=["team"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])

# Health endpoint at root level (not versioned)
health_router = APIRouter()
health_router.include_router(health.router, tags=["health"])
