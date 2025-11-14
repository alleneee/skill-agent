"""Dependency injection for FastAPI endpoints."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends

from fastapi_agent.core import Agent, LLMClient, settings
from fastapi_agent.core.config import Settings
from fastapi_agent.skills import create_skill_tools
from fastapi_agent.tools import BashTool, EditTool, ReadTool, Tool, WriteTool
from fastapi_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async
from fastapi_agent.tools.note_tool import RecallNoteTool, SessionNoteTool

# Global MCP tools storage (loaded at startup)
_mcp_tools: list[Tool] = []


def get_settings() -> Settings:
    """Get application settings.

    Returns:
        Application settings instance
    """
    return settings


def get_llm_client(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    """Get LLM client instance.

    Args:
        settings: Application settings

    Returns:
        Configured LLM client
    """
    return LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
        model=settings.LLM_MODEL,
    )


async def initialize_mcp_tools() -> None:
    """Initialize MCP tools at application startup.

    This function is called during FastAPI lifespan startup to load
    MCP tools from the configuration file. Tools are stored in the
    global _mcp_tools list for use during request handling.
    """
    global _mcp_tools

    try:
        import sys

        # Force flush to ensure output is visible
        debug_log = open("/tmp/mcp_init_debug.log", "w")
        debug_log.write("=== MCP Initialization Debug Log ===\n")
        debug_log.write(f"ENABLE_MCP: {settings.ENABLE_MCP}\n")
        debug_log.write(f"MCP_CONFIG_PATH: {settings.MCP_CONFIG_PATH}\n")
        debug_log.flush()

        if not settings.ENABLE_MCP:
            msg = "ℹ️  MCP integration disabled"
            print(msg, flush=True)
            debug_log.write(msg + "\n")
            debug_log.close()
            return

        msg = f"🔌 Loading MCP tools from: {settings.MCP_CONFIG_PATH}"
        print(msg, flush=True)
        debug_log.write(msg + "\n")
        debug_log.flush()

        mcp_tools = await load_mcp_tools_async(settings.MCP_CONFIG_PATH)
        _mcp_tools = mcp_tools

        if mcp_tools:
            msg = f"✅ Loaded {len(mcp_tools)} MCP tools"
            print(msg, flush=True)
            debug_log.write(msg + "\n")
            for tool in mcp_tools:
                tool_msg = f"  - {tool.name}"
                print(tool_msg, flush=True)
                debug_log.write(tool_msg + "\n")
        else:
            msg = "ℹ️  No MCP tools loaded"
            print(msg, flush=True)
            debug_log.write(msg + "\n")

        debug_log.write("=== MCP Initialization Complete ===\n")
        debug_log.close()
    except Exception as e:
        import traceback
        error_msg = f"❌ Error during MCP initialization: {e}\n{traceback.format_exc()}"
        print(error_msg, flush=True)
        with open("/tmp/mcp_init_error.log", "w") as f:
            f.write(error_msg)


async def cleanup_mcp_tools() -> None:
    """Cleanup MCP connections at application shutdown.

    This function is called during FastAPI lifespan shutdown to properly
    close all MCP server connections and cleanup resources.
    """
    global _mcp_tools

    if not settings.ENABLE_MCP or not _mcp_tools:
        return

    print("🧹 Cleaning up MCP connections...")
    await cleanup_mcp_connections()
    _mcp_tools = []


def get_agent(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Agent:
    """Get agent instance with configured tools.

    Args:
        llm_client: LLM client instance
        settings: Application settings

    Returns:
        Configured agent instance
    """
    # Determine workspace directory
    workspace_path = Path(settings.AGENT_WORKSPACE_DIR)
    workspace_path.mkdir(parents=True, exist_ok=True)

    # Initialize base tools
    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        EditTool(workspace_dir=str(workspace_path)),
        BashTool(),
        SessionNoteTool(memory_file=str(workspace_path / ".agent_memory.json")),
        RecallNoteTool(memory_file=str(workspace_path / ".agent_memory.json")),
    ]

    # Load skills if enabled (Progressive Disclosure Level 1 & 2)
    system_prompt = settings.SYSTEM_PROMPT
    if settings.ENABLE_SKILLS:
        skill_tools, skill_loader = create_skill_tools(settings.SKILLS_DIR)
        if skill_tools:
            tools.extend(skill_tools)

            # Inject skills metadata into system prompt (Level 1)
            if skill_loader:
                skills_metadata = skill_loader.get_skills_metadata_prompt()
                system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
    else:
        # Remove placeholder if skills not enabled
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    # Add MCP tools if enabled (loaded at startup)
    if settings.ENABLE_MCP and _mcp_tools:
        tools.extend(_mcp_tools)
        print(f"🔌 Added {len(_mcp_tools)} MCP tools to agent")

    # Create agent
    return Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=settings.AGENT_MAX_STEPS,
        workspace_dir=str(workspace_path),
    )
