"""
Session 存储后端抽象层

支持多种存储方式:
- FileStorage: JSON 文件存储 (默认，开发环境)
- RedisStorage: Redis 存储 (生产环境，高并发)
- PostgresStorage: PostgreSQL 存储 (生产环境，需要持久化和查询)
"""

import json
import logging
import time

logger = logging.getLogger(__name__)
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

from omni_agent.core.session import (
    AgentSession,
    TeamSession,
)

T = TypeVar("T", AgentSession, TeamSession)


class SessionStorage(ABC):
    """Session 存储后端抽象基类."""

    @abstractmethod
    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """获取会话数据."""
        pass

    @abstractmethod
    async def save_session(self, session_id: str, data: dict[str, Any]) -> None:
        """保存会话数据."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除会话."""
        pass

    @abstractmethod
    async def list_sessions(self) -> list[str]:
        """列出所有会话 ID."""
        pass

    @abstractmethod
    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """清理过期会话."""
        pass

    async def close(self) -> None:
        """关闭连接（可选实现）."""
        pass


# ============================================================================
# File Storage (JSON 文件存储)
# ============================================================================


class FileStorage(SessionStorage):
    """JSON 文件存储后端.

    适用于开发环境和单机部署。
    """

    def __init__(self, storage_path: str):
        """初始化文件存储.

        Args:
            storage_path: JSON 文件路径
        """
        self.storage_path = Path(storage_path).expanduser()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载数据."""
        if self.storage_path.exists():
            try:
                with self.storage_path.open("r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load session storage from %s: %s", self.storage_path, e)
                self._data = {}

    def _save(self) -> None:
        """保存数据到文件（原子写入）."""
        temp_file = self.storage_path.with_suffix(".tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.storage_path)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._data.get(session_id)

    async def save_session(self, session_id: str, data: dict[str, Any]) -> None:
        self._data[session_id] = data
        self._save()

    async def delete_session(self, session_id: str) -> bool:
        if session_id in self._data:
            del self._data[session_id]
            self._save()
            return True
        return False

    async def list_sessions(self) -> list[str]:
        return list(self._data.keys())

    async def cleanup_expired(self, max_age_seconds: int) -> int:
        cutoff_time = time.time() - max_age_seconds
        to_delete = [
            sid for sid, data in self._data.items() if data.get("updated_at", 0) < cutoff_time
        ]
        for sid in to_delete:
            del self._data[sid]
        if to_delete:
            self._save()
        return len(to_delete)


# ============================================================================
# Redis Storage
# ============================================================================


class RedisStorage(SessionStorage):
    """Redis 存储后端.

    适用于生产环境，支持高并发和分布式部署。
    自动设置 TTL 过期时间。

    依赖: pip install redis
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        prefix: str = "session:",
        ttl_seconds: int = 7 * 86400,  # 默认 7 天
    ):
        """初始化 Redis 存储.

        Args:
            host: Redis 主机
            port: Redis 端口
            db: Redis 数据库编号
            password: Redis 密码
            prefix: Key 前缀
            ttl_seconds: 会话过期时间（秒）
        """
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError(
                "Redis support requires 'redis' package. Install with: pip install redis"
            )

        self.prefix = prefix
        self.ttl_seconds = ttl_seconds
        self._redis = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
        )

    def _key(self, session_id: str) -> str:
        """生成 Redis key."""
        return f"{self.prefix}{session_id}"

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        data = await self._redis.get(self._key(session_id))
        if data:
            return json.loads(data)
        return None

    async def save_session(self, session_id: str, data: dict[str, Any]) -> None:
        key = self._key(session_id)
        await self._redis.setex(key, self.ttl_seconds, json.dumps(data, ensure_ascii=False))

    async def delete_session(self, session_id: str) -> bool:
        result = await self._redis.delete(self._key(session_id))
        return result > 0

    async def list_sessions(self) -> list[str]:
        keys = await self._redis.keys(f"{self.prefix}*")
        return [k.replace(self.prefix, "") for k in keys]

    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """Redis 自动处理 TTL，这里手动清理过期数据."""
        # Redis 使用 TTL 自动过期，无需手动清理
        # 但可以检查并删除超过 max_age_seconds 的会话
        cutoff_time = time.time() - max_age_seconds
        cleaned = 0

        for session_id in await self.list_sessions():
            data = await self.get_session(session_id)
            if data and data.get("updated_at", 0) < cutoff_time:
                await self.delete_session(session_id)
                cleaned += 1

        return cleaned

    async def close(self) -> None:
        await self._redis.close()


