"""Dependency injection for FastAPI endpoints."""

from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends

from fastapi_agent.core import Agent, LLMClient, settings
from fastapi_agent.core.config import Settings
from fastapi_agent.core.session import AgentSessionManager, TeamSessionManager
from fastapi_agent.core.session_manager import (
    UnifiedAgentSessionManager,
    UnifiedTeamSessionManager,
)
from fastapi_agent.skills import create_skill_tools
from fastapi_agent.tools import BashTool, EditTool, ReadTool, Tool, WriteTool, SpawnAgentTool
from fastapi_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async
from fastapi_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
from fastapi_agent.tools.rag_tool import RAGTool

# Global MCP tools storage (loaded at startup)
_mcp_tools: list[Tool] = []

# Global session managers (loaded at startup)
# 支持多种存储后端 (file, redis, postgres)
_agent_session_manager: Optional[UnifiedAgentSessionManager] = None
_team_session_manager: Optional[UnifiedTeamSessionManager] = None


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
        api_base=settings.LLM_API_BASE if settings.LLM_API_BASE else None,
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


async def initialize_session_manager() -> None:
    """Initialize session managers at application startup.

    This function is called during FastAPI lifespan startup to load
    both agent and team session managers with configured storage backend.

    Supports multiple backends:
    - file: JSON file storage (default)
    - redis: Redis storage (high performance)
    - postgres: PostgreSQL storage (persistent, queryable)
    """
    global _agent_session_manager, _team_session_manager

    if not settings.ENABLE_SESSION:
        print("ℹ️  Session management disabled")
        return

    backend = settings.SESSION_BACKEND.lower()
    ttl_seconds = settings.SESSION_MAX_AGE_DAYS * 86400

    try:
        if backend == "file":
            # File storage
            base_path = Path(settings.SESSION_STORAGE_PATH).expanduser()
            base_dir = base_path.parent
            base_dir.mkdir(parents=True, exist_ok=True)

            _agent_session_manager = UnifiedAgentSessionManager(
                backend="file",
                storage_path=str(base_dir / "agent_sessions.json"),
                ttl_seconds=ttl_seconds,
            )
            _team_session_manager = UnifiedTeamSessionManager(
                backend="file",
                storage_path=str(base_dir / "team_sessions.json"),
                ttl_seconds=ttl_seconds,
            )
            print(f"✅ Session managers initialized (file): {base_dir}")

        elif backend == "redis":
            # Redis storage
            _agent_session_manager = UnifiedAgentSessionManager(
                backend="redis",
                redis_host=settings.SESSION_REDIS_HOST,
                redis_port=settings.SESSION_REDIS_PORT,
                redis_db=settings.SESSION_REDIS_DB,
                redis_password=settings.SESSION_REDIS_PASSWORD or None,
                ttl_seconds=ttl_seconds,
            )
            _team_session_manager = UnifiedTeamSessionManager(
                backend="redis",
                redis_host=settings.SESSION_REDIS_HOST,
                redis_port=settings.SESSION_REDIS_PORT,
                redis_db=settings.SESSION_REDIS_DB,
                redis_password=settings.SESSION_REDIS_PASSWORD or None,
                ttl_seconds=ttl_seconds,
            )
            print(f"✅ Session managers initialized (redis): {settings.SESSION_REDIS_HOST}:{settings.SESSION_REDIS_PORT}")

        elif backend in ("postgres", "postgresql"):
            # PostgreSQL storage
            _agent_session_manager = UnifiedAgentSessionManager(
                backend="postgres",
                postgres_dsn=settings.postgres_dsn,
                postgres_table=settings.SESSION_POSTGRES_TABLE,
                ttl_seconds=ttl_seconds,
            )
            _team_session_manager = UnifiedTeamSessionManager(
                backend="postgres",
                postgres_dsn=settings.postgres_dsn,
                postgres_table=settings.SESSION_POSTGRES_TABLE,
                ttl_seconds=ttl_seconds,
            )
            print(f"✅ Session managers initialized (postgres): {settings.POSTGRES_HOST}")

        else:
            raise ValueError(f"Unknown session backend: {backend}")

        # Auto-cleanup old sessions on startup
        agent_sessions = await _agent_session_manager.get_all_sessions()
        team_sessions = await _team_session_manager.get_all_sessions()
        agent_cleaned = await _agent_session_manager.cleanup_old_sessions(
            max_age_days=settings.SESSION_MAX_AGE_DAYS
        )
        team_cleaned = await _team_session_manager.cleanup_old_sessions(
            max_age_days=settings.SESSION_MAX_AGE_DAYS
        )

        print(f"   Agent sessions: {len(agent_sessions)} (cleaned {agent_cleaned} old)")
        print(f"   Team sessions: {len(team_sessions)} (cleaned {team_cleaned} old)")

    except ImportError as e:
        error_msg = f"❌ Session backend '{backend}' requires additional dependencies: {e}"
        print(error_msg)
        print("   Falling back to file storage...")
        # Fallback to file storage
        base_path = Path(settings.SESSION_STORAGE_PATH).expanduser()
        base_dir = base_path.parent
        base_dir.mkdir(parents=True, exist_ok=True)

        _agent_session_manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=str(base_dir / "agent_sessions.json"),
        )
        _team_session_manager = UnifiedTeamSessionManager(
            backend="file",
            storage_path=str(base_dir / "team_sessions.json"),
        )
        print(f"⚠️  Falling back to file storage: {base_dir}")

    except Exception as e:
        import traceback
        error_msg = f"❌ Error during session manager initialization: {e}"
        print(error_msg)
        print(traceback.format_exc())
        # Create fallback file-based session managers
        _agent_session_manager = UnifiedAgentSessionManager(backend="file")
        _team_session_manager = UnifiedTeamSessionManager(backend="file")
        print("⚠️  Falling back to default file session storage")


