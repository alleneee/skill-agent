"""Session Manager 单元测试

测试内容:
1. AgentSession / TeamSession 数据类
2. UnifiedAgentSessionManager / UnifiedTeamSessionManager 统一接口
3. FileStorage 文件存储后端
4. 会话持久化和恢复
5. 会话清理和裁剪
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from omni_agent.core.session import (
    AgentRunRecord,
    AgentSession,
    RunRecord,
    TeamSession,
)
from omni_agent.core.session_manager import (
    UnifiedAgentSessionManager,
    UnifiedTeamSessionManager,
)
from omni_agent.core.session_storage import FileStorage


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_storage_path():
    """创建临时存储路径."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    yield path
    # 清理
    if os.path.exists(path):
        os.unlink(path)
    # 清理 .tmp 文件
    tmp_path = path + ".tmp"
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)


@pytest.fixture
def agent_run_record():
    """创建测试用 AgentRunRecord."""
    return AgentRunRecord(
        run_id=str(uuid.uuid4()),
        task="Test task",
        response="Test response",
        success=True,
        steps=3,
        timestamp=time.time(),
        metadata={"test": True},
    )


@pytest.fixture
def team_run_record():
    """创建测试用 RunRecord."""
    return RunRecord(
        run_id=str(uuid.uuid4()),
        parent_run_id=None,
        runner_type="team_leader",
        runner_name="Test Team",
        task="Test task",
        response="Test response",
        success=True,
        steps=5,
        timestamp=time.time(),
        metadata={"test": True},
    )


# ============================================================================
# AgentSession Tests
# ============================================================================


