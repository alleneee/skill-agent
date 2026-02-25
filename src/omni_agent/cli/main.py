"""Omni Agent CLI - 交互式 REPL，支持流式输出。

Usage:
    omni-agents [OPTIONS]

Options:
    --workspace, -w DIR     Workspace directory (default: ./workspace)
    --session-id, -s ID     Resume existing session
    --no-mcp               Disable MCP tools
    --no-skills            Disable skills
    --version, -v          Show version
    --help, -h             Show help
"""
import argparse
import asyncio
import sys
import termios
import tty
from datetime import datetime
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from omni_agent.core.agent import Agent
from omni_agent.core.config import settings
from omni_agent.core.llm_client import LLMClient
from omni_agent.schemas.message import Message

from omni_agent.cli.commands import (
    AVAILABLE_COMMANDS,
    handle_clear,
    handle_history,
    handle_session,
    handle_stats_command,
    handle_tools,
    print_help,
)
from omni_agent.cli.display import (
    Colors,
    format_error,
    format_step_info,
    format_tool_call,
    format_tool_result,
    print_banner,
    print_session_info,
    print_stats,
)
from omni_agent.cli.session_handler import CLISessionHandler
from omni_agent.cli.tools_loader import cleanup_tools, load_cli_tools


VERSION = "0.1.0"


