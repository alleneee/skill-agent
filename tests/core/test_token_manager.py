from unittest.mock import AsyncMock, MagicMock

import pytest

from omni_agent.core.token_manager import TokenManager
from omni_agent.schemas.message import LLMResponse, Message


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.generate = AsyncMock(
        return_value=LLMResponse(content="summary of conversation", finish_reason="stop")
    )
    return client


@pytest.fixture
def token_manager(mock_llm_client) -> TokenManager:
    return TokenManager(
        llm_client=mock_llm_client,
        token_limit=1000,
        enable_summarization=True,
        summarize_after_rounds=2,
    )


class TestTokenManagerInit:
    def test_default_params(self, mock_llm_client) -> None:
        tm = TokenManager(llm_client=mock_llm_client)
        assert tm.token_limit == 120000
        assert tm.enable_summarization is True
        assert tm.summarize_after_rounds == 2
        assert tm.core_memory == ""

    def test_custom_params(self, mock_llm_client) -> None:
        tm = TokenManager(
            llm_client=mock_llm_client,
            token_limit=50000,
            enable_summarization=False,
            summarize_after_rounds=5,
        )
        assert tm.token_limit == 50000
        assert tm.enable_summarization is False
        assert tm.summarize_after_rounds == 5

    def test_tiktoken_available(self, mock_llm_client) -> None:
        tm = TokenManager(llm_client=mock_llm_client)
        assert tm.tiktoken_available is True
        assert tm.encoding is not None


class TestEstimateTokens:
    def test_empty_messages(self, token_manager) -> None:
        assert token_manager.estimate_tokens([]) == 0

    def test_single_string_message(self, token_manager) -> None:
        messages = [Message(role="user", content="hello world")]
        tokens = token_manager.estimate_tokens(messages)
        assert tokens > 0

    def test_message_with_list_content(self, token_manager) -> None:
        messages = [Message(role="user", content=[{"type": "text", "text": "hello"}])]
        tokens = token_manager.estimate_tokens(messages)
        assert tokens > 0

    def test_message_with_thinking(self, token_manager) -> None:
        messages = [Message(role="assistant", content="reply", thinking="let me think")]
        tokens = token_manager.estimate_tokens(messages)
        assert tokens > 4

    def test_message_with_tool_calls(self, token_manager) -> None:
        from omni_agent.schemas.message import FunctionCall, ToolCall

        messages = [
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        type="function",
                        function=FunctionCall(name="bash", arguments={"command": "ls"}),
                    )
                ],
            )
        ]
        tokens = token_manager.estimate_tokens(messages)
        assert tokens > 0

    def test_metadata_overhead(self, token_manager) -> None:
        messages = [Message(role="user", content="")]
        tokens = token_manager.estimate_tokens(messages)
        assert tokens >= 4

    def test_multiple_messages(self, token_manager) -> None:
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        tokens = token_manager.estimate_tokens(messages)
        assert tokens > 12


class TestEstimateTokensFallback:
    def test_fallback_estimation(self, mock_llm_client) -> None:
        tm = TokenManager(llm_client=mock_llm_client)
        tm.tiktoken_available = False
        tm.encoding = None
        messages = [Message(role="user", content="hello world")]
        tokens = tm.estimate_tokens(messages)
        assert tokens > 0
        assert tokens == int(len("hello world") / 2.5)

    def test_fallback_with_thinking(self, mock_llm_client) -> None:
        tm = TokenManager(llm_client=mock_llm_client)
        tm.tiktoken_available = False
        tm.encoding = None
        messages = [Message(role="assistant", content="reply", thinking="thoughts")]
        tokens = tm.estimate_tokens(messages)
        expected = int((len("reply") + len("thoughts")) / 2.5)
        assert tokens == expected


