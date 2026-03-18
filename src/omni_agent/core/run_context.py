"""Agent 执行的运行上下文.

重要: 此模块仅供框架内部使用。用户不应手动创建 RunContext 实例。
请使用 team.run() 或 agents.run() 的 session_id 和 user_id 参数。

设计理念参见 docs/RUNCONTEXT_DESIGN.md

RunContext 用于在框架各层级之间传递上下文信息（如 Team 到 Member Agent），
避免使用全局变量或线程本地存储，参考 agno 的 RunContext 设计。
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class RunContext:
    """Context information for agents/team run.

    This class is used internally to pass context between different levels of
    the framework (e.g., from Team to member Agents). Users should not create
    instances manually.

    Similar to agno's RunContext, this provides explicit context passing instead
    of global variables or thread-local storage.

    Attributes:
        run_id: Unique identifier for this run (auto-generated)
        session_id: Session identifier for multi-turn conversations
        user_id: Optional user identifier
        metadata: Additional metadata for this run
        session_state: Session state data
        dependencies: Dependency injection data

    Note:
        Users should use session_id/user_id parameters in team.run() instead of
        manually creating RunContext. The framework creates it automatically.

    Example (Internal use only):
        >>> # ❌ Users should NOT do this:
        >>> run_context = RunContext(run_id=..., session_id=...)

        >>> # ✅ Users should do this instead:
        >>> response = await team.run(
        ...     message="task",
        ...     session_id="user-session-123",
        ...     user_id="user-456"
        ... )
    """

    run_id: str
    session_id: str
    user_id: str | None = None
    metadata: dict[str, Any] | None = None
    session_state: dict[str, Any] | None = None
    dependencies: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "session_state": self.session_state,
            "dependencies": self.dependencies,
        }
