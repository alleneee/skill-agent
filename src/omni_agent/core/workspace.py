"""工作区管理模块.

为每个会话/请求自动创建隔离的子目录，支持：
- 会话级工作目录隔离
- 过期目录自动清理
- 会话列表查询

目录结构:
    workspace/
    ├── session_abc123/  # 会话 1 的工作目录
    ├── session_def456/  # 会话 2 的工作目录
    └── run_xxx/         # 临时运行目录
"""

import shutil
import time
from pathlib import Path
from uuid import uuid4


class WorkspaceManager:
    """工作区目录管理器，提供会话隔离."""

    def __init__(self, base_dir: str = "./workspace"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_session_workspace(self, session_id: str | None = None) -> Path:
        """Get or create a workspace directory for a session.

        Args:
            session_id: Session identifier. If None, generates a new UUID.

        Returns:
            Path to the session's workspace directory
        """
        if session_id is None:
            session_id = f"run_{uuid4().hex[:12]}"

        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def cleanup_session(self, session_id: str) -> bool:
        """Remove a session's workspace directory.

        Args:
            session_id: Session identifier

        Returns:
            True if cleaned up successfully
        """
        session_dir = self.base_dir / session_id
        if session_dir.exists() and session_dir.is_dir():
            shutil.rmtree(session_dir)
            return True
        return False

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        """Clean up expired session workspaces.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of directories cleaned up
        """
        cutoff_time = time.time() - (max_age_hours * 3600)
        cleaned = 0

        for session_dir in self.base_dir.iterdir():
            if session_dir.is_dir() and not session_dir.name.startswith("_"):
                try:
                    mtime = session_dir.stat().st_mtime
                    if mtime < cutoff_time:
                        shutil.rmtree(session_dir)
                        cleaned += 1
                except (OSError, PermissionError):
                    continue

        return cleaned

    def list_sessions(self) -> list[str]:
        """List all session workspace directories.

        Returns:
            List of session IDs
        """
        return [
            d.name for d in self.base_dir.iterdir() if d.is_dir() and not d.name.startswith("_")
        ]


_workspace_manager: WorkspaceManager | None = None


def get_workspace_manager(base_dir: str = "./workspace") -> WorkspaceManager:
    """Get or create a global workspace manager instance."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager(base_dir)
    return _workspace_manager