def get_agent_session_manager() -> Optional[UnifiedAgentSessionManager]:
    """Get global agent session manager instance.

    Returns:
        UnifiedAgentSessionManager instance or None if disabled
    """
    return _agent_session_manager


def get_session_manager() -> Optional[UnifiedTeamSessionManager]:
    """Get global team session manager instance.

    Returns:
        UnifiedTeamSessionManager instance or None if disabled
    """
    return _team_session_manager


def get_tools(workspace_dir: str | None = None) -> list[Tool]:
    """Get all available tools including base tools, MCP tools, and skill tools.

    Args:
        workspace_dir: Optional workspace directory path. If not provided,
                      uses settings.AGENT_WORKSPACE_DIR

    Returns:
        List of all available tools
    """
    # Determine workspace directory
    workspace_path = Path(workspace_dir or settings.AGENT_WORKSPACE_DIR)
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

    # Load skills if enabled
    if settings.ENABLE_SKILLS:
        skill_tools, skill_loader = create_skill_tools(settings.SKILLS_DIR)
        if skill_tools:
            tools.extend(skill_tools)

    # Add MCP tools if enabled (loaded at startup)
    if settings.ENABLE_MCP and _mcp_tools:
        tools.extend(_mcp_tools)

    # Add RAG tool if enabled
    if settings.ENABLE_RAG:
        tools.append(RAGTool())

    return tools


def get_agent(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Agent:
    """Get agent instance with configured tools.

    DEPRECATED: This method is kept for backward compatibility.
    Consider using AgentFactory.create_agent() for dynamic configuration.

    Args:
        llm_client: LLM client instance
        settings: Application settings

    Returns:
        Configured agent instance
    """
    # Determine workspace directory
    workspace_path = Path(settings.AGENT_WORKSPACE_DIR)
    workspace_path.mkdir(parents=True, exist_ok=True)

    # Get all tools
    tools = get_tools(str(workspace_path))

    # Load system prompt
    system_prompt = settings.SYSTEM_PROMPT

    # Inject skills metadata if enabled
    if settings.ENABLE_SKILLS:
        _, skill_loader = create_skill_tools(settings.SKILLS_DIR)
        if skill_loader:
            skills_metadata = skill_loader.get_skills_metadata_prompt()
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
    else:
        # Remove placeholder if skills not enabled
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    # Create agent
    return Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=settings.AGENT_MAX_STEPS,
        workspace_dir=str(workspace_path),
    )


