"""ANSI 颜色定义和 CLI 输出显示工具。"""

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from omni_agent.core.agent import Agent


class Colors:
    """Terminal color definitions using ANSI escape codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


def calculate_display_width(text: str) -> int:
    """Calculate display width accounting for ANSI codes and CJK characters.

    Args:
        text: Text string to measure

    Returns:
        Display width in terminal columns
    """
    # Strip ANSI codes for width calculation
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    clean_text = ansi_escape.sub("", text)

    # Account for CJK characters (width 2)
    width = 0
    for char in clean_text:
        code = ord(char)
        # CJK character ranges
        if (
            0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
            or 0x3400 <= code <= 0x4DBF  # CJK Extension A
            or 0xF900 <= code <= 0xFAFF  # CJK Compatibility
            or 0xFF00 <= code <= 0xFFEF  # Fullwidth Forms
        ):
            width += 2
        else:
            width += 1
    return width


def print_banner() -> None:
    """Print welcome banner with proper alignment."""
    BOX_WIDTH = 58
    banner_text = f"{Colors.BOLD}Omni Agent - Multi-turn Interactive Session{Colors.RESET}"
    banner_width = calculate_display_width(banner_text)

    # Center the text with proper padding
    total_padding = BOX_WIDTH - banner_width
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding

    print()
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}{'=' * (BOX_WIDTH + 2)}{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.BRIGHT_CYAN}|{Colors.RESET}"
        f"{' ' * left_padding}{banner_text}{' ' * right_padding}"
        f"{Colors.BOLD}{Colors.BRIGHT_CYAN}|{Colors.RESET}"
    )
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}{'=' * (BOX_WIDTH + 2)}{Colors.RESET}")
    print()


def print_session_info(
    agent: "Agent",
    workspace_dir: Any,
    model: str,
    tools_count: int,
) -> None:
    """Print session information box.

    Args:
        agent: Agent instance
        workspace_dir: Workspace directory path
        model: Model name
        tools_count: Number of tools loaded
    """
    BOX_WIDTH = 58

    def print_info_line(text: str) -> None:
        """Print a single info line with proper padding."""
        text_width = calculate_display_width(text)
        padding = max(0, BOX_WIDTH - 1 - text_width)
        print(f"{Colors.DIM}|{Colors.RESET} {text}{' ' * padding}{Colors.DIM}|{Colors.RESET}")

    # Top border
    print(f"{Colors.DIM}+{'-' * BOX_WIDTH}+{Colors.RESET}")

    # Header (centered)
    header_text = f"{Colors.BRIGHT_CYAN}Session Info{Colors.RESET}"
    header_width = calculate_display_width(header_text)
    header_padding_total = BOX_WIDTH - 1 - header_width
    header_padding_left = header_padding_total // 2
    header_padding_right = header_padding_total - header_padding_left
    print(
        f"{Colors.DIM}|{Colors.RESET} "
        f"{' ' * header_padding_left}{header_text}{' ' * header_padding_right}"
        f"{Colors.DIM}|{Colors.RESET}"
    )

    # Divider
    print(f"{Colors.DIM}+{'-' * BOX_WIDTH}+{Colors.RESET}")

    # Info lines
    print_info_line(f"Model: {model}")
    print_info_line(f"Workspace: {workspace_dir}")
    print_info_line(f"Message History: {len(agent.messages)} messages")
    print_info_line(f"Available Tools: {tools_count} tools")

    # Bottom border
    print(f"{Colors.DIM}+{'-' * BOX_WIDTH}+{Colors.RESET}")
    print()
    print(
        f"{Colors.DIM}Type {Colors.BRIGHT_GREEN}/help{Colors.DIM} for help, "
        f"{Colors.BRIGHT_GREEN}/exit{Colors.DIM} to quit{Colors.RESET}"
    )
    print()


def print_stats(
    agent: "Agent",
    session_start: datetime,
    tool_calls_count: int,
) -> None:
    """Print session statistics.

    Args:
        agent: Agent instance
        session_start: Session start time
        tool_calls_count: Total tool calls made
    """
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Count different types of messages
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")

    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Session Statistics:{Colors.RESET}")
    print(f"{Colors.DIM}{'-' * 40}{Colors.RESET}")
    print(f"  Session Duration: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"  Total Messages: {len(agent.messages)}")
    print(f"    - User Messages: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - Assistant Replies: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    print(f"    - Tool Results: {Colors.BRIGHT_YELLOW}{tool_msgs}{Colors.RESET}")
    print(f"  Tool Calls: {Colors.BRIGHT_MAGENTA}{tool_calls_count}{Colors.RESET}")
    print(f"{Colors.DIM}{'-' * 40}{Colors.RESET}\n")


def format_tool_call(tool_name: str, arguments: dict) -> str:
    """Format tool call for display.

    Args:
        tool_name: Name of the tool being called
        arguments: Tool arguments

    Returns:
        Formatted string for display
    """
    # Truncate arguments display
    args_str = str(arguments)
    if len(args_str) > 100:
        args_str = args_str[:100] + "..."

    return (
        f"{Colors.BRIGHT_YELLOW}[Tool]{Colors.RESET} "
        f"{Colors.BOLD}{tool_name}{Colors.RESET} "
        f"{Colors.DIM}{args_str}{Colors.RESET}"
    )


def format_tool_result(
    tool_name: str,
    success: bool,
    content: str,
    execution_time: float,
) -> str:
    """Format tool result for display.

    Args:
        tool_name: Name of the tool
        success: Whether execution was successful
        content: Result content (truncated)
        execution_time: Execution time in seconds

    Returns:
        Formatted string for display
    """
    status = f"{Colors.GREEN}OK{Colors.RESET}" if success else f"{Colors.RED}FAIL{Colors.RESET}"
    time_str = f"{execution_time * 1000:.0f}ms"

    # Truncate content
    if len(content) > 150:
        content = content[:150] + "..."
    content = content.replace("\n", " ")

    return (
        f"{Colors.DIM}  -> [{status}] {time_str}{Colors.RESET} {Colors.DIM}{content}{Colors.RESET}"
    )


def format_thinking(content: str) -> str:
    """Format thinking content for display.

    Args:
        content: Thinking content

    Returns:
        Formatted string
    """
    return f"{Colors.DIM}{Colors.MAGENTA}{content}{Colors.RESET}"


def format_error(message: str) -> str:
    """Format error message for display.

    Args:
        message: Error message

    Returns:
        Formatted string
    """
    return f"{Colors.RED}Error: {message}{Colors.RESET}"


def format_step_info(step: int, max_steps: int, tokens: int, token_limit: int) -> str:
    """Format step information for display.

    Args:
        step: Current step number
        max_steps: Maximum steps
        tokens: Current token count
        token_limit: Token limit

    Returns:
        Formatted string
    """
    percentage = (tokens / token_limit) * 100 if token_limit > 0 else 0
    return (
        f"{Colors.DIM}[Step {step}/{max_steps}] "
        f"Tokens: {tokens:,}/{token_limit:,} ({percentage:.1f}%){Colors.RESET}"
    )
