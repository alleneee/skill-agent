"""斜杠命令的 CLI 命令处理器。"""

from datetime import datetime
from typing import TYPE_CHECKING

from omni_agent.cli.display import Colors, print_stats

if TYPE_CHECKING:
    from omni_agent.core.agent import Agent


AVAILABLE_COMMANDS = [
    "/help",
    "/clear",
    "/history",
    "/stats",
    "/tools",
    "/session",
    "/exit",
    "/quit",
    "/q",
]


def print_help() -> None:
    """Print help information."""
    help_text = f"""
{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Commands:{Colors.RESET}
  {Colors.BRIGHT_GREEN}/help{Colors.RESET}      - Show this help message
  {Colors.BRIGHT_GREEN}/clear{Colors.RESET}     - Clear session history (keep system prompt)
  {Colors.BRIGHT_GREEN}/history{Colors.RESET}   - Show current session message count
  {Colors.BRIGHT_GREEN}/stats{Colors.RESET}     - Show session statistics
  {Colors.BRIGHT_GREEN}/tools{Colors.RESET}     - List available tools
  {Colors.BRIGHT_GREEN}/session{Colors.RESET}   - Show session info
  {Colors.BRIGHT_GREEN}/exit{Colors.RESET}      - Exit program (also: /quit, /q, exit, quit, q)

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Keyboard Shortcuts:{Colors.RESET}
  {Colors.BRIGHT_CYAN}Ctrl+O{Colors.RESET}     - Toggle thinking display (during agents execution)
  {Colors.BRIGHT_CYAN}Ctrl+U{Colors.RESET}     - Clear current input line
  {Colors.BRIGHT_CYAN}Ctrl+L{Colors.RESET}     - Clear screen
  {Colors.BRIGHT_CYAN}Ctrl+J{Colors.RESET}     - Insert newline (multi-line input)
  {Colors.BRIGHT_CYAN}Tab{Colors.RESET}        - Auto-complete commands
  {Colors.BRIGHT_CYAN}Up/Down{Colors.RESET}    - Browse command history
  {Colors.BRIGHT_CYAN}Right{Colors.RESET}      - Accept auto-suggestion

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Usage:{Colors.RESET}
  - Enter your task directly, Agent will help you complete it
  - Agent remembers all conversation in this session
  - Use {Colors.BRIGHT_GREEN}/clear{Colors.RESET} to start a new session
  - Press {Colors.BRIGHT_CYAN}Enter{Colors.RESET} to submit your message
  - Use {Colors.BRIGHT_CYAN}Ctrl+J{Colors.RESET} to insert line breaks
"""
    print(help_text)


def handle_clear(agent: "Agent") -> int:
    """Clear message history, keep system prompt.

    Args:
        agent: Agent instance

    Returns:
        Number of messages cleared
    """
    old_count = len(agent.messages)
    agent.messages = [agent.messages[0]]  # Keep only system message
    return old_count - 1


def handle_history(agent: "Agent") -> None:
    """Show message history count.

    Args:
        agent: Agent instance
    """
    # Count by type
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")
    system_msgs = sum(1 for m in agent.messages if m.role == "system")

    print(f"\n{Colors.BRIGHT_CYAN}Message History:{Colors.RESET}")
    print(f"  Total: {len(agent.messages)} messages")
    print(f"    - System: {Colors.DIM}{system_msgs}{Colors.RESET}")
    print(f"    - User: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - Assistant: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    print(f"    - Tool: {Colors.BRIGHT_YELLOW}{tool_msgs}{Colors.RESET}")
    print()


def handle_tools(agent: "Agent") -> None:
    """List all available tools.

    Args:
        agent: Agent instance
    """
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Available Tools ({len(agent.tools)}):{Colors.RESET}")
    for name, tool in agent.tools.items():
        desc = tool.description
        if len(desc) > 60:
            desc = desc[:60] + "..."
        print(f"  {Colors.BRIGHT_GREEN}{name}{Colors.RESET}: {Colors.DIM}{desc}{Colors.RESET}")
    print()


def handle_session(session_id: str, workspace_dir: str) -> None:
    """Show current session info.

    Args:
        session_id: Session identifier
        workspace_dir: Workspace directory path
    """
    print(f"\n{Colors.BRIGHT_CYAN}Session Info:{Colors.RESET}")
    print(f"  Session ID: {Colors.BRIGHT_GREEN}{session_id}{Colors.RESET}")
    print(f"  Workspace: {Colors.DIM}{workspace_dir}{Colors.RESET}")
    print(f"  Time: {Colors.DIM}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
    print()


def handle_stats_command(
    agent: "Agent",
    session_start: datetime,
    tool_calls_count: int,
) -> None:
    """Handle /stats command.

    Args:
        agent: Agent instance
        session_start: Session start time
        tool_calls_count: Total tool calls
    """
    print_stats(agent, session_start, tool_calls_count)
