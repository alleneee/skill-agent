"""Run log storage backends for agent execution logs.

Supports:
- FileStorage: Local file storage (default)
- RedisStorage: Redis storage for cloud debugging
"""

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi_agent.core.config import settings


class RunLogStorage(ABC):
    @abstractmethod
    async def save_event(self, run_id: str, event: dict) -> None:
        pass

    @abstractmethod
    async def get_events(self, run_id: str) -> list[dict]:
        pass

    @abstractmethod
    async def list_runs(self, limit: int = 50) -> list[dict]:
        pass

    @abstractmethod
    async def get_run_summary(self, run_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def delete_run(self, run_id: str) -> bool:
        pass

    async def close(self) -> None:
        pass


class NullRunLogStorage(RunLogStorage):
    async def save_event(self, run_id: str, event: dict) -> None:
        pass

    async def get_events(self, run_id: str) -> list[dict]:
        return []

    async def list_runs(self, limit: int = 50) -> list[dict]:
        return []

    async def get_run_summary(self, run_id: str) -> Optional[dict]:
        return None

    async def delete_run(self, run_id: str) -> bool:
        return False


class FileRunLogStorage(RunLogStorage):
    def __init__(self, log_dir: str, retention_days: int = 30):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> int:
        if not self.log_dir.exists():
            return 0
        deleted = 0
        cutoff = time.time() - (self.retention_days * 86400)
        for f in self.log_dir.glob("*.jsonl"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except OSError:
                pass
        return deleted

    def _get_run_file(self, run_id: str) -> Path:
        return self.log_dir / f"{run_id}.jsonl"

    async def save_event(self, run_id: str, event: dict) -> None:
        event["run_id"] = run_id
        event["logged_at"] = datetime.now().isoformat()
        with open(self._get_run_file(run_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    async def get_events(self, run_id: str) -> list[dict]:
        run_file = self._get_run_file(run_id)
        if not run_file.exists():
            return []
        events = []
        with open(run_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    async def list_runs(self, limit: int = 50) -> list[dict]:
        runs = []
        files = sorted(
            self.log_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]

        for f in files:
            run_id = f.stem
            summary = await self.get_run_summary(run_id)
            if summary:
                runs.append(summary)
        return runs

    async def get_run_summary(self, run_id: str) -> Optional[dict]:
        events = await self.get_events(run_id)
        if not events:
            return None

        total_steps = sum(1 for e in events if e.get("type") == "STEP")
        total_tools = sum(1 for e in events if e.get("type") == "TOOL_EXECUTION")
        completion = next((e for e in events if e.get("type") == "COMPLETION"), None)

        first_event = events[0] if events else {}
        last_event = events[-1] if events else {}

        return {
            "run_id": run_id,
            "timestamp": first_event.get("logged_at", ""),
            "total_steps": total_steps,
            "total_tool_calls": total_tools,
            "total_events": len(events),
            "success": completion is not None,
            "final_token_count": last_event.get("data", {}).get("token_count", 0)
        }

    async def delete_run(self, run_id: str) -> bool:
        run_file = self._get_run_file(run_id)
        if run_file.exists():
            run_file.unlink()
            return True
        return False


class RedisRunLogStorage(RunLogStorage):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = "",
        prefix: str = "agent_run:",
        ttl: int = 86400 * 7
    ):
        self.prefix = prefix
        self.ttl = ttl
        self._redis = None
        self._host = host
        self._port = port
        self._db = db
        self._password = password

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password or None,
                decode_responses=True
            )
        return self._redis

    def _run_key(self, run_id: str) -> str:
        return f"{self.prefix}{run_id}"

    def _index_key(self) -> str:
        return f"{self.prefix}index"

    async def save_event(self, run_id: str, event: dict) -> None:
        r = await self._get_redis()
        event["run_id"] = run_id
        event["logged_at"] = datetime.now().isoformat()

        key = self._run_key(run_id)
        await r.rpush(key, json.dumps(event, ensure_ascii=False))
        await r.expire(key, self.ttl)

        await r.zadd(self._index_key(), {run_id: time.time()})

    async def get_events(self, run_id: str) -> list[dict]:
        r = await self._get_redis()
        key = self._run_key(run_id)
        raw_events = await r.lrange(key, 0, -1)
        return [json.loads(e) for e in raw_events]

    async def list_runs(self, limit: int = 50) -> list[dict]:
        r = await self._get_redis()
        run_ids = await r.zrevrange(self._index_key(), 0, limit - 1)
        runs = []
        for run_id in run_ids:
            summary = await self.get_run_summary(run_id)
            if summary:
                runs.append(summary)
        return runs

    async def get_run_summary(self, run_id: str) -> Optional[dict]:
        events = await self.get_events(run_id)
        if not events:
            return None

        total_steps = sum(1 for e in events if e.get("type") == "STEP")
        total_tools = sum(1 for e in events if e.get("type") == "TOOL_EXECUTION")
        completion = next((e for e in events if e.get("type") == "COMPLETION"), None)

        first_event = events[0] if events else {}
        last_event = events[-1] if events else {}

        return {
            "run_id": run_id,
            "timestamp": first_event.get("logged_at", ""),
            "total_steps": total_steps,
            "total_tool_calls": total_tools,
            "total_events": len(events),
            "success": completion is not None,
            "final_token_count": last_event.get("data", {}).get("token_count", 0)
        }

    async def delete_run(self, run_id: str) -> bool:
        r = await self._get_redis()
        key = self._run_key(run_id)
        deleted = await r.delete(key)
        await r.zrem(self._index_key(), run_id)
        return deleted > 0

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


def create_run_log_storage() -> RunLogStorage:
    if not settings.ENABLE_DEBUG_LOGGING:
        return NullRunLogStorage()

    backend = settings.RUN_LOG_BACKEND.lower()
    if backend == "redis":
        return RedisRunLogStorage(
            host=settings.SESSION_REDIS_HOST,
            port=settings.SESSION_REDIS_PORT,
            db=settings.SESSION_REDIS_DB,
            password=settings.SESSION_REDIS_PASSWORD,
            prefix=settings.RUN_LOG_REDIS_PREFIX,
            ttl=settings.RUN_LOG_REDIS_TTL
        )
    return FileRunLogStorage(
        log_dir=settings.RUN_LOG_DIR,
        retention_days=settings.RUN_LOG_RETENTION_DAYS
    )


_storage: Optional[RunLogStorage] = None


async def get_run_log_storage() -> RunLogStorage:
    global _storage
    if _storage is None:
        _storage = create_run_log_storage()
    return _storage


async def close_run_log_storage() -> None:
    global _storage
    if _storage:
        await _storage.close()
        _storage = None
