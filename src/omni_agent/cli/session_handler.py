"""CLI 模式的会话处理。"""

import uuid
from datetime import datetime

from omni_agent.core.config import settings


class CLISessionHandler:
    """Handles session persistence for CLI mode."""

    def __init__(
        self,
        session_id: str | None = None,
        auto_save: bool = True,
    ):
        """Initialize session handler.

        Args:
            session_id: Existing session ID to resume, or None for new session
            auto_save: Whether to auto-save after each run
        """
        self.session_id = session_id or f"cli-{uuid.uuid4().hex[:8]}"
        self.auto_save = auto_save
        self._manager: UnifiedAgentSessionManager | None = None
        self._run_count = 0
        self._start_time = datetime.now()
        self._tool_calls_count = 0

    async def initialize(self) -> None:
        """Initialize session manager based on settings."""
        if not settings.ENABLE_SESSION:
            return

        try:
            from omni_agent.core.session_manager import UnifiedAgentSessionManager

            self._manager = UnifiedAgentSessionManager(
                backend=settings.SESSION_BACKEND,
                storage_path=settings.SESSION_STORAGE_PATH,
                redis_host=settings.SESSION_REDIS_HOST,
                redis_port=settings.SESSION_REDIS_PORT,
                redis_db=settings.SESSION_REDIS_DB,
                redis_password=settings.SESSION_REDIS_PASSWORD or None,
                postgres_dsn=settings.postgres_dsn
                if settings.SESSION_BACKEND == "postgres"
                else None,
                postgres_table=settings.SESSION_POSTGRES_TABLE,
                ttl_seconds=settings.SESSION_MAX_AGE_DAYS * 86400,
            )
        except Exception as e:
            print(f"Warning: Session manager initialization failed: {e}")
            self._manager = None

    async def save_run(
        self,
        task: str,
        response: str,
        success: bool,
        steps: int,
    ) -> None:
        """Save a run record to session.

        Args:
            task: Task description
            response: Agent response
            success: Whether run was successful
            steps: Number of steps taken
        """
        if not self._manager or not self.auto_save:
            return

        try:
            from omni_agent.core.session import AgentRunRecord

            self._run_count += 1
            run_record = AgentRunRecord(
                run_id=f"{self.session_id}-run-{self._run_count}",
                task=task,
                response=response,
                success=success,
                steps=steps,
                timestamp=datetime.now().timestamp(),
                metadata={"source": "cli"},
            )
            await self._manager.add_run(self.session_id, run_record)
        except Exception:
            pass  # Silently ignore session save errors

    async def get_history_context(self, num_runs: int = 3) -> list[dict]:
        """Get history messages for context injection.

        Args:
            num_runs: Number of recent runs to include

        Returns:
            List of history messages
        """
        if not self._manager:
            return []

        try:
            session = await self._manager.get_session(self.session_id, agent_name="cli")
            return session.get_history_messages(num_runs=num_runs)
        except Exception:
            return []

    def increment_tool_calls(self, count: int = 1) -> None:
        """Increment tool calls counter.

        Args:
            count: Number of calls to add
        """
        self._tool_calls_count += count

    @property
    def tool_calls_count(self) -> int:
        """Get total tool calls count."""
        return self._tool_calls_count

    @property
    def run_count(self) -> int:
        """Get total run count."""
        return self._run_count

    @property
    def start_time(self) -> datetime:
        """Get session start time."""
        return self._start_time

    @property
    def stats(self) -> dict:
        """Get session statistics."""
        duration = datetime.now() - self._start_time
        return {
            "session_id": self.session_id,
            "run_count": self._run_count,
            "tool_calls_count": self._tool_calls_count,
            "duration": str(duration).split(".")[0],
            "start_time": self._start_time.isoformat(),
        }

    async def close(self) -> None:
        """Close session manager connections."""
        if self._manager:
            try:
                # Session manager may have a close method
                if hasattr(self._manager, "close"):
                    await self._manager.close()
            except Exception:
                pass
