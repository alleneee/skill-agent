#!/usr/bin/env python3
"""Streaming ACP example using async iterator.

Demonstrates the stream_prompt API for processing events as they arrive.

Usage:
    uv run python examples/acp/streaming_example.py --backend claude
    uv run python examples/acp/streaming_example.py --backend codex -p "Write hello world"
"""

import argparse
import asyncio
import os

from omni_agent.acp import (
    MessageEvent,
    PermissionRequestEvent,
    ThoughtEvent,
    ToolCallEvent,
    ToolProgressEvent,
    stream_prompt,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Streaming ACP example")
    parser.add_argument("-b", "--backend", default="claude")
    parser.add_argument("-p", "--prompt", default="What is 2 + 2?")
    parser.add_argument("-w", "--workspace", default=os.getcwd())
    args = parser.parse_args()

    print(f"Backend: {args.backend}")
    print(f"Workspace: {args.workspace}")
    print("-" * 50)

    async for event in stream_prompt(
        backend=args.backend,
        prompt=args.prompt,
        workspace=args.workspace,
        auto_approve=True,
    ):
        if isinstance(event, MessageEvent):
            print(event.text, end="", flush=True)
        elif isinstance(event, ThoughtEvent):
            print(f"\033[90m{event.text}\033[0m", end="", flush=True)
        elif isinstance(event, ToolCallEvent):
            print(f"\n[Tool Start] {event.title} ({event.kind})")
        elif isinstance(event, ToolProgressEvent):
            print(f"  [Progress] {event.status}")
        elif isinstance(event, PermissionRequestEvent):
            print(f"\n[Permission] {event.tool_call.title}")

    print("\n" + "-" * 50)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
