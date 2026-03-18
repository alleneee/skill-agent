"""Markdown 格式记忆存储系统

目录结构:
    .agent_memories/{user_id}/
    ├── profile.md          # 用户画像 (跨会话持久)
    ├── habit.md            # 用户习惯 (跨会话持久)
    └── sessions/
        └── {session_id}/
            ├── context.md  # 当前会话上下文
            └── meta.json   # 轻量元数据
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_str() -> str:
    return datetime.now().strftime(TIME_FORMAT)


def parse_time(time_str: str) -> datetime:
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except (ValueError, TypeError):
        return datetime.now()


class Memory:
    """基于 Markdown 文件的记忆存储

    profile/habit 存储在用户级别（跨会话持久），
    context 存储在会话级别。
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        base_dir: str = "./.agent_memories",
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.base_dir = Path(base_dir).expanduser()
        self.user_dir = self.base_dir / user_id
        self.session_dir = self.user_dir / "sessions" / session_id
        self.profile_path = self.user_dir / "profile.md"
        self.habit_path = self.user_dir / "habit.md"
        self.context_path = self.session_dir / "context.md"
        self.meta_path = self.session_dir / "meta.json"

        self._ensure_dirs()
        self._maybe_migrate()

    def _ensure_dirs(self) -> None:
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.session_dir.mkdir(parents=True, exist_ok=True)

    # ── 文件读写 ──

    def read_profile(self) -> str:
        if not self.profile_path.exists():
            return ""
        return self.profile_path.read_text(encoding="utf-8")

    def read_habit(self) -> str:
        if not self.habit_path.exists():
            return ""
        return self.habit_path.read_text(encoding="utf-8")

    def read_context(self) -> str:
        if not self.context_path.exists():
            return ""
        return self.context_path.read_text(encoding="utf-8")

    def write_profile(self, content: str) -> None:
        self.profile_path.write_text(content, encoding="utf-8")

    def write_habit(self, content: str) -> None:
        self.habit_path.write_text(content, encoding="utf-8")

    def write_context(self, content: str) -> None:
        self.context_path.write_text(content, encoding="utf-8")

    def append_profile(self, text: str) -> None:
        current = self.read_profile()
        separator = "\n" if current and not current.endswith("\n") else ""
        self.profile_path.write_text(current + separator + text + "\n", encoding="utf-8")

    def append_habit(self, text: str) -> None:
        current = self.read_habit()
        separator = "\n" if current and not current.endswith("\n") else ""
        self.habit_path.write_text(current + separator + text + "\n", encoding="utf-8")

    def append_context(self, text: str) -> None:
        current = self.read_context()
        separator = "\n" if current and not current.endswith("\n") else ""
        self.context_path.write_text(current + separator + text + "\n", encoding="utf-8")

    # ── 元数据 ──

    def _load_meta(self) -> dict:
        if not self.meta_path.exists():
            return {
                "created_at": now_str(),
                "updated_at": now_str(),
                "round_count": 0,
            }
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            return {
                "created_at": now_str(),
                "updated_at": now_str(),
                "round_count": 0,
            }

    def _save_meta(self, meta: dict) -> None:
        meta["updated_at"] = now_str()
        self.meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def increment_round(self) -> int:
        meta = self._load_meta()
        meta["round_count"] = meta.get("round_count", 0) + 1
        self._save_meta(meta)
        return meta["round_count"]

    @property
    def round_count(self) -> int:
        return self._load_meta().get("round_count", 0)

    @property
    def meta(self) -> dict:
        return self._load_meta()

    # ── 上下文注入 ──

    def get_context_for_prompt(self) -> str:
        profile = self.read_profile().strip()
        habit = self.read_habit().strip()
        context = self.read_context().strip()

        if not any([profile, habit, context]):
            return ""

        lines = ["<user_memory>"]

        if profile:
            lines.append("用户画像:")
            for line in profile.splitlines():
                stripped = line.strip()
                if stripped:
                    lines.append(f"  {stripped}")

        if habit:
            lines.append("用户习惯:")
            for line in habit.splitlines():
                stripped = line.strip()
                if stripped:
                    lines.append(f"  {stripped}")

        if context:
            lines.append("会话上下文:")
            for line in context.splitlines():
                stripped = line.strip()
                if stripped:
                    lines.append(f"  {stripped}")

        lines.append("</user_memory>")
        return "\n".join(lines)

    # ── 生命周期 ──

    def exists(self) -> bool:
        return self.meta_path.exists() or self.context_path.exists()

    def init_memory(self, task: str = "") -> None:
        self._ensure_dirs()
        if task:
            self.write_context(f"# 当前任务\n\n{task}\n")
        self._save_meta(
            {
                "created_at": now_str(),
                "updated_at": now_str(),
                "round_count": 0,
            }
        )

    def delete(self) -> None:
        shutil.rmtree(self.session_dir, ignore_errors=True)

    def get_memory_paths(self) -> dict[str, str]:
        return {
            "profile": str(self.profile_path),
            "habit": str(self.habit_path),
            "context": str(self.context_path),
            "meta": str(self.meta_path),
        }

    # ── 旧 JSON 迁移 ──

    def _maybe_migrate(self) -> None:
        """检测旧 JSON 格式并自动迁移到 .md 文件"""
        old_session_dir = self.base_dir / self.user_id / self.session_id
        old_path = old_session_dir / "memory.json"

        if not old_path.exists():
            return

        try:
            data = json.loads(old_path.read_text(encoding="utf-8"))
            memories = data.get("memories", {})

            profile_items = memories.get("profile", [])
            if profile_items and not self.profile_path.exists():
                lines = []
                for item in profile_items:
                    content = item.get("content", "") or item.get("overview", "")
                    if content:
                        lines.append(f"- {content}")
                if lines:
                    self.write_profile("\n".join(lines) + "\n")

            habit_items = memories.get("habit", [])
            if habit_items and not self.habit_path.exists():
                lines = []
                for item in habit_items:
                    content = item.get("content", "") or item.get("overview", "")
                    if content:
                        lines.append(f"- {content}")
                if lines:
                    self.write_habit("\n".join(lines) + "\n")

            if not self.context_path.exists():
                context_parts = []
                ctx = data.get("context", {})
                task = ctx.get("task", "")
                if task:
                    context_parts.append(f"# 当前任务\n\n{task}\n")

                summary = data.get("summary", {})
                core_facts = summary.get("core_facts", [])
                if core_facts:
                    context_parts.append("# 核心事实\n")
                    for fact in core_facts:
                        context_parts.append(f"- {fact}")
                    context_parts.append("")

                task_items = memories.get("task", [])
                active_tasks = [
                    t for t in task_items if t.get("metadata", {}).get("status") != "completed"
                ]
                if active_tasks:
                    context_parts.append("# 活跃任务\n")
                    for t in active_tasks:
                        content = t.get("content", "")
                        if content:
                            context_parts.append(f"- {content}")
                    context_parts.append("")

                if context_parts:
                    self.write_context("\n".join(context_parts))

            meta = data.get("meta", {})
            session_mems = memories.get("session", [])
            round_count = len(session_mems) // 2
            self._save_meta(
                {
                    "created_at": meta.get("created_at", now_str()),
                    "updated_at": meta.get("updated_at", now_str()),
                    "round_count": round_count,
                }
            )

            old_path.rename(old_path.with_suffix(".json.bak"))

            old_detail = old_session_dir / "memory_detail.json"
            if old_detail.exists():
                old_detail.rename(old_detail.with_suffix(".json.bak"))

            logger.info(
                f"迁移旧 JSON 记忆到 Markdown: user={self.user_id}, session={self.session_id}"
            )

        except Exception as e:
            logger.warning(f"记忆迁移失败: {e}")


