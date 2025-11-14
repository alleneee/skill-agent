"""Tests for Session Note Tool."""

import json
import pytest
from pathlib import Path
from fastapi_agent.tools.note_tool import SessionNoteTool, RecallNoteTool


@pytest.fixture
def temp_memory_file(tmp_path):
    """Create a temporary memory file."""
    return str(tmp_path / ".agent_memory.json")


@pytest.fixture
def session_tool(temp_memory_file):
    """Create SessionNoteTool instance."""
    return SessionNoteTool(memory_file=temp_memory_file)


@pytest.fixture
def recall_tool(temp_memory_file):
    """Create RecallNoteTool instance."""
    return RecallNoteTool(memory_file=temp_memory_file)


@pytest.mark.asyncio
async def test_record_note_creates_file(session_tool, temp_memory_file):
    """Test that recording a note creates the memory file."""
    # Record a note
    result = await session_tool.execute(
        content="用户偏好简洁的回复",
        category="user_preference"
    )

    # Check result
    assert result.success is True
    assert "已记录笔记" in result.content

    # Check file exists
    assert Path(temp_memory_file).exists()

    # Check file content
    with open(temp_memory_file, 'r', encoding='utf-8') as f:
        notes = json.load(f)

    assert len(notes) == 1
    assert notes[0]["content"] == "用户偏好简洁的回复"
    assert notes[0]["category"] == "user_preference"
    assert "timestamp" in notes[0]


@pytest.mark.asyncio
async def test_record_multiple_notes(session_tool, temp_memory_file):
    """Test recording multiple notes."""
    # Record first note
    await session_tool.execute(
        content="项目使用 Python 3.12",
        category="project_info"
    )

    # Record second note
    await session_tool.execute(
        content="用户喜欢 FastAPI",
        category="user_preference"
    )

    # Check file content
    with open(temp_memory_file, 'r', encoding='utf-8') as f:
        notes = json.load(f)

    assert len(notes) == 2
    assert notes[0]["content"] == "项目使用 Python 3.12"
    assert notes[1]["content"] == "用户喜欢 FastAPI"


@pytest.mark.asyncio
async def test_recall_notes_empty(recall_tool):
    """Test recalling notes when no notes exist."""
    result = await recall_tool.execute()

    assert result.success is True
    assert "尚未记录任何笔记" in result.content


@pytest.mark.asyncio
async def test_recall_all_notes(session_tool, recall_tool):
    """Test recalling all notes."""
    # Record some notes
    await session_tool.execute(content="第一条笔记", category="general")
    await session_tool.execute(content="第二条笔记", category="project")

    # Recall all notes
    result = await recall_tool.execute()

    assert result.success is True
    assert "已记录的笔记" in result.content
    assert "第一条笔记" in result.content
    assert "第二条笔记" in result.content
    assert "[general]" in result.content
    assert "[project]" in result.content


@pytest.mark.asyncio
async def test_recall_notes_by_category(session_tool, recall_tool):
    """Test recalling notes filtered by category."""
    # Record notes with different categories
    await session_tool.execute(content="用户信息", category="user")
    await session_tool.execute(content="项目信息", category="project")
    await session_tool.execute(content="另一个用户信息", category="user")

    # Recall only 'user' category
    result = await recall_tool.execute(category="user")

    assert result.success is True
    assert "用户信息" in result.content
    assert "另一个用户信息" in result.content
    assert "项目信息" not in result.content


@pytest.mark.asyncio
async def test_recall_notes_category_not_found(session_tool, recall_tool):
    """Test recalling notes with non-existent category."""
    # Record a note
    await session_tool.execute(content="测试笔记", category="test")

    # Try to recall non-existent category
    result = await recall_tool.execute(category="nonexistent")

    assert result.success is True
    assert "未找到分类为 'nonexistent' 的笔记" in result.content


@pytest.mark.asyncio
async def test_tool_schemas():
    """Test that tools have correct schemas."""
    session_tool = SessionNoteTool()
    recall_tool = RecallNoteTool()

    # Check SessionNoteTool schema
    session_schema = session_tool.to_schema()
    assert session_schema["function"]["name"] == "record_note"
    assert "content" in session_schema["function"]["parameters"]["properties"]
    assert "category" in session_schema["function"]["parameters"]["properties"]

    # Check RecallNoteTool schema
    recall_schema = recall_tool.to_schema()
    assert recall_schema["function"]["name"] == "recall_notes"
    assert "category" in recall_schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_default_category(session_tool):
    """Test that default category is 'general'."""
    # Record note without specifying category
    await session_tool.execute(content="测试笔记")

    # Read from file
    memory_file = session_tool.memory_file
    with open(memory_file, 'r', encoding='utf-8') as f:
        notes = json.load(f)

    assert notes[0]["category"] == "general"
