"""MCP 工具加载器，集成了官方 MCP Python SDK。

此模块基于官方 modelcontextprotocol/python-sdk 实现 MCP（模型上下文协议）客户端集成。

支持多种传输方式：
- stdio: 本地进程通信（例如 npx、python、uv）
- sse: 服务器发送事件（HTTP 流）
- http: 可流式 HTTP（双向 HTTP）

官方 SDK 文档：https://github.com/modelcontextprotocol/python-sdk
"""

import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .base import Tool, ToolResult

# Type alias for transport types
TransportType = Literal["stdio", "sse", "http"]


class MCPTool(Tool):
    """官方 SDK 中 MCP 工具的包装器。

    此类包装 MCP 服务器提供的工具，并将其适配到我们的 Tool 接口。
    它通过 ClientSession 处理与 MCP 服务器的通信。

    工具执行遵循官方 SDK 模式：
    - 使用工具名称和参数调用 session.call_tool()
    - 处理包含 content 和 structuredContent 的 CallToolResult
    - 将 MCP TextContent 转换为我们的 ToolResult 格式
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        session: ClientSession,
    ):
        """使用工具元数据和会话初始化 MCPTool。

        Args:
            name: 来自 MCP 服务器的工具名称
            description: 工具描述
            parameters: 工具输入模式（JSON Schema）
            session: 用于调用工具的活动 MCP ClientSession
        """
        self._name = name
        self._description = description
        self._parameters = parameters
        self._session = session

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        """通过会话执行 MCP 工具。

        遵循官方 SDK 模式：
        1. 调用 session.call_tool(name, arguments)
        2. 获取包含 content 列表的 CallToolResult
        3. 从 result.content 中提取 TextContent
        4. 检查 result.isError 的错误状态

        Args:
            **kwargs: 匹配输入模式的工具参数

        Returns:
            包含成功状态和内容的 ToolResult
        """
        try:
            # Call MCP tool using official SDK ClientSession
            result = await self._session.call_tool(self._name, arguments=kwargs)

            # Extract content from CallToolResult
            # result.content is a list of content items (TextContent, ImageContent, etc.)
            content_parts = []
            for item in result.content:
                # Check if item has text attribute (TextContent)
                if hasattr(item, "text"):
                    content_parts.append(item.text)
                else:
                    # Fallback for other content types
                    content_parts.append(str(item))

            content_str = "\n".join(content_parts)

            # Check for error status (official SDK: result.isError)
            is_error = result.isError if hasattr(result, "isError") else False

            return ToolResult(
                success=not is_error,
                content=content_str,
                error=None if not is_error else "Tool returned error",
            )
        except Exception as e:
            return ToolResult(
                success=False, content="", error=f"MCP tool execution failed: {str(e)}"
            )


class MCPServerConnection:
    """使用官方 SDK 管理单个 MCP 服务器的连接。

    此类处理 MCP 服务器连接的生命周期：
    - 建立与 MCP 服务器的 stdio/SSE/HTTP 连接
    - 按照官方 SDK 模式初始化 ClientSession
    - 列出并包装可用工具
    - 在断开连接时进行清理

    支持多种传输方式：
    - stdio: 用于本地进程（npx、python、uv）
    - sse: 用于服务器发送事件端点
    - http: 用于可流式 HTTP 端点

    官方 SDK 参考：
    https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md
    """

    def __init__(
        self,
        name: str,
        transport: TransportType = "stdio",
        # stdio 参数
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        # http/sse 参数
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        """初始化 MCP 服务器连接参数。

        Args:
            name: 用于标识的服务器名称
            transport: 传输类型（'stdio'、'sse' 或 'http'）
            command: 启动 MCP 服务器的命令（仅 stdio）
            args: 命令的参数（仅 stdio）
            env: 服务器进程的环境变量（仅 stdio）
            url: 服务器 URL（仅 sse/http）
            headers: HTTP 头（仅 sse/http）
        """
        self.name = name
        self.transport = transport
        # stdio parameters
        self.command = command
        self.args = args or []
        self.env = env or {}
        # http/sse parameters
        self.url = url
        self.headers = headers or {}
        # connection state
        self.session: ClientSession | None = None
        self.exit_stack: AsyncExitStack | None = None
        self.tools: list[MCPTool] = []

    async def connect(self) -> bool:
        """使用官方 SDK 模式连接到 MCP 服务器。

        针对不同传输方式遵循官方 SDK 连接模式：

        **stdio 传输**：
        1. 使用 command、args、env 创建 StdioServerParameters
        2. 使用 stdio_client() 作为异步上下文管理器
        3. 使用读/写流创建 ClientSession

        **sse 传输**：
        1. 使用 sse_client(url, headers) 作为异步上下文管理器
        2. 使用读/写流创建 ClientSession

        **http 传输**：
        1. 使用 streamablehttp_client(url, headers) 作为异步上下文管理器
        2. 使用读/写/session_id 流创建 ClientSession

        然后对于所有传输方式：
        4. 初始化会话
        5. 列出可用工具

        Returns:
            连接成功返回 True，否则返回 False
        """
        try:
            # Use AsyncExitStack to manage multiple async context managers
            self.exit_stack = AsyncExitStack()

            # Create appropriate client based on transport type
            if self.transport == "stdio":
                # stdio transport (official SDK pattern)
                if not self.command:
                    raise ValueError(f"Server '{self.name}': command required for stdio transport")

                server_params = StdioServerParameters(
                    command=self.command, args=self.args, env=self.env if self.env else None
                )

                # Enter stdio client context
                read_stream, write_stream = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )

            elif self.transport == "sse":
                # SSE transport (official SDK pattern)
                if not self.url:
                    raise ValueError(f"Server '{self.name}': url required for sse transport")

                # Enter SSE client context
                read_stream, write_stream = await self.exit_stack.enter_async_context(
                    sse_client(url=self.url, headers=self.headers)
                )

            elif self.transport == "http":
                # HTTP transport (official SDK pattern)
                if not self.url:
                    raise ValueError(f"Server '{self.name}': url required for http transport")

                # Enter streamable HTTP client context
                # Note: streamablehttp_client returns (read, write, session_id)
                result = await self.exit_stack.enter_async_context(
                    streamablehttp_client(url=self.url, headers=self.headers)
                )

                # Unpack result (may have 2 or 3 elements depending on SDK version)
                if len(result) == 3:
                    read_stream, write_stream, _session_id = result
                else:
                    read_stream, write_stream = result

            else:
                raise ValueError(f"Unsupported transport type: {self.transport}")

            # Enter client session context (same for all transports)
            session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            self.session = session

            # Initialize the session
            await session.initialize()

            # List available tools
            tools_list = await session.list_tools()

            # Wrap each tool
            for tool in tools_list.tools:
                parameters = tool.inputSchema if hasattr(tool, "inputSchema") else {}

                mcp_tool = MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=parameters,
                    session=session,
                )
                self.tools.append(mcp_tool)

            print(
                f"✓ Connected to MCP server '{self.name}' ({self.transport}) - loaded {len(self.tools)} tools"
            )
            for tool in self.tools:
                desc = tool.description[:60] if len(tool.description) > 60 else tool.description
                print(f"  - {tool.name}: {desc}...")
            return True

        except Exception as e:
            print(f"✗ Failed to connect to MCP server '{self.name}': {e}")
            # Clean up exit stack if connection failed
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None
            import traceback

            traceback.print_exc()
            return False

    async def disconnect(self):
        """正确断开与 MCP 服务器的连接。

        使用 AsyncExitStack 按照官方 SDK 模式进行清理。
        """
        if self.exit_stack:
            # AsyncExitStack handles all cleanup properly
            await self.exit_stack.aclose()
            self.exit_stack = None
            self.session = None


# Global connections registry
_mcp_connections: list[MCPServerConnection] = []


async def load_mcp_tools_async(config_path: str = "mcp.json") -> list[Tool]:
    """使用官方 SDK 从配置文件加载 MCP 工具。

    此函数实现官方 SDK 的 MCP 客户端模式：
    1. 读取 mcp.json 配置文件
    2. 解析 mcpServers 配置
    3. 通过 stdio/sse/http 连接到每个启用的服务器
    4. 从每个服务器获取工具定义
    5. 将工具包装到我们的 Tool 接口

    配置文件格式支持多种传输方式：

    **stdio 传输**（本地进程）：
    ```json
    {
      "mcpServers": {
        "server_name": {
          "command": "python",
          "args": ["server.py"],
          "env": {"API_KEY": "value"},
          "disabled": false
        }
      }
    }
    ```

    **http/sse 传输**（远程端点）：
    ```json
    {
      "mcpServers": {
        "server_name": {
          "type": "http",
          "url": "https://mcp.example.com/mcp",
          "headers": {"Authorization": "Bearer token"},
          "disabled": false
        }
      }
    }
    ```

    Args:
        config_path: MCP 配置文件路径（默认："mcp.json"）

    Returns:
        表示 MCP 工具的 Tool 对象列表

    Example:
        ```python
        tools = await load_mcp_tools_async("mcp.json")
        for tool in tools:
            print(f"Loaded: {tool.name}")
        ```
    """
    global _mcp_connections

    config_file = Path(config_path)

    if not config_file.exists():
        print(f"ℹ️  MCP config not found: {config_path} (skipping MCP tools)")
        return []

    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        # Official SDK config format: mcpServers
        mcp_servers = config.get("mcpServers", {})

        if not mcp_servers:
            print("ℹ️  No MCP servers configured")
            return []

        all_tools = []

        # Connect to each enabled server
        for server_name, server_config in mcp_servers.items():
            # Skip disabled servers
            if server_config.get("disabled", False):
                print(f"⊘ Skipping disabled server: {server_name}")
                continue

            # Determine transport type
            transport = server_config.get("type", "stdio").lower()

            # Validate transport type
            if transport not in ["stdio", "sse", "http"]:
                print(f"⚠️  Unknown transport '{transport}' for server '{server_name}', skipping")
                continue

            # Create connection based on transport type
            if transport == "stdio":
                # stdio transport: requires command
                command = server_config.get("command")
                args = server_config.get("args", [])
                env = server_config.get("env", {})

                if not command:
                    print(f"⚠️  No command specified for stdio server: {server_name}")
                    continue

                connection = MCPServerConnection(
                    name=server_name,
                    transport="stdio",
                    command=command,
                    args=args,
                    env=env,
                )

            else:  # sse or http
                # http/sse transport: requires url
                url = server_config.get("url")
                headers = server_config.get("headers", {})

                if not url:
                    print(f"⚠️  No url specified for {transport} server: {server_name}")
                    continue

                connection = MCPServerConnection(
                    name=server_name,
                    transport=transport,  # type: ignore
                    url=url,
                    headers=headers,
                )

            # Connect to server
            success = await connection.connect()

            if success:
                _mcp_connections.append(connection)
                all_tools.extend(connection.tools)

        print(f"\n✅ Total MCP tools loaded: {len(all_tools)}")

        return all_tools

    except Exception as e:
        print(f"❌ Error loading MCP config: {e}")
        import traceback

        traceback.print_exc()
        return []


async def cleanup_mcp_connections():
    """清理所有 MCP 连接。

    应在应用程序关闭时调用，以正确关闭所有 MCP 服务器连接。

    Example:
        ```python
        # 在 FastAPI 生命周期中
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 启动
            yield
            # 关闭
            await cleanup_mcp_connections()
        ```
    """
    global _mcp_connections
    for connection in _mcp_connections:
        await connection.disconnect()
    _mcp_connections.clear()
    print("🧹 All MCP connections cleaned up")
