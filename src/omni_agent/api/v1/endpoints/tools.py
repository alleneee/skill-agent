"""工具列表端点。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from omni_agent.api.deps import get_agent
from omni_agent.core.agent import Agent

router = APIRouter()


@router.get("/")
async def list_tools(
    agent: Annotated[Agent, Depends(get_agent)],
) -> dict[str, list[dict[str, str | dict]]]:
    """列出所有可用工具，包括基础工具、MCP 工具和 Skill 工具。"""
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