class TestAgentSession:
    """AgentSession 数据类测试."""

    def test_create_session(self):
        """测试创建会话."""
        session = AgentSession(
            session_id="test-session",
            agent_name="test-agents",
            user_id="user-1",
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        assert session.session_id == "test-session"
        assert session.agent_name == "test-agents"
        assert session.user_id == "user-1"
        assert len(session.runs) == 0

    def test_add_run(self, agent_run_record):
        """测试添加运行记录."""
        session = AgentSession(
            session_id="test-session",
            agent_name="test-agents",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        old_updated_at = session.updated_at
        time.sleep(0.01)  # 确保时间戳不同
        session.add_run(agent_run_record)

        assert len(session.runs) == 1
        assert session.runs[0].task == "Test task"
        assert session.updated_at > old_updated_at

    def test_get_history_messages(self, agent_run_record):
        """测试获取历史消息."""
        session = AgentSession(
            session_id="test-session",
            agent_name="test-agents",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        # 添加多条记录
        for i in range(5):
            run = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task=f"Task {i}",
                response=f"Response {i}",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            session.add_run(run)

        # 获取最近 3 条
        messages = session.get_history_messages(num_runs=3)
        assert len(messages) == 6  # 3 runs * 2 messages (user + assistant)
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Task 2"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Response 2"

    def test_get_history_context(self):
        """测试获取历史上下文."""
        session = AgentSession(
            session_id="test-session",
            agent_name="test-agents",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        # 添加记录
        run = AgentRunRecord(
            run_id=str(uuid.uuid4()),
            task="What is Python?",
            response="Python is a programming language.",
            success=True,
            steps=1,
            timestamp=time.time(),
            metadata={},
        )
        session.add_run(run)

        context = session.get_history_context(num_runs=1)
        assert "<conversation_history>" in context
        assert "What is Python?" in context
        assert "Python is a programming language." in context
        assert "</conversation_history>" in context

    def test_get_runs_count(self, agent_run_record):
        """测试获取运行次数."""
        session = AgentSession(
            session_id="test-session",
            agent_name="test-agents",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        assert session.get_runs_count() == 0

        session.add_run(agent_run_record)
        assert session.get_runs_count() == 1


# ============================================================================
# TeamSession Tests
# ============================================================================


class TestTeamSession:
    """TeamSession 数据类测试."""

    def test_create_session(self):
        """测试创建 Team 会话."""
        session = TeamSession(
            session_id="team-session",
            team_name="Test Team",
            user_id="user-1",
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        assert session.session_id == "team-session"
        assert session.team_name == "Test Team"

    def test_add_run(self, team_run_record):
        """测试添加运行记录."""
        session = TeamSession(
            session_id="team-session",
            team_name="Test Team",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        session.add_run(team_run_record)
        assert len(session.runs) == 1

    def test_get_history_context_leader_only(self):
        """测试历史上下文只包含 leader runs."""
        session = TeamSession(
            session_id="team-session",
            team_name="Test Team",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        # 添加 leader run
        leader_run = RunRecord(
            run_id="leader-1",
            parent_run_id=None,
            runner_type="team_leader",
            runner_name="Test Team",
            task="Leader task",
            response="Leader response",
            success=True,
            steps=1,
            timestamp=time.time(),
            metadata={},
        )
        session.add_run(leader_run)

        # 添加 member run
        member_run = RunRecord(
            run_id="member-1",
            parent_run_id="leader-1",
            runner_type="member",
            runner_name="Helper",
            task="Member task",
            response="Member response",
            success=True,
            steps=1,
            timestamp=time.time(),
            metadata={},
        )
        session.add_run(member_run)

        context = session.get_history_context(num_runs=10)
        assert "Leader task" in context
        assert "Member task" not in context  # member runs 不应该出现在历史上下文中

    def test_get_member_interactions(self):
        """测试获取成员交互记录."""
        session = TeamSession(
            session_id="team-session",
            team_name="Test Team",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        # 添加 leader run
        leader_run = RunRecord(
            run_id="leader-1",
            parent_run_id=None,
            runner_type="team_leader",
            runner_name="Test Team",
            task="Leader task",
            response="Leader response",
            success=True,
            steps=1,
            timestamp=time.time(),
            metadata={},
        )
        session.add_run(leader_run)

        # 添加 member run
        member_run = RunRecord(
            run_id="member-1",
            parent_run_id="leader-1",
            runner_type="member",
            runner_name="Helper",
            task="Member task",
            response="Member response",
            success=True,
            steps=1,
            timestamp=time.time(),
            metadata={},
        )
        session.add_run(member_run)

        interactions = session.get_member_interactions("leader-1")
        assert "Helper" in interactions
        assert "Member task" in interactions
        assert "Member response" in interactions

    def test_get_runs_count(self, team_run_record):
        """测试获取运行统计."""
        session = TeamSession(
            session_id="team-session",
            team_name="Test Team",
            user_id=None,
            runs=[],
            state={},
            created_at=time.time(),
            updated_at=time.time(),
        )

        session.add_run(team_run_record)

        # 添加 member run
        member_run = RunRecord(
            run_id="member-1",
            parent_run_id=team_run_record.run_id,
            runner_type="member",
            runner_name="Helper",
            task="Member task",
            response="Member response",
            success=True,
            steps=1,
            timestamp=time.time(),
            metadata={},
        )
        session.add_run(member_run)

        stats = session.get_runs_count()
        assert stats["total"] == 2
        assert stats["leader"] == 1
        assert stats["member"] == 1


# ============================================================================
# FileStorage Tests
# ============================================================================


class TestFileStorage:
    """FileStorage 测试."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, temp_storage_path):
        """测试保存和获取."""
        storage = FileStorage(temp_storage_path)

        data = {"session_id": "test", "value": 123}
        await storage.save_session("test", data)

        loaded = await storage.get_session("test")
        assert loaded == data

    @pytest.mark.asyncio
    async def test_delete(self, temp_storage_path):
        """测试删除."""
        storage = FileStorage(temp_storage_path)

        await storage.save_session("test", {"value": 1})
        assert await storage.delete_session("test") is True
        assert await storage.get_session("test") is None
        assert await storage.delete_session("test") is False

    @pytest.mark.asyncio
    async def test_list_sessions(self, temp_storage_path):
        """测试列出会话."""
        storage = FileStorage(temp_storage_path)

        await storage.save_session("session-1", {"value": 1})
        await storage.save_session("session-2", {"value": 2})

        sessions = await storage.list_sessions()
        assert set(sessions) == {"session-1", "session-2"}

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, temp_storage_path):
        """测试清理过期会话."""
        storage = FileStorage(temp_storage_path)

        # 保存一个 "旧" 会话
        await storage.save_session("old", {
            "value": 1,
            "updated_at": time.time() - (8 * 86400)
        })
        # 保存一个新会话
        await storage.save_session("new", {
            "value": 2,
            "updated_at": time.time()
        })

        cleaned = await storage.cleanup_expired(7 * 86400)
        assert cleaned == 1

        sessions = await storage.list_sessions()
        assert "old" not in sessions
        assert "new" in sessions


# ============================================================================
# UnifiedAgentSessionManager Tests
# ============================================================================


class TestUnifiedAgentSessionManager:
    """UnifiedAgentSessionManager 测试."""

    @pytest.mark.asyncio
    async def test_file_backend(self, temp_storage_path):
        """测试文件后端."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session = await manager.get_session("test-session", "test-agents")
            assert session.session_id == "test-session"

            run = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Test task",
                response="Test response",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run("test-session", run)

            # 验证持久化
            session = await manager.get_session("test-session", "test-agents")
            assert len(session.runs) == 1
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_delete_session(self, temp_storage_path):
        """测试删除会话."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            # 创建会话并添加运行记录以确保它被保存到存储
            session = await manager.get_session("test-session", "test-agents")
            run = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Test task",
                response="Test response",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run("test-session", run)
            
            # 现在删除应该成功
            assert await manager.delete_session("test-session") is True
            # 再次删除应该失败（已不存在）
            assert await manager.delete_session("test-session") is False
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, temp_storage_path):
        """测试清理过期会话."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            # 创建会话并手动设置为过期
            session = await manager.get_session("old-session", "test-agents")
            session.updated_at = time.time() - (8 * 86400)
            # 保存更新
            await manager._storage.save_session(
                "old-session",
                manager._serialize_agent_session(session)
            )

            cleaned = await manager.cleanup_old_sessions(max_age_days=7)
            assert cleaned >= 1
        finally:
            await manager.close()


# ============================================================================
# UnifiedTeamSessionManager Tests
# ============================================================================


class TestUnifiedTeamSessionManager:
    """UnifiedTeamSessionManager 测试."""

    @pytest.mark.asyncio
    async def test_file_backend(self, temp_storage_path):
        """测试文件后端."""
        manager = UnifiedTeamSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session = await manager.get_session("test-session", "Test Team")
            assert session.session_id == "test-session"
            assert session.team_name == "Test Team"

            run = RunRecord(
                run_id=str(uuid.uuid4()),
                parent_run_id=None,
                runner_type="team_leader",
                runner_name="Test Team",
                task="Test task",
                response="Test response",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run("test-session", run)

            session = await manager.get_session("test-session", "Test Team")
            assert len(session.runs) == 1
        finally:
            await manager.close()


# ============================================================================
# Integration Tests
# ============================================================================


class TestSessionIntegration:
    """集成测试."""

    @pytest.mark.asyncio
    async def test_multi_round_conversation(self, temp_storage_path):
        """测试多轮对话场景."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session_id = "conversation-test"

            # 第一轮对话
            session = await manager.get_session(session_id, "assistant")
            run1 = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="What is Python?",
                response="Python is a programming language.",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run(session_id, run1)

            # 第二轮对话
            run2 = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Tell me more about it.",
                response="Python is known for its simplicity...",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run(session_id, run2)

            # 验证历史上下文
            session = await manager.get_session(session_id, "assistant")
            context = session.get_history_context(num_runs=2)

            assert "What is Python?" in context
            assert "Tell me more about it." in context
            assert len(session.runs) == 2
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_session_persistence_across_instances(self, temp_storage_path):
        """测试跨实例的会话持久化."""
        session_id = "persist-test"

        # 第一个实例：创建会话
        manager1 = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )
        try:
            await manager1.get_session(session_id, "test-agents")
            run = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Initial task",
                response="Initial response",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager1.add_run(session_id, run)
        finally:
            await manager1.close()

        # 第二个实例：加载并继续
        manager2 = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )
        try:
            session = await manager2.get_session(session_id, "test-agents")
            assert len(session.runs) == 1
            assert session.runs[0].task == "Initial task"

            # 添加新的运行记录
            run2 = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Continued task",
                response="Continued response",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager2.add_run(session_id, run2)
        finally:
            await manager2.close()

        # 第三个实例：验证所有数据
        manager3 = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )
        try:
            session = await manager3.get_session(session_id, "test-agents")
            assert len(session.runs) == 2
        finally:
            await manager3.close()


# ============================================================================
# Extended Integration Tests
# ============================================================================


class TestExtendedIntegration:
    """扩展集成测试 - 验证实际使用场景."""

    @pytest.mark.asyncio
    async def test_concurrent_sessions(self, temp_storage_path):
        """测试并发多会话场景."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            # 模拟多个用户同时使用
            async def user_session(user_id: str, num_rounds: int):
                session_id = f"user-{user_id}"
                for i in range(num_rounds):
                    await manager.get_session(session_id, "assistant", user_id)
                    run = AgentRunRecord(
                        run_id=str(uuid.uuid4()),
                        task=f"User {user_id} task {i}",
                        response=f"Response to user {user_id} task {i}",
                        success=True,
                        steps=1,
                        timestamp=time.time(),
                        metadata={"user_id": user_id, "round": i},
                    )
                    await manager.add_run(session_id, run)

            # 并发执行 5 个用户会话
            await asyncio.gather(
                user_session("alice", 3),
                user_session("bob", 3),
                user_session("charlie", 3),
                user_session("david", 3),
                user_session("eve", 3),
            )

            # 验证所有会话
            all_sessions = await manager.get_all_sessions()
            assert len(all_sessions) == 5

            for user in ["alice", "bob", "charlie", "david", "eve"]:
                session = all_sessions[f"user-{user}"]
                assert len(session.runs) == 3
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_team_workflow(self, temp_storage_path):
        """测试 Team 工作流场景."""
        manager = UnifiedTeamSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session_id = "team-workflow"
            team_name = "Research Team"

            # Leader 发起任务
            leader_run_id = str(uuid.uuid4())
            leader_run = RunRecord(
                run_id=leader_run_id,
                parent_run_id=None,
                runner_type="team_leader",
                runner_name=team_name,
                task="Research Python async programming",
                response="Delegating to team members...",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={"phase": "delegation"},
            )
            await manager.get_session(session_id, team_name)
            await manager.add_run(session_id, leader_run)

            # Member 1 执行子任务
            member1_run = RunRecord(
                run_id=str(uuid.uuid4()),
                parent_run_id=leader_run_id,
                runner_type="member",
                runner_name="Researcher",
                task="Find asyncio documentation",
                response="Found official Python docs on asyncio...",
                success=True,
                steps=2,
                timestamp=time.time(),
                metadata={"role": "researcher"},
            )
            await manager.add_run(session_id, member1_run)

            # Member 2 执行子任务
            member2_run = RunRecord(
                run_id=str(uuid.uuid4()),
                parent_run_id=leader_run_id,
                runner_type="member",
                runner_name="Writer",
                task="Summarize findings",
                response="Summary: asyncio provides infrastructure for...",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={"role": "writer"},
            )
            await manager.add_run(session_id, member2_run)

            # Leader 汇总结果
            leader_final = RunRecord(
                run_id=str(uuid.uuid4()),
                parent_run_id=None,
                runner_type="team_leader",
                runner_name=team_name,
                task="Compile final report",
                response="Final report on Python async programming...",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={"phase": "completion"},
            )
            await manager.add_run(session_id, leader_final)

            # 验证会话状态
            session = await manager.get_session(session_id, team_name)
            stats = session.get_runs_count()
            assert stats["total"] == 4
            assert stats["leader"] == 2
            assert stats["member"] == 2

            # 验证成员交互记录
            interactions = session.get_member_interactions(leader_run_id)
            assert "Researcher" in interactions
            assert "Writer" in interactions

            # 验证历史上下文只包含 leader runs
            context = session.get_history_context(num_runs=10)
            assert "Research Python async programming" in context
            assert "Compile final report" in context
            assert "Find asyncio documentation" not in context  # member task 不应出现
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_session_state_management(self, temp_storage_path):
        """测试会话状态管理."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session_id = "state-test"
            session = await manager.get_session(session_id, "assistant")

            # 设置自定义状态
            session.state["user_preferences"] = {"language": "zh", "theme": "dark"}
            session.state["context"] = {"topic": "Python", "level": "intermediate"}

            # 添加运行记录以触发保存
            run = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Test task",
                response="Test response",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run(session_id, run)

            # 重新加载并验证状态
            manager2 = UnifiedAgentSessionManager(
                backend="file",
                storage_path=temp_storage_path
            )
            try:
                session2 = await manager2.get_session(session_id, "assistant")
                assert session2.state["user_preferences"]["language"] == "zh"
                assert session2.state["context"]["topic"] == "Python"
            finally:
                await manager2.close()
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_history_context_truncation(self, temp_storage_path):
        """测试历史上下文截断."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session_id = "truncation-test"
            await manager.get_session(session_id, "assistant")

            # 添加一个长响应
            long_response = "A" * 1000  # 超过 500 字符限制
            run = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Generate long response",
                response=long_response,
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run(session_id, run)

            session = await manager.get_session(session_id, "assistant")
            context = session.get_history_context(num_runs=1, max_chars=500)

            # 验证超出 max_chars 限制时被截断
            assert "[truncated]" in context
            assert len(context) <= 550  # max_chars + 一些余量
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_max_chars_limit(self, temp_storage_path):
        """测试最大字符数限制."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session_id = "max-chars-test"
            await manager.get_session(session_id, "assistant")

            # 添加多轮对话
            for i in range(10):
                run = AgentRunRecord(
                    run_id=str(uuid.uuid4()),
                    task=f"Task {i}: " + "x" * 100,
                    response=f"Response {i}: " + "y" * 100,
                    success=True,
                    steps=1,
                    timestamp=time.time(),
                    metadata={},
                )
                await manager.add_run(session_id, run)

            session = await manager.get_session(session_id, "assistant")
            
            # 限制最大字符数
            context = session.get_history_context(num_runs=10, max_chars=500)
            assert len(context) <= 600  # 允许一些余量
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_error_recovery(self, temp_storage_path):
        """测试错误恢复场景."""
        manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=temp_storage_path
        )

        try:
            session_id = "error-test"
            await manager.get_session(session_id, "assistant")

            # 添加成功的运行
            run1 = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Successful task",
                response="Success!",
                success=True,
                steps=1,
                timestamp=time.time(),
                metadata={},
            )
            await manager.add_run(session_id, run1)

            # 添加失败的运行
            run2 = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Failed task",
                response="Error: Something went wrong",
                success=False,
                steps=3,
                timestamp=time.time(),
                metadata={"error": "timeout"},
            )
            await manager.add_run(session_id, run2)

            # 添加恢复后的运行
            run3 = AgentRunRecord(
                run_id=str(uuid.uuid4()),
                task="Retry task",
                response="Success after retry!",
                success=True,
                steps=2,
                timestamp=time.time(),
                metadata={"retry": True},
            )
            await manager.add_run(session_id, run3)

            session = await manager.get_session(session_id, "assistant")
            assert len(session.runs) == 3
            assert session.runs[0].success is True
            assert session.runs[1].success is False
            assert session.runs[2].success is True
        finally:
            await manager.close()


# ============================================================================
# Run Tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
