"""记忆系统单元测试 - 覆盖 Markdown 存储、上下文注入、元数据、迁移、深度检索"""

import json
import tempfile
from pathlib import Path

import pytest

from omni_agent.core.memory import Memory, MemoryManager
from omni_agent.tools.memory_tools import DeepRecallMemoryTool


@pytest.fixture
def tmp_memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = Memory("test_user", "test_session", tmpdir)
        yield mem


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestMemoryFiles:
    """读写 profile/habit/context 文件"""

    def test_read_empty_profile(self, tmp_memory):
        assert tmp_memory.read_profile() == ""

    def test_write_and_read_profile(self, tmp_memory):
        tmp_memory.write_profile("- Python开发者\n- 偏好简洁代码\n")
        content = tmp_memory.read_profile()
        assert "Python开发者" in content
        assert "偏好简洁代码" in content

    def test_write_and_read_habit(self, tmp_memory):
        tmp_memory.write_habit("- 先写测试再写代码\n")
        content = tmp_memory.read_habit()
        assert "先写测试再写代码" in content

    def test_write_and_read_context(self, tmp_memory):
        tmp_memory.write_context("# 当前任务\n\n重构记忆系统\n")
        content = tmp_memory.read_context()
        assert "重构记忆系统" in content

    def test_append_profile(self, tmp_memory):
        tmp_memory.write_profile("- 条目1\n")
        tmp_memory.append_profile("- 条目2")
        content = tmp_memory.read_profile()
        assert "条目1" in content
        assert "条目2" in content

    def test_append_habit(self, tmp_memory):
        tmp_memory.write_habit("- 习惯1\n")
        tmp_memory.append_habit("- 习惯2")
        content = tmp_memory.read_habit()
        assert "习惯1" in content
        assert "习惯2" in content

    def test_append_context(self, tmp_memory):
        tmp_memory.write_context("# 任务\n")
        tmp_memory.append_context("## Round 1\n\n完成了第一步")
        content = tmp_memory.read_context()
        assert "任务" in content
        assert "Round 1" in content

    def test_append_to_empty(self, tmp_memory):
        tmp_memory.append_profile("- 新条目")
        content = tmp_memory.read_profile()
        assert "新条目" in content

    def test_profile_is_user_level(self, tmp_memory):
        """profile 存储在用户级目录，非 session 目录"""
        tmp_memory.write_profile("- 测试")
        assert tmp_memory.profile_path.parent == tmp_memory.user_dir
        assert "sessions" not in str(tmp_memory.profile_path)

    def test_habit_is_user_level(self, tmp_memory):
        """habit 存储在用户级目录"""
        tmp_memory.write_habit("- 测试")
        assert tmp_memory.habit_path.parent == tmp_memory.user_dir

    def test_context_is_session_level(self, tmp_memory):
        """context 存储在 session 目录"""
        tmp_memory.write_context("测试")
        assert "sessions" in str(tmp_memory.context_path)
        assert "test_session" in str(tmp_memory.context_path)

    def test_profile_shared_across_sessions(self, tmp_dir):
        """不同 session 共享同一个 profile"""
        mem1 = Memory("user1", "session_a", tmp_dir)
        mem1.write_profile("- 共享画像\n")

        mem2 = Memory("user1", "session_b", tmp_dir)
        assert "共享画像" in mem2.read_profile()

    def test_habit_shared_across_sessions(self, tmp_dir):
        """不同 session 共享同一个 habit"""
        mem1 = Memory("user1", "session_a", tmp_dir)
        mem1.write_habit("- 共享习惯\n")

        mem2 = Memory("user1", "session_b", tmp_dir)
        assert "共享习惯" in mem2.read_habit()


