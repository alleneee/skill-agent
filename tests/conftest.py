"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from omni_agent.core.config import Settings
from omni_agent.main import app


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
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
    """Create test client."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
