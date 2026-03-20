from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omni_agent.core.llm_client import LLMClient, _clean_content
from omni_agent.schemas.message import FunctionCall, LLMResponse, Message, ToolCall


class TestLLMClientInit:
    def test_default_params(self) -> None:
        client = LLMClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.model == "gpt-4o"
        assert client.timeout == 120.0
        assert client.api_base is None
        assert client.thinking is False

    def test_custom_params(self) -> None:
        client = LLMClient(
            api_key="key",
            api_base="https://custom.api.com/v1/",
            model="anthropic/claude-3-5-sonnet",
            timeout=60.0,
            thinking=True,
            thinking_budget=4000,
        )
        assert client.api_key == "key"
        assert client.api_base == "https://custom.api.com/v1"
        assert client.model == "anthropic/claude-3-5-sonnet"
        assert client.timeout == 60.0
        assert client.thinking is True
        assert client.thinking_budget == 4000

    def test_api_base_trailing_slash_stripped(self) -> None:
        client = LLMClient(api_key="key", api_base="https://api.com/v1/")
        assert client.api_base == "https://api.com/v1"


class TestGetMaxTokensLimit:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("deepseek/deepseek-chat", 8192),
            ("qwen/qwen-max", 8192),
            ("openai/gpt-4o", 16384),
            ("anthropic/claude-3-5-sonnet", 8192),
            ("xai/grok-2", 16384),
            ("unknown/model", 16384),
        ],
    )
    def test_provider_limits(self, model: str, expected: int) -> None:
        client = LLMClient(api_key="key", model=model)
        assert client._get_max_tokens_limit() == expected


class TestAdjustMaxTokens:
    def test_within_limit(self) -> None:
        client = LLMClient(api_key="key", model="deepseek/deepseek-chat")
        assert client._adjust_max_tokens(4096) == 4096

    def test_exceeds_limit(self) -> None:
        client = LLMClient(api_key="key", model="deepseek/deepseek-chat")
        assert client._adjust_max_tokens(16384) == 8192

    def test_at_limit(self) -> None:
        client = LLMClient(api_key="key", model="deepseek/deepseek-chat")
        assert client._adjust_max_tokens(8192) == 8192


class TestConvertMessages:
    def test_system_message_extracted(self) -> None:
        client = LLMClient(api_key="key")
        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        system, api_msgs = client._convert_messages(messages)
        assert system == "You are helpful"
        assert len(api_msgs) == 1
        assert api_msgs[0]["role"] == "user"

    def test_user_message(self) -> None:
        client = LLMClient(api_key="key")
        messages = [Message(role="user", content="Hello")]
        system, api_msgs = client._convert_messages(messages)
        assert system is None
        assert api_msgs == [{"role": "user", "content": "Hello"}]

    def test_assistant_message_with_content(self) -> None:
        client = LLMClient(api_key="key")
        messages = [Message(role="assistant", content="Hi there")]
        _, api_msgs = client._convert_messages(messages)
        assert api_msgs[0]["role"] == "assistant"
        assert api_msgs[0]["content"] == "Hi there"

    def test_assistant_message_with_tool_calls(self) -> None:
        client = LLMClient(api_key="key")
        messages = [
            Message(
                role="assistant",
                content="Let me check",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        type="function",
                        function=FunctionCall(name="bash", arguments={"command": "ls"}),
                    )
                ],
            )
        ]
        _, api_msgs = client._convert_messages(messages)
        assert "tool_calls" in api_msgs[0]
        tc = api_msgs[0]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["function"]["name"] == "bash"

    def test_tool_message(self) -> None:
        client = LLMClient(api_key="key")
        messages = [Message(role="tool", content="result", tool_call_id="call_1")]
        _, api_msgs = client._convert_messages(messages)
        assert api_msgs[0]["role"] == "tool"
        assert api_msgs[0]["tool_call_id"] == "call_1"
        assert api_msgs[0]["content"] == "result"


class TestConvertTools:
    def test_none_tools(self) -> None:
        client = LLMClient(api_key="key")
        assert client._convert_tools(None) is None

    def test_empty_tools(self) -> None:
        client = LLMClient(api_key="key")
        assert client._convert_tools([]) is None

    def test_openai_format_passthrough(self) -> None:
        client = LLMClient(api_key="key")
        tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]
        result = client._convert_tools(tools)
        assert result == tools

    def test_anthropic_format_converted(self) -> None:
        client = LLMClient(api_key="key")
        tools = [
            {
                "name": "bash",
                "description": "Run command",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
        result = client._convert_tools(tools)
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "bash"
        assert result[0]["function"]["description"] == "Run command"


class TestCleanContent:
    def test_empty_content(self) -> None:
        assert _clean_content("") == ""
        assert _clean_content(None) is None

    def test_removes_has_function_call(self) -> None:
        result = _clean_content("Hello<has_function_call>bash.run")
        assert "<has_function_call>" not in result

    def test_removes_im_tags(self) -> None:
        result = _clean_content("Hello<|im_start|>system<|im_end|>")
        assert "<|im_start|>" not in result
        assert "<|im_end|>" not in result

    def test_preserves_normal_content(self) -> None:
        text = "Here is a Python function:\ndef hello():\n    return 'world'"
        result = _clean_content(text)
        assert "def hello():" in result


class TestGenerate:
    async def test_generate_basic(self) -> None:
        client = LLMClient(api_key="key")

        mock_choice = MagicMock()
        mock_choice.message.content = "Hello!"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("omni_agent.core.llm_client.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = mock_response
            result = await client.generate(messages=[Message(role="user", content="Hi")])

        assert isinstance(result, LLMResponse)
        assert "Hello" in result.content
        assert result.tool_calls is None
        assert result.finish_reason == "stop"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5

    async def test_generate_with_tool_calls(self) -> None:
        client = LLMClient(api_key="key")

        mock_tc = MagicMock()
        mock_tc.id = "call_abc"
        mock_tc.function.name = "bash"
        mock_tc.function.arguments = '{"command": "ls"}'

        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.message.tool_calls = [mock_tc]
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=20, completion_tokens=10)

        with patch("omni_agent.core.llm_client.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = mock_response
            result = await client.generate(messages=[Message(role="user", content="list files")])

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "bash"
        assert result.tool_calls[0].function.arguments == {"command": "ls"}

    async def test_generate_with_thinking(self) -> None:
        client = LLMClient(api_key="key")

        mock_choice = MagicMock()
        mock_choice.message.content = [
            {"type": "thinking", "thinking": "Let me think..."},
            {"type": "text", "text": "The answer is 42."},
        ]
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

        with patch("omni_agent.core.llm_client.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = mock_response
            result = await client.generate(messages=[Message(role="user", content="What is 6*7?")])

        assert result.thinking == "Let me think..."
        assert "42" in result.content

    async def test_generate_invalid_tool_args(self) -> None:
        client = LLMClient(api_key="key")

        mock_tc = MagicMock()
        mock_tc.id = "call_bad"
        mock_tc.function.name = "bash"
        mock_tc.function.arguments = "not-valid-json"

        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.message.tool_calls = [mock_tc]
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=0, completion_tokens=0)

        with patch("omni_agent.core.llm_client.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = mock_response
            result = await client.generate(messages=[Message(role="user", content="test")])

        assert result.tool_calls[0].function.arguments == {}