class TestContextForPrompt:
    """读 .md 拼接上下文"""

    def test_empty_returns_empty(self, tmp_memory):
        assert tmp_memory.get_context_for_prompt() == ""

    def test_profile_in_prompt(self, tmp_memory):
        tmp_memory.write_profile("- Python高级开发者\n")
        ctx = tmp_memory.get_context_for_prompt()
        assert "<user_memory>" in ctx
        assert "用户画像" in ctx
        assert "Python高级开发者" in ctx
        assert "</user_memory>" in ctx

    def test_habit_in_prompt(self, tmp_memory):
        tmp_memory.write_habit("- TDD开发流程\n")
        ctx = tmp_memory.get_context_for_prompt()
        assert "用户习惯" in ctx
        assert "TDD开发流程" in ctx

    def test_context_in_prompt(self, tmp_memory):
        tmp_memory.write_context("正在重构记忆系统")
        ctx = tmp_memory.get_context_for_prompt()
        assert "会话上下文" in ctx
        assert "正在重构记忆系统" in ctx

    def test_all_sections(self, tmp_memory):
        tmp_memory.write_profile("- 画像信息\n")
        tmp_memory.write_habit("- 习惯信息\n")
        tmp_memory.write_context("上下文信息")
        ctx = tmp_memory.get_context_for_prompt()
        assert "用户画像" in ctx
        assert "用户习惯" in ctx
        assert "会话上下文" in ctx


class TestMetadata:
    """meta.json 和 round_count"""

    def test_init_creates_meta(self, tmp_memory):
        tmp_memory.init_memory(task="测试任务")
        assert tmp_memory.meta_path.exists()
        meta = json.loads(tmp_memory.meta_path.read_text())
        assert "created_at" in meta
        assert "updated_at" in meta
        assert meta["round_count"] == 0

    def test_increment_round(self, tmp_memory):
        tmp_memory.init_memory()
        assert tmp_memory.round_count == 0

        r1 = tmp_memory.increment_round()
        assert r1 == 1
        assert tmp_memory.round_count == 1

        r2 = tmp_memory.increment_round()
        assert r2 == 2
        assert tmp_memory.round_count == 2

    def test_exists_after_init(self, tmp_memory):
        assert not tmp_memory.exists() or tmp_memory.meta_path.exists()
        tmp_memory.init_memory()
        assert tmp_memory.exists()

    def test_delete_removes_session(self, tmp_memory):
        tmp_memory.init_memory(task="test")
        tmp_memory.write_context("content")
        assert tmp_memory.session_dir.exists()
        tmp_memory.delete()
        assert not tmp_memory.session_dir.exists()

    def test_get_memory_paths(self, tmp_memory):
        paths = tmp_memory.get_memory_paths()
        assert "profile" in paths
        assert "habit" in paths
        assert "context" in paths
        assert "meta" in paths

    def test_init_memory_with_task(self, tmp_memory):
        tmp_memory.init_memory(task="实现登录功能")
        content = tmp_memory.read_context()
        assert "实现登录功能" in content


