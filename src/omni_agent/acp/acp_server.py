#!/usr/bin/env python3
"""使用官方 Agent 客户端协议 Python SDK 的 ACP 服务器。

此模块使用官方 SDK 实现符合 ACP 的代理，
允许 Zed、JetBrains、VSCode 等代码编辑器启动 omni-agents。

用法：
    omni-agents-acp [--workspace DIR]
    python -m omni_agent.acp.acp_server [--workspace DIR]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
    update_agent_message,
    update_agent_thought,
    start_tool_call,
    update_tool_call,
)
from acp.interfaces import Client
from acp.schema import (
    ClientCapabilities,
    HttpMcpServer,
    Implementation,
    McpServerStdio,
    SseMcpServer,
    TextContentBlock,
    ImageContentBlock,
    AudioContentBlock,
    ResourceContentBlock,
    EmbeddedResourceContentBlock,
)

from omni_agent.core.agent import Agent as OmniAgent
from omni_agent.core.config import settings
from omni_agent.core.llm_client import LLMClient


class OmniACPAgent(Agent):
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.sessions: dict[str, dict[str, Any]] = {}
        self._conn: Client = None
        self._omni_agent: OmniAgent | None = None
        self._llm_client: LLMClient | None = None
        self._tools: list = []
        self._initialized = False

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def _setup_omni_agent(self):
        if self._initialized:
            return

        if not settings.LLM_API_KEY:
            self._log("Warning: LLM_API_KEY not configured")
            return

        self._llm_client = LLMClient(
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE if settings.LLM_API_BASE else None,
            model=settings.LLM_MODEL,
        )

        from omni_agent.cli.tools_loader import load_cli_tools

        self._tools, skill_loader = await load_cli_tools(
            workspace_dir=self.workspace_dir,
            enable_mcp=settings.ENABLE_MCP,
            enable_skills=settings.ENABLE_SKILLS,
            verbose=False,
        )

        system_prompt = settings.SYSTEM_PROMPT
        if skill_loader:
            skills_metadata = skill_loader.get_skills_metadata_prompt()
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
        else:
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

        workspace_info = (
            f"\n\n## Current Workspace\n"
            f"You are working in: `{self.workspace_dir}`\n"
            f"All relative paths resolve relative to this directory."
        )
        system_prompt += workspace_info

        self._omni_agent = OmniAgent(
            llm_client=self._llm_client,
            system_prompt=system_prompt,
            tools=self._tools,
            max_steps=settings.AGENT_MAX_STEPS,
            workspace_dir=self.workspace_dir,
            enable_logging=True,
        )
        self._initialized = True

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        await self._setup_omni_agent()
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        session_id = uuid4().hex

        resolved_cwd = cwd
        if cwd and not os.path.isabs(cwd):
            resolved_cwd = os.path.join(self.workspace_dir, cwd)

        self.sessions[session_id] = {
            "id": session_id,
            "cwd": resolved_cwd or self.workspace_dir,
            "messages": [],
        }

        if self._omni_agent:
            self._omni_agent.messages.clear()

        return NewSessionResponse(session_id=session_id)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        if not self._omni_agent:
            await self._setup_omni_agent()

        if not self._omni_agent:
            error_chunk = update_agent_message(text_block("[Error: Agent not initialized, check LLM_API_KEY]"))
            await self._conn.session_update(session_id=session_id, update=error_chunk)
            return PromptResponse(stop_reason="error")

        user_message = self._extract_text_from_prompt(prompt)
        if not user_message:
            return PromptResponse(stop_reason="end_turn")

        self._omni_agent.add_user_message(user_message)

        async for event in self._omni_agent.run_stream():
            event_type = event.get("type")
            event_data = event.get("data", {})

            if event_type == "thinking":
                delta = event_data.get("delta", "")
                if delta:
                    chunk = update_agent_thought(text_block(delta))
                    await self._conn.session_update(session_id=session_id, update=chunk)

            elif event_type == "content":
                delta = event_data.get("delta", "")
                if delta:
                    chunk = update_agent_message(text_block(delta))
                    await self._conn.session_update(session_id=session_id, update=chunk)

            elif event_type == "tool_call":
                tool_name = event_data.get("name", "")
                tool_call_id = event_data.get("id", str(uuid4()))
                chunk = start_tool_call(
                    tool_call_id=tool_call_id,
                    title=f"Executing {tool_name}",
                    kind="execute",
                )
                await self._conn.session_update(session_id=session_id, update=chunk)

            elif event_type == "tool_result":
                tool_call_id = event_data.get("tool_call_id", "")
                success = event_data.get("success", True)
                status = "completed" if success else "failed"
                chunk = update_tool_call(
                    tool_call_id=tool_call_id,
                    status=status,
                )
                await self._conn.session_update(session_id=session_id, update=chunk)

            elif event_type == "error":
                error_msg = event_data.get("message", "Unknown error")
                chunk = update_agent_message(text_block(f"\n[Error: {error_msg}]"))
                await self._conn.session_update(session_id=session_id, update=chunk)

        return PromptResponse(stop_reason="end_turn")

    def _extract_text_from_prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
    ) -> str:
        parts = []
        for block in prompt:
            if isinstance(block, TextContentBlock):
                parts.append(block.text)
            elif hasattr(block, "text"):
                parts.append(block.text)
        return " ".join(parts)

    def _log(self, message: str):
        print(f"[omni-agents-acp] {message}", file=sys.stderr, flush=True)


async def main():
    parser = argparse.ArgumentParser(description="Omni Agent ACP Server")
    parser.add_argument(
        "--workspace", "-w", type=str, default=None, help="Workspace directory"
    )
    args = parser.parse_args()

    workspace = args.workspace
    if workspace:
        workspace = str(Path(workspace).absolute())
    else:
        workspace = os.getcwd()

    agent = OmniACPAgent(workspace_dir=workspace)
    await run_agent(agent)


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