class KeyboardListener:
    """Non-blocking keyboard listener for terminal."""

    def __init__(self):
        self._old_settings = None

    def start(self):
        """Set terminal to raw mode for non-blocking input."""
        try:
            self._old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception:
            self._old_settings = None

    def stop(self):
        """Restore terminal settings."""
        if self._old_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass

    def check_key(self) -> Optional[str]:
        """Check if a key was pressed (non-blocking).

        Returns:
            Key character if pressed, None otherwise
        """
        import select

        if select.select([sys.stdin], [], [], 0)[0]:
            try:
                char = sys.stdin.read(1)
                return char
            except Exception:
                return None
        return None


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Omni Agent - Interactive AI assistant with tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  omni-agents                           # Use default workspace
  omni-agents -w /path/to/project       # Custom workspace
  omni-agents -s my-session             # Resume session
  omni-agents --no-mcp                  # Disable MCP tools
        """,
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory (default: ./workspace or AGENT_WORKSPACE_DIR)",
    )
    parser.add_argument(
        "--session-id",
        "-s",
        type=str,
        default=None,
        help="Session ID to resume (generates new if not provided)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable MCP tool loading",
    )
    parser.add_argument(
        "--no-skills",
        action="store_true",
        help="Disable skills loading",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help=f"Maximum agents steps (default: {settings.AGENT_MAX_STEPS})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug information (tool loading, MCP connections, etc.)",
    )
    parser.add_argument(
        "--no-thinking",
        action="store_true",
        help="Hide thinking process (toggle with Ctrl+O during execution)",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"omni-agents {VERSION}",
    )
    return parser.parse_args()


async def run_agent_cli(
    workspace_dir: Path,
    session_id: Optional[str] = None,
    enable_mcp: bool = True,
    enable_skills: bool = True,
    max_steps: Optional[int] = None,
    debug: bool = False,
    show_thinking: bool = True,
) -> None:
    """Run interactive CLI agents.

    Args:
        workspace_dir: Workspace directory path
        session_id: Optional session ID to resume
        enable_mcp: Whether to enable MCP tools
        enable_skills: Whether to enable skills
        max_steps: Maximum agents steps per run
        debug: Whether to show debug information
        show_thinking: Whether to show thinking process
    """
    session_start = datetime.now()

    # 1. Check API key
    if not settings.LLM_API_KEY:
        print(f"{Colors.RED}Error: LLM_API_KEY not configured{Colors.RESET}")
        print(f"{Colors.DIM}Set LLM_API_KEY in .env file or environment{Colors.RESET}")
        return

    # 2. Initialize LLM client
    if debug:
        print(f"{Colors.BRIGHT_CYAN}Initializing LLM client...{Colors.RESET}")
    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE if settings.LLM_API_BASE else None,
        model=settings.LLM_MODEL,
    )
    if debug:
        print(f"{Colors.GREEN}LLM client initialized: {settings.LLM_MODEL}{Colors.RESET}")

    # 3. Load tools
    tools, skill_loader = await load_cli_tools(
        workspace_dir=str(workspace_dir),
        enable_mcp=enable_mcp,
        enable_skills=enable_skills,
        verbose=debug,
    )

    # 4. Build system prompt
    system_prompt = settings.SYSTEM_PROMPT
    if skill_loader:
        skills_metadata = skill_loader.get_skills_metadata_prompt()
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
    else:
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    # Add workspace info
    workspace_info = (
        f"\n\n## Current Workspace\n"
        f"You are working in: `{workspace_dir.absolute()}`\n"
        f"All relative paths resolve relative to this directory."
    )
    system_prompt += workspace_info

    # 5. Create agents
    agent = Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=max_steps or settings.AGENT_MAX_STEPS,
        workspace_dir=str(workspace_dir),
        enable_logging=True,
    )

    # 6. Initialize session handler
    session_handler = CLISessionHandler(session_id=session_id)
    await session_handler.initialize()

    # 7. Load history context if resuming session
    if session_id:
        history_messages = await session_handler.get_history_context(
            num_runs=settings.SESSION_HISTORY_RUNS
        )
        for msg in history_messages:
            agent.messages.append(Message(role=msg["role"], content=msg["content"]))
        if history_messages:
            print(f"{Colors.GREEN}Loaded {len(history_messages)} history messages{Colors.RESET}")

    # 8. Display welcome
    print_banner()
    print_session_info(
        agent=agent,
        workspace_dir=workspace_dir,
        model=settings.LLM_MODEL,
        tools_count=len(tools),
    )

    # 9. Setup prompt_toolkit
    command_completer = WordCompleter(
        AVAILABLE_COMMANDS,
        ignore_case=True,
        sentence=True,
    )

    prompt_style = Style.from_dict(
        {
            "prompt": "#00ff00 bold",
            "separator": "#666666",
        }
    )

    kb = KeyBindings()

    @kb.add("c-u")
    def _(event):
        """Clear current line."""
        event.current_buffer.reset()

    @kb.add("c-l")
    def _(event):
        """Clear screen."""
        event.app.renderer.clear()

    @kb.add("c-j")
    def _(event):
        """Insert newline."""
        event.current_buffer.insert_text("\n")

    # History file in user home
    history_file = Path.home() / ".omni-agents" / ".cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        style=prompt_style,
        key_bindings=kb,
    )

    # 10. Interactive loop
    while True:
        try:
            user_input = await session.prompt_async(
                [
                    ("class:prompt", "You"),
                    ("", " > "),
                ],
                multiline=False,
                enable_history_search=True,
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ["/exit", "/quit", "/q"]:
                    print(f"\n{Colors.BRIGHT_YELLOW}Goodbye! Thanks for using Omni Agent{Colors.RESET}\n")
                    print_stats(agent, session_start, session_handler.tool_calls_count)
                    break

                elif command == "/help":
                    print_help()
                    continue

                elif command == "/clear":
                    cleared = handle_clear(agent)
                    print(f"{Colors.GREEN}Cleared {cleared} messages{Colors.RESET}\n")
                    continue

                elif command == "/history":
                    handle_history(agent)
                    continue

                elif command == "/tools":
                    handle_tools(agent)
                    continue

                elif command == "/stats":
                    handle_stats_command(agent, session_start, session_handler.tool_calls_count)
                    continue

                elif command == "/session":
                    handle_session(session_handler.session_id, str(workspace_dir))
                    continue

                else:
                    print(f"{Colors.RED}Unknown command: {user_input}{Colors.RESET}")
                    print(f"{Colors.DIM}Type /help for available commands{Colors.RESET}\n")
                    continue

            # Exit shortcuts
            if user_input.lower() in ["exit", "quit", "q"]:
                print(f"\n{Colors.BRIGHT_YELLOW}Goodbye!{Colors.RESET}\n")
                print_stats(agent, session_start, session_handler.tool_calls_count)
                break

            # Run agents with streaming
            print(f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}>{Colors.RESET} {Colors.DIM}Thinking...{Colors.RESET}", end="", flush=True)
            if show_thinking:
                print(f" {Colors.DIM}(Ctrl+O to hide thinking){Colors.RESET}", end="")
            print("\n")
            agent.add_user_message(user_input)

            content_buffer = ""
            steps = 0
            run_success = True

            # Setup keyboard listener for Ctrl+O toggle
            kb_listener = KeyboardListener()
            kb_listener.start()

            try:
                async for event in agent.run_stream():
                    # Check for Ctrl+O (ASCII 15) to toggle thinking display
                    key = kb_listener.check_key()
                    if key == '\x0f':  # Ctrl+O
                        show_thinking = not show_thinking
                        status = "ON" if show_thinking else "OFF"
                        print(f"\n{Colors.DIM}[Thinking: {status}]{Colors.RESET}", end="", flush=True)

                    event_type = event.get("type")
                    event_data = event.get("data", {})

                    if event_type == "step":
                        steps = event_data.get("step", steps)
                        # 不显示 step 信息,保持输出简洁

                    elif event_type == "thinking":
                        if show_thinking:
                            delta = event_data.get("delta", "")
                            # Show thinking in dimmed magenta
                            print(f"{Colors.DIM}{Colors.MAGENTA}{delta}{Colors.RESET}", end="", flush=True)

                    elif event_type == "content":
                        delta = event_data.get("delta", "")
                        content_buffer += delta
                        print(delta, end="", flush=True)

                    elif event_type == "tool_call":
                        session_handler.increment_tool_calls()
                        # 不显示工具调用详情,保持输出简洁

                    elif event_type == "tool_result":
                        # 不显示工具结果,保持输出简洁
                        pass

                    elif event_type == "user_input_required":
                        # Handle human-in-the-loop
                        fields = event_data.get("fields", [])
                        context = event_data.get("context", "")
                        print(f"\n{Colors.BRIGHT_YELLOW}[User Input Required]{Colors.RESET}")
                        if context:
                            print(f"{Colors.DIM}{context}{Colors.RESET}")
                        for field in fields:
                            field_name = field.get("field_name", "input")
                            field_desc = field.get("field_description", "")
                            print(f"  {Colors.BRIGHT_CYAN}{field_name}{Colors.RESET}: {field_desc}")
                        # Note: Full human-in-the-loop requires additional handling
                        print(f"{Colors.YELLOW}(Human-in-the-loop paused - restart to provide input){Colors.RESET}")

                    elif event_type == "done":
                        content_buffer = event_data.get("message", content_buffer)

                    elif event_type == "error":
                        run_success = False
                        error_msg = event_data.get("message", "Unknown error")
                        print(f"\n{format_error(error_msg)}")

                # Ensure newline after streaming
                if content_buffer and not content_buffer.endswith("\n"):
                    print()

            except Exception as e:
                run_success = False
                print(f"\n{format_error(str(e))}")

            finally:
                # Always restore terminal settings
                kb_listener.stop()

            # Save to session
            await session_handler.save_run(
                task=user_input,
                response=content_buffer,
                success=run_success,
                steps=steps,
            )

            print(f"\n{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRIGHT_YELLOW}Interrupted. Exiting...{Colors.RESET}\n")
            print_stats(agent, session_start, session_handler.tool_calls_count)
            break

        except EOFError:
            # Handle Ctrl+D
            print(f"\n\n{Colors.BRIGHT_YELLOW}Goodbye!{Colors.RESET}\n")
            print_stats(agent, session_start, session_handler.tool_calls_count)
            break

        except Exception as e:
            print(f"\n{format_error(str(e))}")
            print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    # Cleanup
    await session_handler.close()
    await cleanup_tools(verbose=debug)


def main():
    """Main entry point for CLI."""
    args = parse_args()

    # Determine workspace
    if args.workspace:
        workspace_dir = Path(args.workspace).absolute()
    else:
        workspace_dir = Path(settings.AGENT_WORKSPACE_DIR).absolute()

    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Run async main
    asyncio.run(
        run_agent_cli(
            workspace_dir=workspace_dir,
            session_id=args.session_id,
            enable_mcp=not args.no_mcp,
            enable_skills=not args.no_skills,
            max_steps=args.max_steps,
            debug=args.debug,
            show_thinking=not args.no_thinking,
        )
    )


if __name__ == "__main__":
    main()
