#!/usr/bin/env python3
"""OpenAI Codex CLI ACP example.

Prerequisites:
    - Codex CLI installed: npm install -g @openai/codex
    - OPENAI_API_KEY environment variable set

Usage:
    uv run python examples/acp/codex_example.py
    uv run python examples/acp/codex_example.py -p "Write a Python function"
"""

import argparse
import asyncio
import os

from omni_agent.acp import AcpClient, MessageEvent, ToolCallEvent


async def main() -> None:
    parser = argparse.ArgumentParser(description="Codex CLI ACP example")
    parser.add_argument("-p", "--prompt", default="What is 2 + 2?")
    parser.add_argument("-w", "--workspace", default=os.getcwd())
    args = parser.parse_args()

    def on_event(event):
        if isinstance(event, MessageEvent):
            print(event.text, end="", flush=True)
        elif isinstance(event, ToolCallEvent):
            print(f"\n[Tool] {event.title}")

    print("Connecting to Codex CLI...")
    print(f"Workspace: {args.workspace}")
    print("-" * 50)

    async with AcpClient(backend="codex", workspace=args.workspace) as client:
        client.handler.set_event_callback(on_event)
        await client.prompt(args.prompt)

    print("\n" + "-" * 50)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
