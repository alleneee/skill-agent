"""LLM client for Anthropic-compatible API."""

import json
import logging
from typing import Any, AsyncIterator

import httpx

from fastapi_agent.core.retry import RetryConfig, async_retry
from fastapi_agent.schemas.message import FunctionCall, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM Client for Anthropic-compatible endpoints.

    Supports:
    - Claude models via Anthropic API
    - MiniMax M2 via Anthropic-compatible API
    - Other compatible endpoints
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.anthropic.com",
        model: str = "claude-3-5-sonnet-20241022",
        timeout: float = 120.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()

        # Callback for tracking retry count
        self.retry_callback = None

    async def _make_api_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute API request (core method that can be retried).

        Args:
            payload: Request payload

        Returns:
            API response result

        Raises:
            Exception: API call failed
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_base}/v1/messages",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )

            result = response.json()

        # Check for errors (Anthropic format)
        if result.get("type") == "error":
            error_info = result.get("error", {})
            error_msg = f"API Error ({error_info.get('type')}): {error_info.get('message')}"
            raise Exception(error_msg)

        # Check for MiniMax base_resp errors
        if "base_resp" in result:
            base_resp = result["base_resp"]
            status_code = base_resp.get("status_code")
            status_msg = base_resp.get("status_msg")

            if status_code not in [0, 1000, None]:
                error_msg = f"MiniMax API Error (code {status_code}): {status_msg}"
                if status_code == 1008:
                    error_msg += "\n\n⚠️  Insufficient account balance, please recharge on MiniMax platform"
                elif status_code == 2013:
                    error_msg += f"\n\n⚠️  Model '{self.model}' is not supported"
                raise Exception(error_msg)

        return result

    async def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> LLMResponse:
        """Generate response from LLM."""
        # Extract system message
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            # Handle user and assistant messages
            if msg.role in ["user", "assistant"]:
                if msg.role == "assistant" and (msg.thinking or msg.tool_calls):
                    # Build content blocks for assistant with thinking/tool calls
                    content_blocks = []

                    if msg.thinking:
                        content_blocks.append({"type": "thinking", "thinking": msg.thinking})

                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})

                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            content_blocks.append({
                                "type": "tool_use",
                                "id": tool_call.id,
                                "name": tool_call.function.name,
                                "input": tool_call.function.arguments,
                            })

                    api_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    api_messages.append({"role": msg.role, "content": msg.content})

            # Handle tool result messages
            elif msg.role == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }]
                })

        # Build request payload
        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }

        if system_message:
            payload["system"] = system_message

        if tools:
            payload["tools"] = tools

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(
                config=self.retry_config, on_retry=self.retry_callback
            )
            api_call = retry_decorator(self._make_api_request)
            result = await api_call(payload)
        else:
            # Don't use retry
            result = await self._make_api_request(payload)

        # Parse response
        content_blocks = result.get("content", [])
        stop_reason = result.get("stop_reason", "stop")

        # Extract text, thinking, and tool calls
        text_content = ""
        thinking_content = ""
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "thinking":
                thinking_content += block.get("thinking", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id"),
                        type="function",
                        function=FunctionCall(
                            name=block.get("name"),
                            arguments=block.get("input", {}),
                        ),
                    )
                )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=stop_reason,
        )

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Generate streaming response from LLM.

        Yields:
            dict: Stream events包含:
                - type: 'thinking_delta' | 'content_delta' | 'tool_use' | 'done'
                - delta: 增量文本 (for delta events)
                - tool_call: 工具调用信息 (for tool_use events)
                - response: 完整响应 (for done event)
        """
        # Extract system message and build API messages (same as generate)
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            if msg.role in ["user", "assistant"]:
                if msg.role == "assistant" and (msg.thinking or msg.tool_calls):
                    content_blocks = []
                    if msg.thinking:
                        content_blocks.append({"type": "thinking", "thinking": msg.thinking})
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})
                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            content_blocks.append({
                                "type": "tool_use",
                                "id": tool_call.id,
                                "name": tool_call.function.name,
                                "input": tool_call.function.arguments,
                            })
                    api_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    api_messages.append({"role": msg.role, "content": msg.content})
            elif msg.role == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }]
                })

        # Build request payload with stream=True
        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": True,  # Enable streaming
        }

        if system_message:
            payload["system"] = system_message
        if tools:
            payload["tools"] = tools

        # Make streaming API request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.api_base}/v1/messages",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            ) as response:
                # Accumulate complete response for final event
                text_content = ""
                thinking_content = ""
                tool_calls = []
                current_tool = None

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    # Parse SSE format: "data: {...}"
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type")

                        # content_block_delta: streaming text/thinking
                        if event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            delta_type = delta.get("type")

                            if delta_type == "text_delta":
                                text_delta = delta.get("text", "")
                                text_content += text_delta
                                yield {
                                    "type": "content_delta",
                                    "delta": text_delta,
                                }
                            elif delta_type == "thinking_delta":
                                thinking_delta = delta.get("thinking", "")
                                thinking_content += thinking_delta
                                yield {
                                    "type": "thinking_delta",
                                    "delta": thinking_delta,
                                }
                            elif delta_type == "input_json_delta":
                                # Tool input streaming (partial JSON)
                                if current_tool:
                                    current_tool["input_json"] += delta.get("partial_json", "")

                        # content_block_start: tool use start
                        elif event_type == "content_block_start":
                            content_block = event.get("content_block", {})
                            if content_block.get("type") == "tool_use":
                                current_tool = {
                                    "id": content_block.get("id"),
                                    "name": content_block.get("name"),
                                    "input_json": "",
                                }

                        # content_block_stop: tool use complete
                        elif event_type == "content_block_stop":
                            if current_tool:
                                # Parse complete tool input
                                try:
                                    tool_input = json.loads(current_tool["input_json"])
                                except json.JSONDecodeError:
                                    tool_input = {}

                                tool_call = ToolCall(
                                    id=current_tool["id"],
                                    type="function",
                                    function=FunctionCall(
                                        name=current_tool["name"],
                                        arguments=tool_input,
                                    ),
                                )
                                tool_calls.append(tool_call)

                                yield {
                                    "type": "tool_use",
                                    "tool_call": tool_call,
                                }
                                current_tool = None

                        # message_stop: stream complete
                        elif event_type == "message_stop":
                            final_response = LLMResponse(
                                content=text_content,
                                thinking=thinking_content if thinking_content else None,
                                tool_calls=tool_calls if tool_calls else None,
                                finish_reason="stop",
                            )
                            yield {
                                "type": "done",
                                "response": final_response,
                            }
