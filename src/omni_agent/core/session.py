"""会话数据类定义

提供会话记录的数据类:
- AgentRunRecord: 单 Agent 运行记录
- AgentSession: 单 Agent 会话
- RunRecord: Team 运行记录
- TeamSession: Team 会话

会话管理器实现在 session_manager.py 中
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ============================================================================
# Agent Session (单 Agent 会话支持)
# ============================================================================


@dataclass
class AgentRunRecord:
    """单 Agent 运行记录

    记录 Agent 的单次运行结果，用于历史上下文追踪
    """

    run_id: str
    task: str
    response: str
    success: bool
    steps: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class AgentSession:
    """单 Agent 会话

    管理单个 Agent 的所有运行记录和状态
    """

    session_id: str
    agent_name: str
    user_id: Optional[str]
    runs: List[AgentRunRecord]
    state: Dict[str, Any]
    created_at: float
    updated_at: float

    def add_run(self, run: AgentRunRecord) -> None:
        """添加运行记录"""
        self.runs.append(run)
        self.updated_at = time.time()

    def get_history_messages(
        self,
        num_runs: Optional[int] = 3,
        max_response_chars: int = 800,
        smart_compress: bool = True,
    ) -> List[Dict[str, str]]:
        """获取历史消息，用于注入到 Agent messages 中

        Args:
            num_runs: 返回最近 N 轮运行，None 表示全部
            max_response_chars: 每个响应的最大字符数
            smart_compress: 是否智能压缩

        Returns:
            历史消息列表
        """
        if num_runs is not None:
            recent_runs = self.runs[-num_runs:] if self.runs else []
        else:
            recent_runs = self.runs

        messages = []
        for run in recent_runs:
            messages.append({"role": "user", "content": run.task})

            response = run.response
            if smart_compress and len(response) > max_response_chars:
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
        """获取历史上下文 (用于系统提示)

        Args:
            num_runs: 返回最近 N 轮运行，None 表示全部
            max_chars: 最大字符数限制
            truncate_response: 是否截断过长的响应

        Returns:
            格式化的历史上下文
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

            round_text = f"[Round {i}]\nUser: {task}\nAssistant: {response}\n"

            if max_chars and total_chars + len(round_text) > max_chars:
                if i == 1:
                    available = max_chars - total_chars - 50
                    if available > 100:
                        round_text = round_text[:available] + "... [truncated]"
                        context_parts.append(round_text)
                break

            context_parts.append(round_text)
            total_chars += len(round_text)

        context_parts.append("</conversation_history>")
        return "\n".join(context_parts)

    def get_runs_count(self) -> int:
        """获取运行次数"""
        return len(self.runs)


# ============================================================================
# Team Session (多 Agent Team 会话支持)
# ============================================================================


@dataclass
class RunRecord:
    """Team 运行记录

    记录 Team leader 或 member 的单次运行结果，支持父子关系追踪
    """

    run_id: str
    parent_run_id: Optional[str]
    runner_type: str
    runner_name: str
    task: str
    response: str
    success: bool
    steps: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class TeamSession:
    """Team 会话

    管理单个 Team 的所有运行记录和状态
    """

    session_id: str
    team_name: str
    user_id: Optional[str]
    runs: List[RunRecord]
    state: Dict[str, Any]
    created_at: float
    updated_at: float

    def add_run(self, run: RunRecord) -> None:
        """添加运行记录"""
        self.runs.append(run)
        self.updated_at = time.time()

    def get_history_context(
        self,
        num_runs: Optional[int] = 3,
        max_chars: Optional[int] = None,
        truncate_response: bool = True
    ) -> str:
        """获取历史上下文 (仅 leader runs)

        Args:
            num_runs: 返回最近 N 轮运行，None 表示全部
            max_chars: 最大字符数限制
            truncate_response: 是否截断过长的响应

        Returns:
            格式化的历史上下文
        """
        leader_runs = [r for r in self.runs if r.runner_type == "team_leader"]

        if num_runs is not None:
            recent_runs = leader_runs[-num_runs:] if leader_runs else []
        else:
            recent_runs = leader_runs

        if not recent_runs:
            return ""

        context_parts = ["<team_history>"]
        total_chars = len("<team_history>\n</team_history>")

        for i, run in enumerate(recent_runs, 1):
            task = run.task
            response = run.response

            round_text = f"[Round {i}]\nTask: {task}\nResponse: {response}\n"

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
        """获取当前运行的成员交互历史

        Args:
            current_run_id: 当前 leader run ID

        Returns:
            格式化的成员交互记录
        """
        member_runs = [
            r for r in self.runs
            if r.parent_run_id == current_run_id
        ]

        if not member_runs:
            return ""

        context = "<member_interactions>\n"
        for run in member_runs:
            context += f"{run.runner_name}:\n"
            context += f"  Task: {run.task}\n"
            context += f"  Response: {run.response}\n\n"
        context += "</member_interactions>"

        return context

    def get_runs_count(self) -> Dict[str, int]:
        """获取运行统计

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
