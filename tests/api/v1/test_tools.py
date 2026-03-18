"""Tests for tools endpoints."""

from fastapi.testclient import TestClient


def test_list_tools(client: TestClient) -> None:
    """Test list tools endpoint."""
    response = client.get("/api/v1/tools/")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) > 0

    # Check tool structure
    tool = data["tools"][0]
    assert "name" in tool
    assert "description" in tool
    assert "parameters" in tool
