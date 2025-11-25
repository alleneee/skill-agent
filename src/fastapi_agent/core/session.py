"""
会话管理系统

提供轻量级的会话记录和历史上下文管理。
支持:
- 单 Agent 会话 (AgentSession)
- 多 Agent Team 会话 (TeamSession)

参考 agno 的 TeamSession 实现。
"""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================================
# Agent Session (单 Agent 会话支持)
# ============================================================================


@dataclass
class AgentRunRecord:
    """单 Agent 运行记录.

    记录 Agent 的单次运行结果，用于历史上下文追踪。
    """

    run_id: str
    task: str  # 用户输入
    response: str  # Agent 响应
    success: bool
    steps: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class AgentSession:
    """单 Agent 会话.

    管理单个 Agent 的所有运行记录和状态。
    """

    session_id: str
    agent_name: str
    user_id: Optional[str]

    # 运行记录
    runs: List[AgentRunRecord]

    # 会话状态 (可用于存储自定义数据)
    state: Dict[str, Any]

    # 时间戳
    created_at: float
    updated_at: float

    def add_run(self, run: AgentRunRecord) -> None:
        """添加运行记录."""
        self.runs.append(run)
        self.updated_at = time.time()

    def get_history_messages(
        self,
        num_runs: Optional[int] = 3,
        max_response_chars: int = 800,
        smart_compress: bool = True,
    ) -> List[Dict[str, str]]:
        """获取历史消息，用于注入到 Agent messages 中.

        Args:
            num_runs: 返回最近 N 轮运行，None 表示全部
            max_response_chars: 每个响应的最大字符数（防止 token 爆炸）
            smart_compress: 是否智能压缩（截断长响应，保留关键信息）

        Returns:
            历史消息列表 [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]
        """
        if num_runs is not None:
            recent_runs = self.runs[-num_runs:] if self.runs else []
        else:
            recent_runs = self.runs

        messages = []
        for run in recent_runs:
            # 用户消息保持原样
            messages.append({"role": "user", "content": run.task})
            
            # 智能压缩助手响应
            response = run.response
            if smart_compress and len(response) > max_response_chars:
                # 保留开头和结尾，中间截断
                head_chars = int(max_response_chars * 0.7)
                tail_chars = int(max_response_chars * 0.2)
                response = (
                    response[:head_chars] +
                    f"\n\n[... 中间内容已省略，共 {len(run.response)} 字符 ...]\n\n" +
                    response[-tail_chars:]
                )
            
            messages.append({"role": "assistant", "content": response})

        return messages

    def get_history_context(
        self,
        num_runs: Optional[int] = 3,
        max_chars: Optional[int] = None,
        truncate_response: bool = True
    ) -> str:
        """获取历史上下文 (用于系统提示).

        Args:
            num_runs: 返回最近 N 轮运行，None 表示全部
            max_chars: 最大字符数限制，None 表示不限制
            truncate_response: 是否截断过长的响应（保留前200字符）

        Returns:
            格式化的历史上下文，使用 XML 标签包裹
        """
        if num_runs is not None:
            recent_runs = self.runs[-num_runs:] if self.runs else []
        else:
            recent_runs = self.runs

        if not recent_runs:
            return ""

        context_parts = ["<conversation_history>"]
        total_chars = len("<conversation_history>\n</conversation_history>")

        for i, run in enumerate(recent_runs, 1):
            task = run.task
            response = run.response

            # 截断过长响应
            if truncate_response and len(response) > 500:
                response = response[:500] + "... [truncated]"

            round_text = f"[Round {i}]\nUser: {task}\nAssistant: {response}\n"

            # 检查字符数限制
            if max_chars and total_chars + len(round_text) > max_chars:
                # 如果是第一轮也放不下，则截断
                if i == 1:
                    available = max_chars - total_chars - 50  # 留一些余量
                    if available > 100:
                        round_text = round_text[:available] + "... [truncated]"
                        context_parts.append(round_text)
                break

            context_parts.append(round_text)
            total_chars += len(round_text)

        context_parts.append("</conversation_history>")
        return "\n".join(context_parts)

    def get_runs_count(self) -> int:
        """获取运行次数."""
        return len(self.runs)


class AgentSessionManager:
    """单 Agent 会话管理器.

    管理所有单 Agent 会话的生命周期，支持内存存储和可选的文件持久化。
    线程安全，使用 asyncio.Lock 保护并发写操作。
    """

    def __init__(self, storage_path: Optional[str] = None):
        """初始化会话管理器.

        Args:
            storage_path: 可选的持久化存储路径，None 表示仅内存存储
        """
        self.sessions: Dict[str, AgentSession] = {}
        self.storage_path = storage_path
        self._lock = asyncio.Lock()  # 并发保护锁

        # 如果指定了存储路径，尝试加载已有会话
        if storage_path:
            self._load_from_storage()

    def get_session(
        self,
        session_id: str,
        agent_name: str = "default",
        user_id: Optional[str] = None
    ) -> AgentSession:
        """获取或创建会话.

        Args:
            session_id: 会话 ID
            agent_name: Agent 名称
            user_id: 可选的用户 ID

        Returns:
            AgentSession 实例
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = AgentSession(
                session_id=session_id,
                agent_name=agent_name,
                user_id=user_id,
                runs=[],
                state={},
                created_at=time.time(),
                updated_at=time.time(),
            )
        return self.sessions[session_id]

    def add_run(self, session_id: str, run: AgentRunRecord) -> None:
        """添加运行记录到会话（同步版本，向后兼容）.

        Args:
            session_id: 会话 ID
            run: 运行记录
        """
        if session_id in self.sessions:
            self.sessions[session_id].add_run(run)

            # 可选: 保存到文件
            if self.storage_path:
                self._save_to_storage()

    async def add_run_async(self, session_id: str, run: AgentRunRecord) -> None:
        """添加运行记录到会话（异步版本，带锁保护）.

        Args:
            session_id: 会话 ID
            run: 运行记录
        """
        async with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].add_run(run)

                # 可选: 保存到文件（使用原子写入）
                if self.storage_path:
                    self._save_to_storage_atomic()

    def get_all_sessions(self) -> Dict[str, AgentSession]:
        """获取所有会话."""
        return self.sessions

    def delete_session(self, session_id: str) -> bool:
        """删除会话."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            if self.storage_path:
                self._save_to_storage()
            return True
        return False

    async def delete_session_async(self, session_id: str) -> bool:
        """删除会话（异步版本，带锁保护）."""
        async with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                if self.storage_path:
                    self._save_to_storage_atomic()
                return True
            return False

    def _save_to_storage(self) -> None:
        """保存到文件（同步版本）."""
        if not self.storage_path:
            return

        data = {}
        for session_id, session in self.sessions.items():
            runs_data = [asdict(run) for run in session.runs]
            data[session_id] = {
                "session_id": session.session_id,
                "agent_name": session.agent_name,
                "user_id": session.user_id,
                "runs": runs_data,
                "state": session.state,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

        storage_file = Path(self.storage_path).expanduser()
        storage_file.parent.mkdir(parents=True, exist_ok=True)

        with storage_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_to_storage_atomic(self) -> None:
        """原子写入保存到文件（先写临时文件，再重命名）."""
        if not self.storage_path:
            return

        data = {}
        for session_id, session in self.sessions.items():
            runs_data = [asdict(run) for run in session.runs]
            data[session_id] = {
                "session_id": session.session_id,
                "agent_name": session.agent_name,
                "user_id": session.user_id,
                "runs": runs_data,
                "state": session.state,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

        storage_file = Path(self.storage_path).expanduser()
        storage_file.parent.mkdir(parents=True, exist_ok=True)

        # 原子写入：先写入临时文件，再重命名
        temp_file = storage_file.with_suffix(".tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(storage_file)  # 原子替换
        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _load_from_storage(self) -> None:
        """从文件加载."""
        if not self.storage_path:
            return

        storage_file = Path(self.storage_path).expanduser()
        if not storage_file.exists():
            return

        try:
            with storage_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            for session_id, session_data in data.items():
                runs = [
                    AgentRunRecord(**run_data)
                    for run_data in session_data["runs"]
                ]
                self.sessions[session_id] = AgentSession(
                    session_id=session_data["session_id"],
                    agent_name=session_data["agent_name"],
                    user_id=session_data.get("user_id"),
                    runs=runs,
                    state=session_data.get("state", {}),
                    created_at=session_data["created_at"],
                    updated_at=session_data["updated_at"],
                )
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Failed to load agent sessions from {self.storage_path}: {e}")
            self.sessions = {}

    def cleanup_old_sessions(self, max_age_days: int = 7) -> int:
        """清理过期会话.

        Args:
            max_age_days: 会话最大保留天数

        Returns:
            清理的会话数量
        """
        cutoff_time = time.time() - (max_age_days * 86400)  # 86400 seconds per day
        to_delete = [
            sid for sid, session in self.sessions.items()
            if session.updated_at < cutoff_time
        ]

        for sid in to_delete:
            del self.sessions[sid]

        if to_delete and self.storage_path:
            self._save_to_storage()

        return len(to_delete)

    def trim_session_runs(self, session_id: str, max_runs: int = 100) -> int:
        """裁剪会话运行记录，只保留最近的 N 条.

        Args:
            session_id: 会话 ID
            max_runs: 最大保留运行数

        Returns:
            删除的运行记录数量
        """
        if session_id not in self.sessions:
            return 0

        session = self.sessions[session_id]
        if len(session.runs) <= max_runs:
            return 0

        # 保留最近的 max_runs 条
        removed_count = len(session.runs) - max_runs
        session.runs = session.runs[-max_runs:]
        session.updated_at = time.time()

        if self.storage_path:
            self._save_to_storage()

        return removed_count

    def get_stats(self) -> Dict[str, Any]:
        """获取会话统计信息.

        Returns:
            统计信息字典
        """
        total_runs = sum(len(s.runs) for s in self.sessions.values())
        oldest_session = min(
            (s.created_at for s in self.sessions.values()),
            default=None
        )
        newest_session = max(
            (s.updated_at for s in self.sessions.values()),
            default=None
        )

        return {
            "total_sessions": len(self.sessions),
            "total_runs": total_runs,
            "oldest_session_age_days": (
                (time.time() - oldest_session) / 86400 if oldest_session else 0
            ),
            "newest_session_age_days": (
                (time.time() - newest_session) / 86400 if newest_session else 0
            ),
        }


# ============================================================================
# Team Session (多 Agent Team 会话支持)
# ============================================================================


@dataclass
class RunRecord:
    """单次运行记录.

    记录 Team leader 或 member 的单次运行结果,支持父子关系追踪。
    """

    run_id: str
    parent_run_id: Optional[str]  # 父 run ID (成员 run 才有)

    # 运行者信息
    runner_type: str  # "team_leader" 或 "member"
    runner_name: str  # Team/Member 名称

    # 任务和响应
    task: str
    response: str
    success: bool

    # 元数据
    steps: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class TeamSession:
    """Team 会话.

    管理单个会话的所有运行记录和状态。
    """

    session_id: str
    team_name: str
    user_id: Optional[str]

    # 运行记录
    runs: List[RunRecord]

    # 会话状态 (可用于存储自定义数据)
    state: Dict[str, Any]

    # 时间戳
    created_at: float
    updated_at: float

    def add_run(self, run: RunRecord) -> None:
        """添加运行记录."""
        self.runs.append(run)
        self.updated_at = time.time()

    def get_history_context(
        self,
        num_runs: Optional[int] = 3,
        max_chars: Optional[int] = None,
        truncate_response: bool = True
    ) -> str:
        """获取历史上下文 (仅 leader runs).

        Args:
            num_runs: 返回最近 N 轮运行,None 表示全部
            max_chars: 最大字符数限制，None 表示不限制
            truncate_response: 是否截断过长的响应（保留前500字符）

        Returns:
            格式化的历史上下文,使用 XML 标签包裹
        """
        # 筛选 leader runs
        leader_runs = [r for r in self.runs if r.runner_type == "team_leader"]

        # 获取最近 N 轮
        if num_runs is not None:
            recent_runs = leader_runs[-num_runs:] if leader_runs else []
        else:
            recent_runs = leader_runs

        if not recent_runs:
            return ""

        # 构建上下文
        context_parts = ["<team_history>"]
        total_chars = len("<team_history>\n</team_history>")

        for i, run in enumerate(recent_runs, 1):
            task = run.task
            response = run.response

            # 截断过长响应
            if truncate_response and len(response) > 500:
                response = response[:500] + "... [truncated]"

            round_text = f"[Round {i}]\nTask: {task}\nResponse: {response}\n"

            # 检查字符数限制
            if max_chars and total_chars + len(round_text) > max_chars:
                if i == 1:
                    available = max_chars - total_chars - 50
                    if available > 100:
                        round_text = round_text[:available] + "... [truncated]"
                        context_parts.append(round_text)
                break

            context_parts.append(round_text)
            total_chars += len(round_text)

        context_parts.append("</team_history>")
        return "\n".join(context_parts)

    def get_member_interactions(self, current_run_id: str) -> str:
        """获取当前运行的成员交互历史.

        Args:
            current_run_id: 当前 leader run ID

        Returns:
            格式化的成员交互记录
        """
        # 筛选当前 run 的子 runs
        member_runs = [
            r for r in self.runs
            if r.parent_run_id == current_run_id
        ]

        if not member_runs:
            return ""

        # 构建上下文
        context = "<member_interactions>\n"
        for run in member_runs:
            context += f"{run.runner_name}:\n"
            context += f"  Task: {run.task}\n"
            context += f"  Response: {run.response}\n\n"
        context += "</member_interactions>"

        return context

    def get_runs_count(self) -> Dict[str, int]:
        """获取运行统计.

        Returns:
            包含各类运行计数的字典
        """
        leader_count = sum(1 for r in self.runs if r.runner_type == "team_leader")
        member_count = sum(1 for r in self.runs if r.runner_type == "member")

        return {
            "total": len(self.runs),
            "leader": leader_count,
            "member": member_count,
        }


class TeamSessionManager:
    """Team 会话管理器.

    管理所有会话的生命周期,支持内存存储和可选的文件持久化。
    线程安全，使用 asyncio.Lock 保护并发写操作。
    """

    def __init__(self, storage_path: Optional[str] = None):
        """初始化会话管理器.

        Args:
            storage_path: 可选的持久化存储路径,None 表示仅内存存储
        """
        self.sessions: Dict[str, TeamSession] = {}
        self.storage_path = storage_path
        self._lock = asyncio.Lock()  # 并发保护锁

        # 如果指定了存储路径,尝试加载已有会话
        if storage_path:
            self._load_from_storage()

    def get_session(
        self,
        session_id: str,
        team_name: str,
        user_id: Optional[str] = None
    ) -> TeamSession:
        """获取或创建会话.

        Args:
            session_id: 会话 ID
            team_name: Team 名称
            user_id: 可选的用户 ID

        Returns:
            TeamSession 实例
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = TeamSession(
                session_id=session_id,
                team_name=team_name,
                user_id=user_id,
                runs=[],
                state={},
                created_at=time.time(),
                updated_at=time.time(),
            )
        return self.sessions[session_id]

    def add_run(
        self,
        session_id: str,
        run: RunRecord
    ) -> None:
        """添加运行记录到会话（同步版本，向后兼容）.

        Args:
            session_id: 会话 ID
            run: 运行记录
        """
        if session_id in self.sessions:
            self.sessions[session_id].add_run(run)

            # 可选: 保存到文件
            if self.storage_path:
                self._save_to_storage()

    async def add_run_async(
        self,
        session_id: str,
        run: RunRecord
    ) -> None:
        """添加运行记录到会话（异步版本，带锁保护）.

        Args:
            session_id: 会话 ID
            run: 运行记录
        """
        async with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].add_run(run)

                # 可选: 保存到文件（使用原子写入）
                if self.storage_path:
                    self._save_to_storage_atomic()

    def get_all_sessions(self) -> Dict[str, TeamSession]:
        """获取所有会话.

        Returns:
            会话字典 {session_id: TeamSession}
        """
        return self.sessions

    def delete_session(self, session_id: str) -> bool:
        """删除会话（同步版本）.

        Args:
            session_id: 会话 ID

        Returns:
            删除是否成功
        """
        if session_id in self.sessions:
            del self.sessions[session_id]

            # 更新存储
            if self.storage_path:
                self._save_to_storage()

            return True
        return False

    async def delete_session_async(self, session_id: str) -> bool:
        """删除会话（异步版本，带锁保护）.

        Args:
            session_id: 会话 ID

        Returns:
            删除是否成功
        """
        async with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]

                # 更新存储（使用原子写入）
                if self.storage_path:
                    self._save_to_storage_atomic()

                return True
            return False

    def clear_all_sessions(self) -> None:
        """清空所有会话."""
        self.sessions.clear()

        # 清空存储文件
        if self.storage_path:
            self._save_to_storage()

    def _save_to_storage(self) -> None:
        """保存到文件（同步版本）."""
        if not self.storage_path:
            return

        # 转换为可序列化的字典
        data = {}
        for session_id, session in self.sessions.items():
            # 转换 runs
            runs_data = [asdict(run) for run in session.runs]

            data[session_id] = {
                "session_id": session.session_id,
                "team_name": session.team_name,
                "user_id": session.user_id,
                "runs": runs_data,
                "state": session.state,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

        # 写入文件
        storage_file = Path(self.storage_path).expanduser()
        storage_file.parent.mkdir(parents=True, exist_ok=True)

        with storage_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_to_storage_atomic(self) -> None:
        """原子写入保存到文件（先写临时文件，再重命名）."""
        if not self.storage_path:
            return

        # 转换为可序列化的字典
        data = {}
        for session_id, session in self.sessions.items():
            runs_data = [asdict(run) for run in session.runs]
            data[session_id] = {
                "session_id": session.session_id,
                "team_name": session.team_name,
                "user_id": session.user_id,
                "runs": runs_data,
                "state": session.state,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

        storage_file = Path(self.storage_path).expanduser()
        storage_file.parent.mkdir(parents=True, exist_ok=True)

        # 原子写入：先写入临时文件，再重命名
        temp_file = storage_file.with_suffix(".tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(storage_file)  # 原子替换
        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _load_from_storage(self) -> None:
        """从文件加载."""
        if not self.storage_path:
            return

        storage_file = Path(self.storage_path).expanduser()

        if not storage_file.exists():
            return

        try:
            with storage_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # 重建会话对象
            for session_id, session_data in data.items():
                # 重建 RunRecord 对象
                runs = [
                    RunRecord(**run_data)
                    for run_data in session_data["runs"]
                ]

                self.sessions[session_id] = TeamSession(
                    session_id=session_data["session_id"],
                    team_name=session_data["team_name"],
                    user_id=session_data.get("user_id"),
                    runs=runs,
                    state=session_data.get("state", {}),
                    created_at=session_data["created_at"],
                    updated_at=session_data["updated_at"],
                )
        except (json.JSONDecodeError, KeyError) as e:
            # 如果文件损坏,记录错误但继续运行
            print(f"Warning: Failed to load sessions from {self.storage_path}: {e}")
            self.sessions = {}

    def cleanup_old_sessions(self, max_age_days: int = 7) -> int:
        """清理过期会话.

        Args:
            max_age_days: 会话最大保留天数

        Returns:
            清理的会话数量
        """
        cutoff_time = time.time() - (max_age_days * 86400)
        to_delete = [
            sid for sid, session in self.sessions.items()
            if session.updated_at < cutoff_time
        ]

        for sid in to_delete:
            del self.sessions[sid]

        if to_delete and self.storage_path:
            self._save_to_storage()

        return len(to_delete)

    def trim_session_runs(self, session_id: str, max_runs: int = 100) -> int:
        """裁剪会话运行记录，只保留最近的 N 条.

        Args:
            session_id: 会话 ID
            max_runs: 最大保留运行数

        Returns:
            删除的运行记录数量
        """
        if session_id not in self.sessions:
            return 0

        session = self.sessions[session_id]
        if len(session.runs) <= max_runs:
            return 0

        # 保留最近的 max_runs 条
        removed_count = len(session.runs) - max_runs
        session.runs = session.runs[-max_runs:]
        session.updated_at = time.time()

        if self.storage_path:
            self._save_to_storage()

        return removed_count

    def get_stats(self) -> Dict[str, Any]:
        """获取会话统计信息.

        Returns:
            统计信息字典
        """
        total_runs = sum(len(s.runs) for s in self.sessions.values())
        leader_runs = sum(
            sum(1 for r in s.runs if r.runner_type == "team_leader")
            for s in self.sessions.values()
        )
        member_runs = sum(
            sum(1 for r in s.runs if r.runner_type == "member")
            for s in self.sessions.values()
        )
        oldest_session = min(
            (s.created_at for s in self.sessions.values()),
            default=None
        )
        newest_session = max(
            (s.updated_at for s in self.sessions.values()),
            default=None
        )

        return {
            "total_sessions": len(self.sessions),
            "total_runs": total_runs,
            "leader_runs": leader_runs,
            "member_runs": member_runs,
            "oldest_session_age_days": (
                (time.time() - oldest_session) / 86400 if oldest_session else 0
            ),
            "newest_session_age_days": (
                (time.time() - newest_session) / 86400 if newest_session else 0
            ),
        }