# ============================================================================
# PostgreSQL Storage
# ============================================================================


class PostgresStorage(SessionStorage):
    """PostgreSQL 存储后端.

    适用于生产环境，需要持久化和复杂查询。

    依赖: pip install asyncpg

    需要的表结构:
    ```sql
    CREATE TABLE IF NOT EXISTS agent_sessions (
        session_id VARCHAR(255) PRIMARY KEY,
        session_type VARCHAR(50) NOT NULL DEFAULT 'agents',
        data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_sessions_updated_at ON agent_sessions(updated_at);
    CREATE INDEX idx_sessions_type ON agent_sessions(session_type);
    ```
    """

    def __init__(
        self,
        dsn: str,
        table_name: str = "agent_sessions",
        session_type: str = "agents",
    ):
        """初始化 PostgreSQL 存储.

        Args:
            dsn: PostgreSQL 连接字符串
            table_name: 表名
            session_type: 会话类型（用于区分 agents/team）
        """
        self.dsn = dsn
        self.table_name = table_name
        self.session_type = session_type
        self._pool = None

    async def _get_pool(self):
        """获取连接池."""
        if self._pool is None:
            try:
                import asyncpg
            except ImportError:
                raise ImportError(
                    "PostgreSQL support requires 'asyncpg' package. "
                    "Install with: pip install asyncpg"
                )
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)
            await self._ensure_table()
        return self._pool

    async def _ensure_table(self) -> None:
        """确保表存在."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    session_id VARCHAR(255) PRIMARY KEY,
                    session_type VARCHAR(50) NOT NULL DEFAULT 'agents',
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated_at
                ON {self.table_name}(updated_at)
            """)
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_type
                ON {self.table_name}(session_type)
            """)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT data FROM {self.table_name}
                WHERE session_id = $1 AND session_type = $2
                """,
                session_id,
                self.session_type,
            )
            if row:
                return json.loads(row["data"])
            return None

    async def save_session(self, session_id: str, data: dict[str, Any]) -> None:
        pool = await self._get_pool()
        json_data = json.dumps(data, ensure_ascii=False)
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self.table_name} (session_id, session_type, data, updated_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (session_id)
                DO UPDATE SET data = $3, updated_at = CURRENT_TIMESTAMP
                """,
                session_id,
                self.session_type,
                json_data,
            )

    async def delete_session(self, session_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE session_id = $1 AND session_type = $2
                """,
                session_id,
                self.session_type,
            )
            return "DELETE 1" in result

    async def list_sessions(self) -> list[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT session_id FROM {self.table_name}
                WHERE session_type = $1
                """,
                self.session_type,
            )
            return [row["session_id"] for row in rows]

    async def cleanup_expired(self, max_age_seconds: int) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE session_type = $1
                AND updated_at < CURRENT_TIMESTAMP - INTERVAL '{max_age_seconds} seconds'
                """,
                self.session_type,
            )
            # Parse "DELETE N" to get count
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


# ============================================================================
# Storage Factory
# ============================================================================


def create_storage(backend: str = "file", **kwargs) -> SessionStorage:
    """创建存储后端实例.

    Args:
        backend: 存储类型 ("file", "redis", "postgres")
        **kwargs: 后端特定参数

    Returns:
        SessionStorage 实例

    Examples:
        # 文件存储
        storage = create_storage("file", storage_path="~/.sessions.json")

        # Redis 存储
        storage = create_storage(
            "redis",
            host="localhost",
            port=6379,
            password="secret",
            ttl_seconds=86400
        )

        # PostgreSQL 存储
        storage = create_storage(
            "postgres",
            dsn="postgresql://user:pass@localhost/db",
            table_name="sessions"
        )
    """
    backends = {
        "file": FileStorage,
        "redis": RedisStorage,
        "postgres": PostgresStorage,
        "postgresql": PostgresStorage,
    }

    backend_lower = backend.lower()
    if backend_lower not in backends:
        raise ValueError(f"Unknown storage backend: {backend}. Available: {list(backends.keys())}")

    return backends[backend_lower](**kwargs)
