#!/usr/bin/env python3
"""用于代码编辑器集成的 ACP stdio 桥接器。

此脚本将 stdio（Zed、JetBrains 使用）桥接到 HTTP ACP 端点。
在编辑器配置中将此脚本作为 ACP 代理命令运行。

用法：
    python -m omni_agent.acp.stdio_bridge [--port 8000] [--host localhost]
"""

import argparse
import asyncio
import json
import sys

import httpx


class ACPStdioBridge:
    def __init__(self, host: str = "localhost", port: int = 8000):
        self.base_url = f"http://{host}:{port}/api/v1/acp"
        self.client: httpx.AsyncClient | None = None

    async def start(self):
        self.client = httpx.AsyncClient(timeout=120.0)
        await self._run_loop()

    async def stop(self):
        if self.client:
            await self.client.aclose()

    async def _run_loop(self):
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break

                line = line.decode("utf-8").strip()
                if not line:
                    continue

                request = json.loads(line)
                await self._handle_request(request)

            except json.JSONDecodeError as e:
                self._send_error(None, -32700, f"Parse error: {e}")
            except Exception as e:
                self._send_error(None, -32603, f"Internal error: {e}")

    async def _handle_request(self, request: dict):
        method = request.get("method", "")
        request_id = request.get("id")

        endpoint_map = {
            "agents/initialize": "/agents/initialize",
            "initialize": "/agents/initialize",
            "session/new": "/session/new",
            "session/prompt": "/session/prompt",
            "session/cancel": "/session/cancel",
        }

        endpoint = endpoint_map.get(method)
        if not endpoint:
            self._send_error(request_id, -32601, f"Method not found: {method}")
            return

        try:
            if method == "session/prompt":
                await self._handle_stream_prompt(request)
            else:
                response = await self.client.post(
                    f"{self.base_url}{endpoint}",
                    json=request,
                )
                result = response.json()
                self._send_response(result)
        except Exception as e:
            self._send_error(request_id, -32603, str(e))

    async def _handle_stream_prompt(self, request: dict):
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/session/prompt/stream",
                json=request,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data:
                            self._send_response(json.loads(data))
        except Exception as e:
            self._send_error(request.get("id"), -32603, str(e))

    def _send_response(self, response: dict):
        print(json.dumps(response), flush=True)

    def _send_error(self, request_id, code: int, message: str):
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        print(json.dumps(error_response), flush=True)


async def main():
    parser = argparse.ArgumentParser(description="ACP stdio bridge")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    args = parser.parse_args()

    bridge = ACPStdioBridge(host=args.host, port=args.port)
    try:
        await bridge.start()
    finally:
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
