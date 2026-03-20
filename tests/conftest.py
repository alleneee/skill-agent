"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from omni_agent.core.config import Settings
from omni_agent.core.llm_client import LLMClient
from omni_agent.core.token_manager import TokenManager
from omni_agent.core.tool_executor import ToolExecutor
from omni_agent.main import app
from omni_agent.schemas.message import LLMResponse, TokenUsage
from omni_agent.tools.base import Tool, ToolResult


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        DEBUG=True,
        LLM_API_KEY="test-api-key",
        LLM_API_BASE="https://api.test.com",
        LLM_MODEL="test-model",
        AGENT_MAX_STEPS=10,
        AGENT_WORKSPACE_DIR="./test_workspace",
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock(spec=LLMClient)
    client.generate = AsyncMock(
        return_value=LLMResponse(
            content="mock response",
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
        )
    )
    client.generate_stream = AsyncMock()
    client.model = "test/model"
    client.api_key = "test-key"
    return client


@pytest.fixture
def mock_token_manager(mock_llm_client) -> MagicMock:
    tm = MagicMock(spec=TokenManager)
    tm.estimate_tokens = MagicMock(return_value=100)
    tm.maybe_summarize_messages = AsyncMock(side_effect=lambda msgs: msgs)
    tm.token_limit = 120000
    tm.core_memory = ""
    return tm


@pytest.fixture
def mock_tool_executor() -> MagicMock:
    executor = MagicMock(spec=ToolExecutor)
    executor.tool_names = []
    executor.has_tool = MagicMock(return_value=False)
    executor.get_tool = MagicMock(return_value=None)
    return executor


class MockTool(Tool):
    def __init__(self, name: str = "mock_tool", should_fail: bool = False):
        self._name = name
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock tool: {self._name}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": [],
        }

    async def execute(self, **kwargs) -> ToolResult:
        if self._should_fail:
            return ToolResult(success=False, error="Mock failure")
        return ToolResult(success=True, content=f"mock result: {kwargs}")


@pytest.fixture
def mock_tool() -> MockTool:
    return MockTool()


@pytest.fixture
def mock_tools() -> dict[str, Tool]:
    return {
        "mock_tool": MockTool("mock_tool"),
        "fail_tool": MockTool("fail_tool", should_fail=True),
    }


@pytest.fixture
def workspace(tmp_path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws
