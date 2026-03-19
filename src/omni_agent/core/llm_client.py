"""基于 LiteLLM 的 LLM 客户端，支持 100+ 个提供商.

通过 LiteLLM 统一接口调用各种 LLM 提供商，包括：
- OpenAI (gpt-4o, gpt-4, gpt-3.5-turbo)
- Anthropic (claude-3-5-sonnet, claude-3-opus)
- Azure OpenAI
- Google (gemini-pro, gemini-1.5-pro)
- DeepSeek, Qwen, Mistral, Cohere, Bedrock 等

模型命名约定:
    - OpenAI: "openai/gpt-4o" 或 "gpt-4o"
    - Anthropic: "anthropic/claude-3-5-sonnet-20241022"
    - Azure: "azure/deployment-name"
    - Gemini: "gemini/gemini-1.5-pro"
    - 自定义: "openai/model-name" + 自定义 api_base

自动调整:
    - max_tokens 自动适配各提供商限制（如 DeepSeek 8192, OpenAI 16384）
    - 内容过滤器清理模型输出中的杂质标记

使用示例:
    client = LLMClient(
        api_key="sk-xxx",
        model="anthropic/claude-3-5-sonnet-20241022",
    )
    response = await client.generate(messages)
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm
from litellm import acompletion

from omni_agent.core.retry import RetryConfig, async_retry
from omni_agent.schemas.message import FunctionCall, LLMResponse, Message, TokenUsage, ToolCall

logger = logging.getLogger(__name__)

litellm.drop_params = True

from omni_agent.core.langfuse_tracing import init_langfuse

init_langfuse()

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
    return content


class LLMClient:
    """基于 LiteLLM 的多提供商 LLM 客户端.

    支持 100+ 种 LLM 提供商，通过统一接口调用。
    自动处理 max_tokens 限制适配、消息格式转换、工具调用解析。
    """

    # 各提供商的 max_tokens 限制
    # 超过限制时自动调整，避免 API 报错
    PROVIDER_MAX_TOKENS = {
        "deepseek": 8192,
        "qwen": 8192,  # 文档标称 32K，但 API 实际限制 8192
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
        thinking: bool = False,
        thinking_budget: int = 8000,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/") if api_base else None
        self.model = model
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self.retry_callback = None
        self.thinking = thinking
        self.thinking_budget = thinking_budget

    def _get_max_tokens_limit(self) -> int:
        """根据模型名称获取提供商特定的 max_tokens 限制."""
        model_lower = self.model.lower()

        for provider, limit in self.PROVIDER_MAX_TOKENS.items():
            if provider in model_lower:
                return limit

        return 16384  # 未知提供商默认值

    def _adjust_max_tokens(self, requested: int) -> int:
        """调整 max_tokens 以适应提供商限制."""
        limit = self._get_max_tokens_limit()
        if requested > limit:
            logger.debug(
                f"Requested max_tokens={requested} exceeds {self.model} limit of {limit}. "
                f"Adjusting to {limit}."
            )
            return limit
        return requested

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """将内部消息格式转换为 OpenAI API 格式.

        Returns:
            (system_message, api_messages) 元组
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
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )

        return system_message, api_messages

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """将工具定义转换为 OpenAI 格式（如需要）."""
        if not tools:
            return None

        openai_tools = []
        for tool in tools:
            if "type" in tool and tool["type"] == "function":
                openai_tools.append(tool)
            else:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.get("name"),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema") or tool.get("parameters", {}),
                        },
                    }
                )
        return openai_tools

    async def _make_api_request(
        self,
        messages: list[dict[str, Any]],
        system: str | None,
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """通过 LiteLLM 执行 API 请求."""
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

        if metadata:
            kwargs["metadata"] = metadata

        if self.thinking:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        response = await acompletion(**kwargs)
        return response

    async def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """生成 LLM 响应（同步模式）.

        Args:
            messages: 对话消息列表
            tools: 可用工具定义
            max_tokens: 响应最大 token 数
            metadata: 追踪元数据（如 Langfuse trace_id）

        Returns:
            LLMResponse 包含 content、tool_calls、usage 等
        """
        max_tokens = self._adjust_max_tokens(max_tokens)

        system_message, api_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools)

        if self.retry_config.enabled:
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                api_messages, system_message, openai_tools, max_tokens, metadata
            )
        else:
            response = await self._make_api_request(
                api_messages, system_message, openai_tools, max_tokens, metadata
            )

        choice = response.choices[0]
        message = choice.message

        thinking_text = None
        if isinstance(message.content, list):
            text_parts = []
            for block in message.content:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        thinking_text = block.get("thinking", "")
                    elif block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                else:
                    text_parts.append(str(block))
            text_content = _clean_content("".join(text_parts))
        else:
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
            thinking=thinking_text,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """生成 LLM 流式响应.

        事件类型:
        - content_delta: 内容增量
        - tool_use: 工具调用
        - done: 完成，包含完整 LLMResponse

        Args:
            messages: 对话消息列表
            tools: 可用工具定义
            max_tokens: 响应最大 token 数
            metadata: 追踪元数据
        """
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

        if metadata:
            kwargs["metadata"] = metadata

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
