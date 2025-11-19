"""Tools listing endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from fastapi_agent.core.agent import Agent
from fastapi_agent.api.deps import get_agent

router = APIRouter()


@router.get("/")
async def list_tools(
    agent: Annotated[Agent, Depends(get_agent)],
) -> dict[str, list[dict[str, str | dict]]]:
    """List available tools including MCP tools."""
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in agent.tools.values()
        ]
    }