class TestMigration:
    """旧 JSON -> .md 自动迁移"""

    def test_migrate_profile_and_habit(self, tmp_dir):
        """旧 JSON 中的 profile/habit 条目迁移到 .md"""
        old_session_dir = Path(tmp_dir) / "user1" / "sess1"
        old_session_dir.mkdir(parents=True)

        old_data = {
            "version": "2.0",
            "meta": {
                "user_id": "user1",
                "session_id": "sess1",
                "created_at": "2026-01-01 00:00:00",
                "updated_at": "2026-01-15 00:00:00",
            },
            "context": {"task": "旧任务", "workspace": "", "preferences": {}},
            "memories": {
                "session": [
                    {"id": "s1", "content": "对话1", "type": "session"},
                    {"id": "s2", "content": "对话2", "type": "session"},
                ],
                "profile": [
                    {"id": "p1", "content": "Python开发者", "type": "profile"},
                    {"id": "p2", "content": "偏好vim", "type": "profile"},
                ],
                "task": [
                    {
                        "id": "t1",
                        "content": "完成登录",
                        "type": "task",
                        "metadata": {"status": "active"},
                    },
                ],
                "habit": [
                    {"id": "h1", "content": "TDD流程", "type": "habit"},
                ],
            },
            "summary": {
                "core_facts": ["事实1", "事实2"],
                "decisions": [],
                "last_compressed_at": None,
            },
        }

        old_path = old_session_dir / "memory.json"
        old_path.write_text(json.dumps(old_data, ensure_ascii=False))

        mem = Memory("user1", "sess1", tmp_dir)

        profile = mem.read_profile()
        assert "Python开发者" in profile
        assert "偏好vim" in profile

        habit = mem.read_habit()
        assert "TDD流程" in habit

        context = mem.read_context()
        assert "旧任务" in context
        assert "事实1" in context
        assert "完成登录" in context

        meta = mem.meta
        assert meta["round_count"] == 1
        assert meta["created_at"] == "2026-01-01 00:00:00"

    def test_migrate_creates_backup(self, tmp_dir):
        """迁移后旧 JSON 重命名为 .json.bak"""
        old_session_dir = Path(tmp_dir) / "user1" / "sess1"
        old_session_dir.mkdir(parents=True)

        old_data = {
            "version": "2.0",
            "meta": {"user_id": "user1", "session_id": "sess1", "created_at": "", "updated_at": ""},
            "context": {"task": "", "workspace": "", "preferences": {}},
            "memories": {"session": [], "profile": [], "task": [], "habit": []},
            "summary": {"core_facts": [], "decisions": [], "last_compressed_at": None},
        }
        old_path = old_session_dir / "memory.json"
        old_path.write_text(json.dumps(old_data))

        old_detail = old_session_dir / "memory_detail.json"
        old_detail.write_text("{}")

        Memory("user1", "sess1", tmp_dir)

        assert not old_path.exists()
        assert (old_session_dir / "memory.json.bak").exists()
        assert not old_detail.exists()
        assert (old_session_dir / "memory_detail.json.bak").exists()

    def test_no_migration_without_old_json(self, tmp_dir):
        """没有旧 JSON 时不触发迁移"""
        mem = Memory("user1", "sess1", tmp_dir)
        assert mem.read_profile() == ""
        assert mem.read_habit() == ""
        assert mem.read_context() == ""

    def test_migration_preserves_existing_md(self, tmp_dir):
        """已有 .md 文件时不覆盖"""
        old_session_dir = Path(tmp_dir) / "user1" / "sess1"
        old_session_dir.mkdir(parents=True)

        user_dir = Path(tmp_dir) / "user1"
        profile_path = user_dir / "profile.md"
        profile_path.write_text("- 已有画像\n")

        old_data = {
            "version": "2.0",
            "meta": {"user_id": "user1", "session_id": "sess1", "created_at": "", "updated_at": ""},
            "context": {"task": "", "workspace": "", "preferences": {}},
            "memories": {
                "session": [],
                "profile": [{"id": "p1", "content": "新画像", "type": "profile"}],
                "task": [],
                "habit": [],
            },
            "summary": {"core_facts": [], "decisions": [], "last_compressed_at": None},
        }
        (old_session_dir / "memory.json").write_text(json.dumps(old_data))

        mem = Memory("user1", "sess1", tmp_dir)
        assert "已有画像" in mem.read_profile()
        assert "新画像" not in mem.read_profile()


