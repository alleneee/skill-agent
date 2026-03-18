#!/usr/bin/env python3
"""Claude Code ACP example.

Prerequisites:
    - Claude Code CLI installed: npm install -g @anthropic-ai/claude-code
    - ANTHROPIC_API_KEY environment variable set
    - Or authenticated via: claude /login

Usage:
    uv run python examples/acp/claude_example.py
    uv run python examples/acp/claude_example.py -p "Explain this codebase"
"""

import argparse
import asyncio
import os

from omni_agent.acp import AcpClient, MessageEvent, ThoughtEvent, ToolCallEvent


async def main() -> None:
    parser = argparse.ArgumentParser(description="Claude Code ACP example")
    parser.add_argument("-p", "--prompt", default="What is 2 + 2?")
    parser.add_argument("-w", "--workspace", default=os.getcwd())
    args = parser.parse_args()

    def on_event(event):
        if isinstance(event, MessageEvent):
            print(event.text, end="", flush=True)
        elif isinstance(event, ThoughtEvent):
            print(f"\033[90m{event.text}\033[0m", end="", flush=True)
        elif isinstance(event, ToolCallEvent):
            print(f"\n[Tool] {event.title}")

    print("Connecting to Claude Code...")
    print(f"Workspace: {args.workspace}")
    print("-" * 50)

    async with AcpClient(backend="claude", workspace=args.workspace) as client:
        client.handler.set_event_callback(on_event)
        await client.prompt(args.prompt)

    print("\n" + "-" * 50)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
