"""Run context for agent execution.

IMPORTANT: This module is for internal framework use. Users should not manually
create RunContext instances. Instead, use the session_id and user_id parameters
when calling team.run() or agent.run().

See docs/RUNCONTEXT_DESIGN.md for design rationale.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class RunContext:
    """Context information for agent/team run.

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
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    session_state: Optional[Dict[str, Any]] = None
    dependencies: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "session_state": self.session_state,
            "dependencies": self.dependencies,
        }
