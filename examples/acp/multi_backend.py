#!/usr/bin/env python3
"""Multi-backend ACP client example.

Demonstrates connecting to different ACP backends: Claude, Codex, Qwen, Goose, etc.

Usage:
    uv run python examples/acp/multi_backend.py --backend claude
    uv run python examples/acp/multi_backend.py --backend codex --prompt "What is Python?"
    uv run python examples/acp/multi_backend.py --backend qwen
    uv run python examples/acp/multi_backend.py --list
"""

import argparse
import asyncio
import os

from omni_agent.acp import (
    AcpClient,
    AcpEvent,
    MessageEvent,
    ThoughtEvent,
    ToolCallEvent,
    get_enabled_backends,
    run_prompt,
)


def print_event(event: AcpEvent) -> None:
    if isinstance(event, MessageEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ThoughtEvent):
        print(f"\033[90m{event.text}\033[0m", end="", flush=True)
    elif isinstance(event, ToolCallEvent):
        print(f"\n[Tool] {event.title} ({event.kind})")


async def run_with_client(backend: str, prompt: str, workspace: str) -> None:
    print(f"Backend: {backend}")
    print(f"Workspace: {workspace}")
    print(f"Prompt: {prompt}")
    print("-" * 50)

    async with AcpClient(
        backend=backend,
        workspace=workspace,
    ) as client:
        client.handler.set_event_callback(print_event)
        await client.prompt(prompt)

    print("\n" + "-" * 50)
    print("Done!")


async def run_simple(backend: str, prompt: str, workspace: str) -> None:
    print(f"Backend: {backend}")
    print(f"Prompt: {prompt}")
    print("-" * 50)

    result = await run_prompt(
        backend=backend,
        prompt=prompt,
        workspace=workspace,
        auto_approve=True,
        on_event=print_event,
    )

    print("\n" + "-" * 50)
    print(f"Result length: {len(result)} chars")


def list_backends() -> None:
    print("Available ACP backends:\n")
    for cfg in get_enabled_backends():
        cli = cfg.cli_command or cfg.default_cli_path or "(custom)"
        args = " ".join(cfg.acp_args)
        auth = "requires auth" if cfg.auth_required else "no auth"
        print(f"  {cfg.id:12} {cfg.name:20} [{cli} {args}] ({auth})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-backend ACP client")
    parser.add_argument(
        "--backend",
        "-b",
        type=str,
        default="claude",
        help="Backend to use (claude, codex, qwen, goose, auggie, kimi, opencode)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default="What is 2 + 2? Answer briefly.",
        help="Prompt to send",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=os.getcwd(),
        help="Workspace directory",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available backends",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Use simple run_prompt API",
    )
    args = parser.parse_args()

    if args.list:
        list_backends()
        return

    if args.simple:
        asyncio.run(run_simple(args.backend, args.prompt, args.workspace))
    else:
        asyncio.run(run_with_client(args.backend, args.prompt, args.workspace))


if __name__ == "__main__":
    main()
