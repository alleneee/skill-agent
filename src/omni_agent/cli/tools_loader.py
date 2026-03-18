"""CLI 模式的工具加载（镜像 api/deps.py 模式）。"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from omni_agent.cli.display import Colors
from omni_agent.core.config import settings
from omni_agent.skills import SkillLoader, create_skill_tools
from omni_agent.tools import BashTool, EditTool, ReadTool, Tool, WriteTool
from omni_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async
from omni_agent.tools.note_tool import RecallNoteTool, SessionNoteTool


@contextmanager
def suppress_output():
    """Context manager to suppress stdout and stderr at OS level.

    This is necessary to suppress output from MCP server subprocesses
    which write directly to inherited file descriptors.
    """
    # Save original file descriptors
    original_stdout_fd = os.dup(1)
    original_stderr_fd = os.dup(2)

    try:
        # Open devnull
        devnull = os.open(os.devnull, os.O_WRONLY)

        # Redirect stdout and stderr to devnull
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)

        # Also redirect Python's sys.stdout/stderr
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115

        yield
    finally:
        # Restore original file descriptors
        os.dup2(original_stdout_fd, 1)
        os.dup2(original_stderr_fd, 2)
        os.close(original_stdout_fd)
        os.close(original_stderr_fd)

        # Restore Python's sys.stdout/stderr
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


async def load_cli_tools(
    workspace_dir: str,
    enable_mcp: bool = True,
    enable_skills: bool = True,
    enable_rag: bool = False,
    verbose: bool = True,
) -> tuple[list[Tool], SkillLoader | None]:
    """Load all tools for CLI mode.

    Args:
        workspace_dir: Workspace directory for file tools
        enable_mcp: Whether to load MCP tools
        enable_skills: Whether to load skill tools
        enable_rag: Whether to load RAG tool
        verbose: Whether to print loading messages (debug mode)

    Returns:
        Tuple of (tools list, skill_loader or None)
    """
    tools: list[Tool] = []
    skill_loader: SkillLoader | None = None
    workspace_path = Path(workspace_dir)
    workspace_path.mkdir(parents=True, exist_ok=True)

    # 1. Base tools (always loaded)
    if verbose:
        print(f"{Colors.BRIGHT_CYAN}Loading base tools...{Colors.RESET}")

    base_tools: list[Tool] = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        EditTool(workspace_dir=str(workspace_path)),
        BashTool(),
        SessionNoteTool(memory_file=str(workspace_path / ".agent_memory.json")),
        RecallNoteTool(memory_file=str(workspace_path / ".agent_memory.json")),
    ]
    tools.extend(base_tools)
    if verbose:
        print(f"{Colors.GREEN}Loaded {len(base_tools)} base tools{Colors.RESET}")

    # 2. Skills (if enabled)
    if enable_skills and settings.ENABLE_SKILLS:
        if verbose:
            print(f"{Colors.BRIGHT_CYAN}Loading skills...{Colors.RESET}")
        try:
            skill_tools, skill_loader = create_skill_tools(settings.SKILLS_DIR)
            if skill_tools:
                tools.extend(skill_tools)
                skill_count = len(skill_loader.loaded_skills) if skill_loader else 0
                if verbose:
                    print(f"{Colors.GREEN}Loaded {skill_count} skills{Colors.RESET}")
        except Exception as e:
            if verbose:
                print(f"{Colors.YELLOW}Warning: Failed to load skills: {e}{Colors.RESET}")

    # 3. MCP tools (if enabled)
    if enable_mcp and settings.ENABLE_MCP:
        if verbose:
            print(
                f"{Colors.BRIGHT_CYAN}Loading MCP tools from: {settings.MCP_CONFIG_PATH}{Colors.RESET}"
            )
        try:
            if verbose:
                # Load with output visible
                mcp_tools = await load_mcp_tools_async(settings.MCP_CONFIG_PATH)
            else:
                # Suppress all output from MCP server processes
                with suppress_output():
                    mcp_tools = await load_mcp_tools_async(settings.MCP_CONFIG_PATH)

            if mcp_tools:
                tools.extend(mcp_tools)
                if verbose:
                    print(f"{Colors.GREEN}Loaded {len(mcp_tools)} MCP tools{Colors.RESET}")
        except Exception as e:
            if verbose:
                print(f"{Colors.YELLOW}Warning: Failed to load MCP tools: {e}{Colors.RESET}")

    # 4. RAG tool (if enabled)
    if enable_rag and settings.ENABLE_RAG:
        if verbose:
            print(f"{Colors.BRIGHT_CYAN}Loading RAG tool...{Colors.RESET}")
        try:
            from omni_agent.tools.rag_tool import RAGTool

            tools.append(RAGTool())
            if verbose:
                print(f"{Colors.GREEN}Loaded RAG tool{Colors.RESET}")
        except Exception as e:
            if verbose:
                print(f"{Colors.YELLOW}Warning: Failed to load RAG tool: {e}{Colors.RESET}")

    if verbose:
        print()  # Empty line separator
    return tools, skill_loader


async def cleanup_tools(verbose: bool = False) -> None:
    """Cleanup tool connections (MCP, etc.).

    Args:
        verbose: Whether to print cleanup messages
    """
    if verbose:
        print(f"{Colors.BRIGHT_CYAN}Cleaning up connections...{Colors.RESET}")
    try:
        if verbose:
            await cleanup_mcp_connections()
        else:
            with suppress_output():
                await cleanup_mcp_connections()
        if verbose:
            print(f"{Colors.GREEN}Cleanup complete{Colors.RESET}")
    except Exception as e:
        if verbose:
            print(f"{Colors.YELLOW}Cleanup warning (can be ignored): {e}{Colors.RESET}")
