"""
预设 Agents

提供开箱即用的 Agent 配置
"""

from .general_agent import (
    create_general_agent,
    create_general_agent_sync,
    GeneralAgentConfig,
    LLMConfig,
)

__all__ = [
    "create_general_agent",
    "create_general_agent_sync",
    "GeneralAgentConfig",
    "LLMConfig",
]