class TestMaybeSummarizeMessages:
    async def test_no_summarization_when_disabled(self, mock_llm_client) -> None:
        tm = TokenManager(
            llm_client=mock_llm_client,
            enable_summarization=False,
        )
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="q3"),
        ]
        result = await tm.maybe_summarize_messages(messages)
        assert result is messages

    async def test_no_summarization_below_threshold(self, mock_llm_client) -> None:
        tm = TokenManager(
            llm_client=mock_llm_client,
            token_limit=999999,
            summarize_after_rounds=10,
        )
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi"),
        ]
        result = await tm.maybe_summarize_messages(messages)
        assert result is messages

    async def test_summarization_triggered_by_rounds(self, mock_llm_client) -> None:
        tm = TokenManager(
            llm_client=mock_llm_client,
            token_limit=999999,
            summarize_after_rounds=2,
        )
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="q3"),
            Message(role="assistant", content="a3"),
        ]
        result = await tm.maybe_summarize_messages(messages)
        assert len(result) < len(messages)
        assert result[0].role == "system"
        assert result[0].content == "sys"

    async def test_summarization_triggered_by_token_limit(self, mock_llm_client) -> None:
        tm = TokenManager(
            llm_client=mock_llm_client,
            token_limit=10,
            summarize_after_rounds=100,
        )
        messages = [
            Message(role="system", content="system prompt " * 20),
            Message(role="user", content="first question " * 20),
            Message(role="assistant", content="first answer " * 20),
            Message(role="user", content="second question " * 20),
            Message(role="assistant", content="second answer " * 20),
            Message(role="user", content="third question " * 20),
            Message(role="assistant", content="third answer " * 20),
        ]
        result = await tm.maybe_summarize_messages(messages)
        assert len(result) < len(messages)

    async def test_summarization_preserves_system_prompt(self, token_manager) -> None:
        messages = [
            Message(role="system", content="system prompt"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="q3"),
        ]
        result = await token_manager.maybe_summarize_messages(messages)
        assert result[0].role == "system"
        assert result[0].content == "system prompt"

    async def test_summarization_preserves_last_round(self, token_manager) -> None:
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="last_question"),
        ]
        result = await token_manager.maybe_summarize_messages(messages)
        last_user = [m for m in result if m.role == "user" and "last_question" in str(m.content)]
        assert len(last_user) == 1

    async def test_core_memory_stored(self, token_manager) -> None:
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="q3"),
        ]
        await token_manager.maybe_summarize_messages(messages)
        assert token_manager.core_memory != ""

    async def test_single_round_not_compressed(self, mock_llm_client) -> None:
        tm = TokenManager(
            llm_client=mock_llm_client,
            token_limit=10,
            summarize_after_rounds=0,
        )
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
        ]
        result = await tm.maybe_summarize_messages(messages)
        assert result is messages


class TestExtractCoreMemory:
    async def test_successful_extraction(self, token_manager, mock_llm_client) -> None:
        messages = [
            Message(role="user", content="Write a function"),
            Message(role="assistant", content="Here is the function"),
        ]
        result = await token_manager._extract_core_memory(messages, 1)
        assert result == "summary of conversation"
        mock_llm_client.generate.assert_called_once()

    async def test_extraction_failure_returns_fallback(self, mock_llm_client) -> None:
        mock_llm_client.generate = AsyncMock(side_effect=Exception("API error"))
        tm = TokenManager(llm_client=mock_llm_client)
        messages = [Message(role="user", content="hello")]
        result = await tm._extract_core_memory(messages, 1)
        assert "extraction failed" in result

    async def test_extraction_includes_tool_calls(self, token_manager, mock_llm_client) -> None:
        from omni_agent.schemas.message import FunctionCall, ToolCall

        messages = [
            Message(
                role="assistant",
                content="Let me check",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        type="function",
                        function=FunctionCall(name="bash", arguments={"command": "ls"}),
                    )
                ],
            ),
            Message(role="tool", content="file1.py\nfile2.py", tool_call_id="c1"),
        ]
        await token_manager._extract_core_memory(messages, 1)
        call_args = mock_llm_client.generate.call_args
        prompt_content = (
            call_args[1]["messages"][1].content
            if "messages" in call_args[1]
            else call_args[0][0][1].content
        )
        assert "bash" in prompt_content
