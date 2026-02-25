"""
统一的 Session Manager，支持多种存储后端。

使用方式:
    from omni_agent.core.session_manager import (
        UnifiedAgentSessionManager,
        UnifiedTeamSessionManager,
    )

    # 使用文件存储
    manager = UnifiedAgentSessionManager(backend="file", storage_path="~/.sessions.json")

    # 使用 Redis
    manager = UnifiedAgentSessionManager(
        backend="redis",
        redis_host="localhost",
        redis_port=6379
    )

    # 使用 PostgreSQL
    manager = UnifiedAgentSessionManager(
        backend="postgres",
        postgres_dsn="postgresql://user:pass@localhost/db"
    )
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from omni_agent.core.session import (
    AgentRunRecord,
    AgentSession,
    RunRecord,
    TeamSession,
)
from omni_agent.core.session_storage import (
    SessionStorage,
    FileStorage,
    RedisStorage,
    PostgresStorage,
    create_storage,
)


class UnifiedAgentSessionManager:
    """统一的 Agent Session 管理器，支持多种存储后端."""

    def __init__(
        self,
        backend: str = "file",
        # File backend options
        storage_path: Optional[str] = None,
        # Redis backend options
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        # PostgreSQL backend options
        postgres_dsn: Optional[str] = None,
        postgres_table: str = "agent_sessions",
        # Common options
        ttl_seconds: int = 7 * 86400,  # 7 days
    ):
        """初始化 Session 管理器.

        Args:
            backend: 存储后端类型 ("file", "redis", "postgres")
            storage_path: 文件存储路径 (file backend)
            redis_host: Redis 主机 (redis backend)
            redis_port: Redis 端口 (redis backend)
            redis_db: Redis 数据库 (redis backend)
            redis_password: Redis 密码 (redis backend)
            postgres_dsn: PostgreSQL 连接字符串 (postgres backend)
            postgres_table: PostgreSQL 表名 (postgres backend)
            ttl_seconds: 会话过期时间（秒）
        """
        self.backend_type = backend.lower()
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

        # 创建存储后端
        if self.backend_type == "file":
            if not storage_path:
                storage_path = "~/.omni-agent/agent_sessions.json"
            self._storage: SessionStorage = FileStorage(storage_path)
        elif self.backend_type == "redis":
            self._storage = RedisStorage(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password or None,
                prefix="agent_session:",
                ttl_seconds=ttl_seconds,
            )
        elif self.backend_type in ("postgres", "postgresql"):
            if not postgres_dsn:
                raise ValueError("postgres_dsn is required for PostgreSQL backend")
            self._storage = PostgresStorage(
                dsn=postgres_dsn,
                table_name=postgres_table,
                session_type="agents",
            )
        else:
            raise ValueError(f"Unknown backend: {backend}")

        # 内存缓存（用于快速访问）
        self._cache: Dict[str, AgentSession] = {}

    async def get_session(
        self,
        session_id: str,
        agent_name: str = "default",
        user_id: Optional[str] = None
    ) -> AgentSession:
        """获取或创建会话."""
        # 先检查缓存
        if session_id in self._cache:
            return self._cache[session_id]

        # 从存储后端加载
        data = await self._storage.get_session(session_id)
        if data:
            session = self._deserialize_agent_session(data)
        else:
            # 创建新会话
            session = AgentSession(
                session_id=session_id,
                agent_name=agent_name,
                user_id=user_id,
                runs=[],
                state={},
                created_at=time.time(),
                updated_at=time.time(),
            )

        self._cache[session_id] = session
        return session

    async def add_run(self, session_id: str, run: AgentRunRecord) -> None:
        """添加运行记录."""
        async with self._lock:
            if session_id not in self._cache:
                await self.get_session(session_id)

            session = self._cache[session_id]
            session.add_run(run)

            # 保存到存储后端
            await self._storage.save_session(
                session_id,
                self._serialize_agent_session(session)
            )

    async def delete_session(self, session_id: str) -> bool:
        """删除会话."""
        async with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
            return await self._storage.delete_session(session_id)

    async def cleanup_old_sessions(self, max_age_days: int = 7) -> int:
        """清理过期会话."""
        max_age_seconds = max_age_days * 86400
        cleaned = await self._storage.cleanup_expired(max_age_seconds)

        # 清理缓存中的过期会话
        cutoff_time = time.time() - max_age_seconds
        to_delete = [
            sid for sid, session in self._cache.items()
            if session.updated_at < cutoff_time
        ]
        for sid in to_delete:
            del self._cache[sid]

        return cleaned

    async def get_all_sessions(self) -> Dict[str, AgentSession]:
        """获取所有会话."""
        session_ids = await self._storage.list_sessions()
        sessions = {}
        for sid in session_ids:
            sessions[sid] = await self.get_session(sid)
        return sessions

    async def close(self) -> None:
        """关闭连接."""
        await self._storage.close()

    def _serialize_agent_session(self, session: AgentSession) -> Dict[str, Any]:
        """序列化会话."""
        return {
            "session_id": session.session_id,
            "agent_name": session.agent_name,
            "user_id": session.user_id,
            "runs": [
                {
                    "run_id": r.run_id,
                    "task": r.task,
                    "response": r.response,
                    "success": r.success,
                    "steps": r.steps,
                    "timestamp": r.timestamp,
                    "metadata": r.metadata,
                }
                for r in session.runs
            ],
            "state": session.state,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def _deserialize_agent_session(self, data: Dict[str, Any]) -> AgentSession:
        """反序列化会话."""
        runs = [
            AgentRunRecord(**run_data)
            for run_data in data.get("runs", [])
        ]
        return AgentSession(
            session_id=data["session_id"],
            agent_name=data.get("agent_name", "default"),
            user_id=data.get("user_id"),
            runs=runs,
            state=data.get("state", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


class UnifiedTeamSessionManager:
    """统一的 Team Session 管理器，支持多种存储后端."""

    def __init__(
        self,
        backend: str = "file",
        # File backend options
        storage_path: Optional[str] = None,
        # Redis backend options
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        # PostgreSQL backend options
        postgres_dsn: Optional[str] = None,
        postgres_table: str = "agent_sessions",
        # Common options
        ttl_seconds: int = 7 * 86400,  # 7 days
    ):
        """初始化 Session 管理器."""
        self.backend_type = backend.lower()
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

        # 创建存储后端
        if self.backend_type == "file":
            if not storage_path:
                storage_path = "~/.omni-agent/team_sessions.json"
            self._storage: SessionStorage = FileStorage(storage_path)
        elif self.backend_type == "redis":
            self._storage = RedisStorage(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password or None,
                prefix="team_session:",
                ttl_seconds=ttl_seconds,
            )
        elif self.backend_type in ("postgres", "postgresql"):
            if not postgres_dsn:
                raise ValueError("postgres_dsn is required for PostgreSQL backend")
            self._storage = PostgresStorage(
                dsn=postgres_dsn,
                table_name=postgres_table,
                session_type="team",
            )
        else:
            raise ValueError(f"Unknown backend: {backend}")

        # 内存缓存
        self._cache: Dict[str, TeamSession] = {}

    async def get_session(
        self,
        session_id: str,
        team_name: str,
        user_id: Optional[str] = None
    ) -> TeamSession:
        """获取或创建会话."""
        if session_id in self._cache:
            return self._cache[session_id]

        data = await self._storage.get_session(session_id)
        if data:
            session = self._deserialize_team_session(data)
        else:
            session = TeamSession(
                session_id=session_id,
                team_name=team_name,
                user_id=user_id,
                runs=[],
                state={},
                created_at=time.time(),
                updated_at=time.time(),
            )

        self._cache[session_id] = session
        return session

    async def add_run(self, session_id: str, run: RunRecord) -> None:
        """添加运行记录."""
        async with self._lock:
            if session_id not in self._cache:
                await self.get_session(session_id, "default")

            session = self._cache[session_id]
            session.add_run(run)

            await self._storage.save_session(
                session_id,
                self._serialize_team_session(session)
            )

    async def delete_session(self, session_id: str) -> bool:
        """删除会话."""
        async with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
            return await self._storage.delete_session(session_id)

    async def cleanup_old_sessions(self, max_age_days: int = 7) -> int:
        """清理过期会话."""
        max_age_seconds = max_age_days * 86400
        cleaned = await self._storage.cleanup_expired(max_age_seconds)

        cutoff_time = time.time() - max_age_seconds
        to_delete = [
            sid for sid, session in self._cache.items()
            if session.updated_at < cutoff_time
        ]
        for sid in to_delete:
            del self._cache[sid]

        return cleaned

    async def get_all_sessions(self) -> Dict[str, TeamSession]:
        """获取所有会话."""
        session_ids = await self._storage.list_sessions()
        sessions = {}
        for sid in session_ids:
            sessions[sid] = await self.get_session(sid, "default")
        return sessions

    async def close(self) -> None:
        """关闭连接."""
        await self._storage.close()

    def _serialize_team_session(self, session: TeamSession) -> Dict[str, Any]:
        """序列化会话."""
        return {
            "session_id": session.session_id,
            "team_name": session.team_name,
            "user_id": session.user_id,
            "runs": [
                {
                    "run_id": r.run_id,
                    "parent_run_id": r.parent_run_id,
                    "runner_type": r.runner_type,
                    "runner_name": r.runner_name,
                    "task": r.task,
                    "response": r.response,
                    "success": r.success,
                    "steps": r.steps,
                    "timestamp": r.timestamp,
                    "metadata": r.metadata,
                }
                for r in session.runs
            ],
            "state": session.state,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def _deserialize_team_session(self, data: Dict[str, Any]) -> TeamSession:
        """反序列化会话."""
        runs = [
            RunRecord(**run_data)
            for run_data in data.get("runs", [])
        ]
        return TeamSession(
            session_id=data["session_id"],
            team_name=data.get("team_name", "default"),
            user_id=data.get("user_id"),
            runs=runs,
            state=data.get("state", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