class AgentFactory:
    """Factory for creating agents with dynamic configuration."""

    def __init__(self, settings: Settings):
        """Initialize factory with settings.

        Args:
            settings: Application settings
        """
        self.settings = settings

    async def create_agent(
        self,
        llm_client: LLMClient,
        config: Optional["AgentConfig"] = None,
    ) -> Agent:
        """Create agent with dynamic configuration.

        Args:
            llm_client: LLM client instance
            config: Dynamic agent configuration (optional)

        Returns:
            Configured agent instance
        """
        from fastapi_agent.schemas.message import AgentConfig

        # Use default config if not provided
        if config is None:
            config = AgentConfig()

        # Merge config with settings (config takes precedence)
        workspace_dir = config.workspace_dir or self.settings.AGENT_WORKSPACE_DIR
        max_steps = config.max_steps or self.settings.AGENT_MAX_STEPS
        token_limit = config.token_limit or 120000
        enable_summarization = config.enable_summarization if config.enable_summarization is not None else True

        # Prepare workspace
        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Build tool list based on configuration
        tools = await self._build_tools(config, str(workspace_path))

        # Add SpawnAgentTool if enabled (must be done after other tools are built)
        tools = self._add_spawn_agent_tool(
            tools=tools,
            config=config,
            workspace_dir=str(workspace_path),
            llm_client=llm_client,
            current_depth=0,  # Root agent starts at depth 0
        )

        # Build system prompt
        system_prompt = config.system_prompt or self.settings.SYSTEM_PROMPT

        # Inject skills metadata if enabled
        enable_skills = config.enable_skills if config.enable_skills is not None else self.settings.ENABLE_SKILLS
        if enable_skills:
            _, skill_loader = create_skill_tools(self.settings.SKILLS_DIR)
            if skill_loader:
                skills_metadata = skill_loader.get_skills_metadata_prompt()
                system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
        else:
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

        # Create agent
        return Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=max_steps,
            workspace_dir=str(workspace_path),
            token_limit=token_limit,
            enable_summarization=enable_summarization,
        )

    async def _build_tools(self, config: "AgentConfig", workspace_dir: str) -> list[Tool]:
        """Build tool list based on configuration.

        Args:
            config: Agent configuration
            workspace_dir: Workspace directory path

        Returns:
            List of configured tools
        """
        from fastapi_agent.schemas.message import AgentConfig

        tools = []

        # Base tools
        enable_base = config.enable_base_tools if config.enable_base_tools is not None else True
        if enable_base:
            # Create all base tools
            all_base_tools = [
                ReadTool(workspace_dir=workspace_dir),
                WriteTool(workspace_dir=workspace_dir),
                EditTool(workspace_dir=workspace_dir),
                BashTool(),
                SessionNoteTool(memory_file=str(Path(workspace_dir) / ".agent_memory.json")),
                RecallNoteTool(memory_file=str(Path(workspace_dir) / ".agent_memory.json")),
            ]

            # Build tool name mapping (supports both actual names and short aliases)
            base_tools_map = {}
            for tool in all_base_tools:
                base_tools_map[tool.name] = tool
                # Add short aliases for convenience
                if tool.name == "read_file":
                    base_tools_map["read"] = tool
                elif tool.name == "write_file":
                    base_tools_map["write"] = tool
                elif tool.name == "edit_file":
                    base_tools_map["edit"] = tool

            # Filter if specific tools requested
            if config.base_tools_filter:
                # Deduplicate tools (in case both alias and real name are used)
                seen = set()
                for name in config.base_tools_filter:
                    if name in base_tools_map:
                        tool = base_tools_map[name]
                        if tool.name not in seen:
                            tools.append(tool)
                            seen.add(tool.name)
            else:
                tools.extend(all_base_tools)

        # Skills
        enable_skills = config.enable_skills if config.enable_skills is not None else self.settings.ENABLE_SKILLS
        if enable_skills:
            skill_tools, _ = create_skill_tools(self.settings.SKILLS_DIR)
            if skill_tools:
                tools.extend(skill_tools)

        # MCP tools
        enable_mcp = config.enable_mcp_tools if config.enable_mcp_tools is not None else self.settings.ENABLE_MCP
        if enable_mcp:
            # Use custom MCP config if provided
            if config.mcp_config_path:
                mcp_tools = await load_mcp_tools_async(config.mcp_config_path)
            else:
                # Use global MCP tools
                mcp_tools = _mcp_tools

            # Filter if specific tools requested
            if config.mcp_tools_filter and mcp_tools:
                tools.extend([
                    tool for tool in mcp_tools
                    if tool.name in config.mcp_tools_filter
                ])
            elif mcp_tools:
                tools.extend(mcp_tools)

        # RAG tool
        enable_rag = config.enable_rag if config.enable_rag is not None else self.settings.ENABLE_RAG
        if enable_rag:
            tools.append(RAGTool())

        return tools

    def _add_spawn_agent_tool(
        self,
        tools: list[Tool],
        config: "AgentConfig",
        workspace_dir: str,
        llm_client: LLMClient,
        current_depth: int = 0,
    ) -> list[Tool]:
        """Add SpawnAgentTool to tool list if enabled.

        Args:
            tools: Current tool list
            config: Agent configuration
            workspace_dir: Workspace directory path
            llm_client: LLM client instance
            current_depth: Current nesting depth (0 for root agent)

        Returns:
            Updated tool list with SpawnAgentTool if enabled
        """
        enable_spawn = config.enable_spawn_agent if config.enable_spawn_agent is not None else self.settings.ENABLE_SPAWN_AGENT
        if not enable_spawn:
            return tools

        max_depth = config.spawn_agent_max_depth or self.settings.SPAWN_AGENT_MAX_DEPTH

        # Don't add spawn_agent if already at max depth
        if current_depth >= max_depth:
            return tools

        # Create SpawnAgentTool with current tools as parent tools
        parent_tools = {tool.name: tool for tool in tools}

        spawn_tool = SpawnAgentTool(
            llm_client=llm_client,
            parent_tools=parent_tools,
            workspace_dir=workspace_dir,
            current_depth=current_depth,
            max_depth=max_depth,
            default_max_steps=self.settings.SPAWN_AGENT_DEFAULT_MAX_STEPS,
            default_token_limit=self.settings.SPAWN_AGENT_TOKEN_LIMIT,
        )

        tools.append(spawn_tool)
        return tools


def get_agent_factory(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentFactory:
    """Get agent factory instance.

    Args:
        settings: Application settings

    Returns:
        AgentFactory instance
    """
    return AgentFactory(settings)


def get_builtin_research_team(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> "Team":
    """Get builtin web research team instance.

    Creates a team with two specialized agents:
    - Web Search Agent (uses exa MCP tools)
    - Web Spider Agent (uses firecrawl MCP tools)

    Args:
        llm_client: LLM client instance
        settings: Application settings

    Returns:
        Configured web research team
    """
    from fastapi_agent.core.builtin_teams import create_web_research_team

    # Get all available tools (including MCP tools)
    workspace_path = Path(settings.AGENT_WORKSPACE_DIR)
    workspace_path.mkdir(parents=True, exist_ok=True)
    tools = get_tools(str(workspace_path))

    # Create and return the team
    return create_web_research_team(
        llm_client=llm_client,
        available_tools=tools,
        workspace_dir=str(workspace_path),
    )