class TestDeepRecallMemoryTool:
    """关键词搜索 .md 内容"""

    @pytest.fixture
    def deep_tool(self, tmp_memory):
        tmp_memory.write_profile(
            "- Python高级开发者，偏好vim编辑器\n"
            "- 使用macOS和zsh终端\n"
        )
        tmp_memory.write_habit(
            "- 先写测试再写代码(TDD)\n"
            "- 使用git进行版本管理\n"
        )
        tmp_memory.write_context(
            "# 当前任务\n\n重构记忆系统，从JSON迁移到Markdown\n\n"
            "## Round 1\n\n完成了Memory类的重写\n"
        )
        return DeepRecallMemoryTool(tmp_memory, "test_user", "test_session")

    @pytest.mark.asyncio
    async def test_keyword_search_profile(self, deep_tool):
        result = await deep_tool.execute(query="Python", mode="keyword")
        assert result.success
        assert "Python" in result.content

    @pytest.mark.asyncio
    async def test_keyword_search_habit(self, deep_tool):
        result = await deep_tool.execute(query="TDD", mode="keyword")
        assert result.success
        assert "TDD" in result.content

    @pytest.mark.asyncio
    async def test_keyword_search_context(self, deep_tool):
        result = await deep_tool.execute(query="重构", mode="keyword")
        assert result.success
        assert "重构" in result.content

    @pytest.mark.asyncio
    async def test_keyword_search_no_result(self, deep_tool):
        result = await deep_tool.execute(query="不存在的关键词XYZ", mode="keyword")
        assert result.success
        assert "没有找到" in result.content

    @pytest.mark.asyncio
    async def test_keyword_search_with_type_filter(self, deep_tool):
        result = await deep_tool.execute(
            query="vim", mode="keyword", memory_type="profile"
        )
        assert result.success
        assert "vim" in result.content

    @pytest.mark.asyncio
    async def test_keyword_search_type_filter_excludes_other(self, deep_tool):
        result = await deep_tool.execute(
            query="重构", mode="keyword", memory_type="profile"
        )
        assert result.success
        assert "没有找到" in result.content

    @pytest.mark.asyncio
    async def test_no_query_returns_error(self, deep_tool):
        result = await deep_tool.execute()
        assert not result.success
        assert "请提供" in result.error

    @pytest.mark.asyncio
    async def test_hybrid_falls_back_to_keyword(self, deep_tool):
        result = await deep_tool.execute(query="macOS", mode="hybrid")
        assert result.success
        assert "macOS" in result.content


class TestMemoryManager:
    """新目录结构下的管理操作"""

    def test_list_sessions(self, tmp_dir):
        mgr = MemoryManager(tmp_dir)
        mem1 = mgr.get_memory("user1", "sess_a")
        mem1.init_memory()
        mem2 = mgr.get_memory("user1", "sess_b")
        mem2.init_memory()

        sessions = mgr.list_sessions("user1")
        assert set(sessions) == {"sess_a", "sess_b"}

    def test_list_users(self, tmp_dir):
        mgr = MemoryManager(tmp_dir)
        mgr.get_memory("alice", "s1").init_memory()
        mgr.get_memory("bob", "s1").init_memory()

        users = mgr.list_users()
        assert "alice" in users
        assert "bob" in users

    def test_delete_session(self, tmp_dir):
        mgr = MemoryManager(tmp_dir)
        mem = mgr.get_memory("user1", "sess1")
        mem.init_memory()
        assert mgr.delete_session("user1", "sess1")
        assert "sess1" not in mgr.list_sessions("user1")

    def test_delete_user(self, tmp_dir):
        mgr = MemoryManager(tmp_dir)
        mgr.get_memory("user1", "sess1").init_memory()
        assert mgr.delete_user("user1")
        assert "user1" not in mgr.list_users()

    def test_get_stats(self, tmp_dir):
        mgr = MemoryManager(tmp_dir)
        mgr.get_memory("u1", "s1").init_memory()
        mgr.get_memory("u1", "s2").init_memory()
        mgr.get_memory("u2", "s1").init_memory()

        stats = mgr.get_stats()
        assert stats["users"] == 2
        assert stats["sessions"] == 3

    def test_delete_nonexistent_returns_false(self, tmp_dir):
        mgr = MemoryManager(tmp_dir)
        assert not mgr.delete_session("ghost", "phantom")
        assert not mgr.delete_user("ghost")
