"""LLM client using LiteLLM for multi-provider support."""

import json
import logging
from typing import Any, AsyncIterator

import litellm
from litellm import acompletion

from fastapi_agent.core.retry import RetryConfig, async_retry
from fastapi_agent.schemas.message import FunctionCall, LLMResponse, Message, ToolCall, TokenUsage

logger = logging.getLogger(__name__)

litellm.drop_params = True

import re

CONTENT_FILTER_PATTERNS = [
    re.compile(r"<has_function_call>[A-Za-z0-9\.\-\s]*"),
    re.compile(r"</has_function_call>"),
    re.compile(r"<\|im_start\|>[^<]*"),
    re.compile(r"<\|im_end\|>"),
    re.compile(r"<\|function_call\|>[^<]*"),
    re.compile(r"`[a-z]+_[a-z_]+`", re.IGNORECASE),
    re.compile(r"I[a-z]{2,}(?:will|now|use|the|to|am|search|get|find)[a-z]*", re.IGNORECASE),
    re.compile(r"tool[a-zA-Z\u00C0-\u017F]+\.", re.IGNORECASE),
]

def _clean_content(content: str) -> str:
    if not content:
        return content
    for pattern in CONTENT_FILTER_PATTERNS:
        content = pattern.sub("", content)
    return content.lstrip()


class LLMClient:
    """LLM Client using LiteLLM for multi-provider support.

    Supports 100+ LLM providers including:
    - OpenAI (gpt-4o, gpt-4, gpt-3.5-turbo)
    - Anthropic (claude-3-5-sonnet, claude-3-opus)
    - Azure OpenAI
    - Google (gemini-pro, gemini-1.5-pro)
    - Mistral, Cohere, Bedrock, etc.

    Model naming convention:
    - OpenAI: "openai/gpt-4o" or just "gpt-4o"
    - Anthropic: "anthropic/claude-3-5-sonnet-20241022"
    - Azure: "azure/deployment-name"
    - Gemini: "gemini/gemini-1.5-pro"
    - Custom: "openai/model-name" with custom api_base
    """

    # Provider-specific max_tokens limits
    PROVIDER_MAX_TOKENS = {
        "deepseek": 8192,
        "qwen": 8192,  # Actual API limit is 8192 (docs show 32K but API enforces 8192)
        "glm": 8192,
        "openai": 16384,
        "anthropic": 8192,
        "gemini": 8192,
        "xai": 16384,
        "mistral": 16384,
    }

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        model: str = "gpt-4o",
        timeout: float = 120.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/") if api_base else None
        self.model = model
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self.retry_callback = None

    def _get_max_tokens_limit(self) -> int:
        """Get provider-specific max_tokens limit based on model name."""
        model_lower = self.model.lower()

        for provider, limit in self.PROVIDER_MAX_TOKENS.items():
            if provider in model_lower:
                return limit

        # Default limit for unknown providers
        return 16384

    def _adjust_max_tokens(self, requested: int) -> int:
        """Adjust max_tokens to respect provider limits."""
        limit = self._get_max_tokens_limit()
        if requested > limit:
            logger.warning(
                f"Requested max_tokens={requested} exceeds {self.model} limit of {limit}. "
                f"Adjusting to {limit}."
            )
            return limit
        return requested

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal message format to OpenAI format.

        Returns:
            Tuple of (system_message, api_messages)
        """
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            if msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})

            elif msg.role == "assistant":
                message_dict: dict[str, Any] = {"role": "assistant"}

                if msg.content:
                    message_dict["content"] = msg.content

                if msg.tool_calls:
                    message_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": json.dumps(tc.function.arguments)
                                    if isinstance(tc.function.arguments, dict)
                                    else tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]

                api_messages.append(message_dict)

            elif msg.role == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })

        return system_message, api_messages

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Convert tools to OpenAI format if needed."""
        if not tools:
            return None

        openai_tools = []
        for tool in tools:
            if "type" in tool and tool["type"] == "function":
                openai_tools.append(tool)
            else:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema") or tool.get("parameters", {}),
                    }
                })
        return openai_tools

    async def _make_api_request(
        self,
        messages: list[dict[str, Any]],
        system: str | None,
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        """Execute API request via litellm."""
        if system:
            messages = [{"role": "system", "content": system}] + messages

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "timeout": self.timeout,
        }

        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await acompletion(**kwargs)
        return response

    async def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> LLMResponse:
        """Generate response from LLM."""
        # Adjust max_tokens to respect provider limits
        max_tokens = self._adjust_max_tokens(max_tokens)

        system_message, api_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools)

        if self.retry_config.enabled:
            retry_decorator = async_retry(
                config=self.retry_config, on_retry=self.retry_callback
            )
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(api_messages, system_message, openai_tools, max_tokens)
        else:
            response = await self._make_api_request(api_messages, system_message, openai_tools, max_tokens)

        choice = response.choices[0]
        message = choice.message

        text_content = _clean_content(message.content or "")
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        type="function",
                        function=FunctionCall(
                            name=tc.function.name,
                            arguments=arguments,
                        ),
                    )
                )

        usage_data = response.usage
        usage = TokenUsage(
            input_tokens=getattr(usage_data, "prompt_tokens", 0),
            output_tokens=getattr(usage_data, "completion_tokens", 0),
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )

        return LLMResponse(
            content=text_content,
            thinking=None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Generate streaming response from LLM."""
        # Adjust max_tokens to respect provider limits
        max_tokens = self._adjust_max_tokens(max_tokens)

        system_message, api_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools)

        if system_message:
            api_messages = [{"role": "system", "content": system_message}] + api_messages

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "timeout": self.timeout,
            "stream": True,
        }

        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        response = await acompletion(**kwargs)

        text_content = ""
        tool_calls: list[ToolCall] = []
        current_tool_calls: dict[int, dict] = {}

        async for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if hasattr(delta, "content") and delta.content:
                cleaned_delta = _clean_content(delta.content)
                if cleaned_delta:
                    text_content += cleaned_delta
                    yield {
                        "type": "content_delta",
                        "delta": cleaned_delta,
                    }

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index

                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }

                    if tc_delta.id:
                        current_tool_calls[idx]["id"] = tc_delta.id

                    if tc_delta.function:
                        if tc_delta.function.name:
                            current_tool_calls[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            current_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            if finish_reason:
                for idx in sorted(current_tool_calls.keys()):
                    tc_data = current_tool_calls[idx]
                    try:
                        arguments = json.loads(tc_data["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_call = ToolCall(
                        id=tc_data["id"],
                        type="function",
                        function=FunctionCall(
                            name=tc_data["name"],
                            arguments=arguments,
                        ),
                    )
                    tool_calls.append(tool_call)
                    yield {
                        "type": "tool_use",
                        "tool_call": tool_call,
                    }

                final_response = LLMResponse(
                    content=_clean_content(text_content),
                    thinking=None,
                    tool_calls=tool_calls if tool_calls else None,
                    finish_reason=finish_reason,
                )
                yield {
                    "type": "done",
                    "response": final_response,
                }