class MemoryManager:
    """记忆管理器，管理多个用户/会话的记忆"""

    def __init__(self, base_dir: str = "./.agent_memories"):
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_memory(self, user_id: str, session_id: str) -> Memory:
        return Memory(user_id, session_id, str(self.base_dir))

    def list_sessions(self, user_id: str) -> list[str]:
        sessions_dir = self.base_dir / user_id / "sessions"
        if not sessions_dir.exists():
            return []
        return [d.name for d in sessions_dir.iterdir() if d.is_dir()]

    def delete_session(self, user_id: str, session_id: str) -> bool:
        session_dir = self.base_dir / user_id / "sessions" / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        return False

    def list_users(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return [
            d.name for d in self.base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]

    def delete_user(self, user_id: str) -> bool:
        user_dir = self.base_dir / user_id
        if user_dir.exists():
            shutil.rmtree(user_dir)
            return True
        return False

    def cleanup_expired(self, max_age_days: int = 30) -> int:
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        for user_id in self.list_users():
            for session_id in self.list_sessions(user_id):
                memory = self.get_memory(user_id, session_id)
                meta = memory.meta
                updated = parse_time(meta.get("updated_at", ""))
                if updated < cutoff:
                    memory.delete()
                    removed += 1

        return removed

    def get_stats(self) -> dict:
        users = self.list_users()
        total_sessions = 0

        for user_id in users:
            sessions = self.list_sessions(user_id)
            total_sessions += len(sessions)

        return {
            "users": len(users),
            "sessions": total_sessions,
        }
