import contextlib
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Any

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from .backends import get_backend_config, get_cli_args


class AcpEvent:
    pass


class MessageEvent(AcpEvent):
    def __init__(self, text: str):
        self.text = text


class ThoughtEvent(AcpEvent):
    def __init__(self, text: str):
        self.text = text


class ToolCallEvent(AcpEvent):
    def __init__(self, title: str, kind: str, status: str):
        self.title = title
        self.kind = kind
        self.status = status


class ToolProgressEvent(AcpEvent):
    def __init__(self, status: str):
        self.status = status


class PermissionRequestEvent(AcpEvent):
    def __init__(self, options: list[PermissionOption], tool_call: ToolCallUpdate):
        self.options = options
        self.tool_call = tool_call


class SessionHandler(Client, ABC):
    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve
        self._event_callback: Callable[[AcpEvent], None] | None = None

    def set_event_callback(self, callback: Callable[[AcpEvent], None]):
        self._event_callback = callback

    def _emit(self, event: AcpEvent):
        if self._event_callback:
            self._event_callback(event)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        self._emit(PermissionRequestEvent(options, tool_call))

        if self.auto_approve and options:
            return RequestPermissionResponse(
                outcome={"outcome": "selected", "optionId": options[0].option_id}
            )
        return await self.handle_permission(options, session_id, tool_call)

    @abstractmethod
    async def handle_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
    ) -> RequestPermissionResponse:
        pass

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if isinstance(update, AgentMessageChunk):
            if isinstance(update.content, TextContentBlock):
                self._emit(MessageEvent(update.content.text))
        elif isinstance(update, AgentThoughtChunk):
            if isinstance(update.content, TextContentBlock):
                self._emit(ThoughtEvent(update.content.text))
        elif isinstance(update, ToolCallStart):
            self._emit(ToolCallEvent(update.title, update.kind, "started"))
        elif isinstance(update, ToolCallProgress):
            self._emit(ToolProgressEvent(update.status))

    def on_connect(self, conn: Any) -> None:
        pass


class AutoApproveHandler(SessionHandler):
    def __init__(self):
        super().__init__(auto_approve=True)

    async def handle_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
    ) -> RequestPermissionResponse:
        if options:
            return RequestPermissionResponse(
                outcome={"outcome": "selected", "optionId": options[0].option_id}
            )
        return RequestPermissionResponse(outcome={"outcome": "cancelled"})


class InteractiveHandler(SessionHandler):
    def __init__(self):
        super().__init__(auto_approve=False)

    async def handle_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
    ) -> RequestPermissionResponse:
        print(f"\n[Permission] Tool: {tool_call.title}")
        for i, opt in enumerate(options):
            print(f"  {i + 1}. {opt.name} ({opt.option_id})")

        try:
            choice = input("Select (number) or 'c' to cancel: ").strip()
            if choice.lower() == "c":
                return RequestPermissionResponse(outcome={"outcome": "cancelled"})
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return RequestPermissionResponse(
                    outcome={"outcome": "selected", "optionId": options[idx].option_id}
                )
        except (ValueError, EOFError):
            pass
        return RequestPermissionResponse(outcome={"outcome": "cancelled"})


class AcpClient:
    def __init__(
        self,
        backend: str,
        workspace: str | None = None,
        cli_path: str | None = None,
        handler: SessionHandler | None = None,
        env: dict[str, str] | None = None,
    ):
        self.backend = backend
        self.workspace = workspace or os.getcwd()
        self.cli_path = cli_path
        self.handler = handler or AutoApproveHandler()
        self.custom_env = env or {}

        self._conn = None
        self._proc = None
        self._session_id: str | None = None

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        config = get_backend_config(self.backend)
        if config and config.env:
            env.update(config.env)
        env.update(self.custom_env)
        return env

    async def connect(self) -> str:
        command, args = get_cli_args(self.backend, self.cli_path)
        env = self._build_env()

        ctx = spawn_agent_process(self.handler, command, *args, env=env)
        self._conn, self._proc = await ctx.__aenter__()
        self._ctx = ctx

        init_resp = await self._conn.initialize(protocol_version=PROTOCOL_VERSION)
        agent_name = init_resp.agent_info.name if init_resp.agent_info else "unknown"

        auth_methods = getattr(init_resp, "auth_methods", None)
        if auth_methods:
            for method in auth_methods:
                method_id = getattr(method, "method_id", None) or getattr(method, "id", None)
                if method_id:
                    try:
                        await self._conn.authenticate(method_id=method_id)
                        break
                    except Exception:
                        pass

        session = await self._conn.new_session(cwd=self.workspace, mcp_servers=[])
        self._session_id = session.session_id

        return agent_name

    async def prompt(self, message: str) -> None:
        if not self._conn or not self._session_id:
            raise RuntimeError("Not connected. Call connect() first.")
        await self._conn.prompt(
            session_id=self._session_id,
            prompt=[text_block(message)],
        )

    async def disconnect(self) -> None:
        if hasattr(self, "_ctx") and self._ctx:
            await self._ctx.__aexit__(None, None, None)
        self._conn = None
        self._proc = None
        self._session_id = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


async def run_prompt(
    backend: str,
    prompt: str,
    workspace: str | None = None,
    cli_path: str | None = None,
    auto_approve: bool = True,
    on_event: Callable[[AcpEvent], None] | None = None,
) -> str:
    handler = AutoApproveHandler() if auto_approve else InteractiveHandler()
    message_buffer = []

    def collect_messages(event: AcpEvent):
        if isinstance(event, MessageEvent):
            message_buffer.append(event.text)
        if on_event:
            on_event(event)

    handler.set_event_callback(collect_messages)

    async with AcpClient(
        backend=backend,
        workspace=workspace,
        cli_path=cli_path,
        handler=handler,
    ) as client:
        await client.prompt(prompt)

    return "".join(message_buffer)


async def stream_prompt(
    backend: str,
    prompt: str,
    workspace: str | None = None,
    cli_path: str | None = None,
    auto_approve: bool = True,
) -> AsyncIterator[AcpEvent]:
    import asyncio

    handler = AutoApproveHandler() if auto_approve else InteractiveHandler()
    queue: asyncio.Queue[AcpEvent | None] = asyncio.Queue()

    def enqueue_event(event: AcpEvent):
        queue.put_nowait(event)

    handler.set_event_callback(enqueue_event)

    async def run_client():
        try:
            async with AcpClient(
                backend=backend,
                workspace=workspace,
                cli_path=cli_path,
                handler=handler,
            ) as client:
                await client.prompt(prompt)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(run_client())

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
