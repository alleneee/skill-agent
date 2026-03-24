"""Self-improvement hook.

使用原生 Agent Hook 在工作区中维护 `.learnings/`，
避免依赖外部 shell hook 或宿主平台特性。

借鉴 OpenClaw ClawHub 社区 self-improving-agent / reflect-learn 的设计：
- 三文件结构 (LEARNINGS / ERRORS / FEATURE_REQUESTS)
- 重复模式检测 (Pattern-Key + Recurrence-Count)
- 条目生命周期 (pending / resolved / promoted / wont_fix)
- Area 标签 (frontend / backend / infra / tests / docs / config / runtime)
- 提升路径 (learning -> CLAUDE.md / AGENTS.md / 新 skill)
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from omni_agent.core.hooks import AgentHook, HookContext
from omni_agent.schemas.message import Message

REMINDER_SENTINEL = "<self_improvement_hook>"
REMINDER_MESSAGE = f"""{REMINDER_SENTINEL}
## Self-Improvement

当你遇到下面这些情况时，优先使用 `self-improvement` skill，并记录到 `.learnings/`：
- 用户纠正了你（correction）
- 工具或命令出现了非预期失败（error）
- 用户提出当前系统缺失的能力（feature_request）
- 你发现了值得复用的项目内模式（best_practice）
- 你的知识已过时或不正确（knowledge_gap）

只记录高价值信息，跳过明显、一次性、无需复盘的噪音。
记录前先搜索已有条目，避免重复；如果已有类似条目，用 See Also 关联并考虑提升优先级。
"""

FILE_HEADERS: dict[str, str] = {
    "LEARNINGS.md": "# Learnings\n\n记录用户纠正、知识缺口和可复用最佳实践。\n\n",
    "ERRORS.md": "# Errors\n\n记录需要复盘的工具失败、运行失败和环境问题。\n\n",
    "FEATURE_REQUESTS.md": "# Feature Requests\n\n记录用户请求但当前系统尚未支持的能力。\n\n",
}

AREA_TAGS = {"frontend", "backend", "infra", "tests", "docs", "config", "runtime"}

_FEATURE_REQUEST_PATTERNS = [
    re.compile(r"(?:能不能|可不可以|能否|有没有办法|是否可以|怎么才能)"),
    re.compile(r"(?:can you|could you|is there a way|i wish|why can't)", re.IGNORECASE),
]

MAX_DEDUPE_ERROR_LEN = 200


def _truncate_for_dedupe(text: str, max_len: int = MAX_DEDUPE_ERROR_LEN) -> str:
    if len(text) <= max_len:
        return text
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class SelfImprovementHook(AgentHook):
    """在 Agent 生命周期中沉淀可复用经验。

    功能：
    1. 运行前注入 reminder，提示模型在需要时加载 skill。
    2. 自动记录工具失败和运行失败到 ERRORS.md。
    3. 用户反馈（reject/edit）记录到 LEARNINGS.md。
    4. 检测用户 feature request 意图并记录到 FEATURE_REQUESTS.md。
    5. 重复模式检测：对同一工具的反复失败进行 Pattern-Key 追踪。
    """

    priority: int = 60

    def __init__(self, workspace_dir: str, skill_name: str = "self-improvement") -> None:
        self._workspace_dir = Path(workspace_dir)
        self._skill_name = skill_name
        self._learnings_dir = self._workspace_dir / ".learnings"
        self._message_cursor = 0
        self._logged_keys: set[str] = set()
        self._error_pattern_counts: dict[str, int] = {}

    async def before_run(self, ctx: HookContext) -> None:
        self._ensure_learning_files()
        self._inject_reminder(ctx)
        self._message_cursor = len(ctx.state.messages)
        self._logged_keys.clear()
        self._error_pattern_counts.clear()

    async def on_step(self, ctx: HookContext, step_data: dict[str, object]) -> None:
        new_messages = ctx.state.messages[self._message_cursor :]
        self._message_cursor = min(
            len(ctx.state.messages), self._message_cursor + len(new_messages)
        )

        for msg in new_messages:
            if msg.role != "tool" or not isinstance(msg.content, str):
                continue
            if not msg.content.startswith("Error:"):
                continue
            if msg.name == "get_user_input":
                continue

            error_text = msg.content.removeprefix("Error:").strip()
            tool_name = msg.name or "unknown_tool"
            summary = f"工具 `{tool_name}` 执行失败"

            pattern_key = f"tool_error.{tool_name}"
            self._error_pattern_counts[pattern_key] = (
                self._error_pattern_counts.get(pattern_key, 0) + 1
            )
            recurrence = self._error_pattern_counts[pattern_key]

            priority = "high" if recurrence >= 3 else "medium"

            dedupe_key = f"tool:{tool_name}:{msg.tool_call_id}:{_truncate_for_dedupe(error_text)}"
            self._append_error_entry(
                dedupe_key=dedupe_key,
                summary=summary,
                error_text=error_text,
                ctx=ctx,
                priority=priority,
                context_lines=[
                    f"- Step: {ctx.step}",
                    f"- Tool: `{tool_name}`",
                    f"- Tool Call ID: `{msg.tool_call_id or 'unknown'}`",
                ],
                pattern_key=pattern_key,
                recurrence_count=recurrence,
            )

        if step_data.get("error"):
            error_text = str(step_data["error"]).strip()
            self._append_error_entry(
                dedupe_key=f"step:{ctx.step}:{_truncate_for_dedupe(error_text)}",
                summary="Agent 单步执行失败",
                error_text=error_text,
                ctx=ctx,
                context_lines=[
                    f"- Step: {ctx.step}",
                    "- Source: step execution",
                ],
            )

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        if success or result in {"Waiting for user input", "Task cancelled by user"}:
            return

        error_text = result.strip()
        self._append_error_entry(
            dedupe_key=f"run:{_truncate_for_dedupe(error_text)}",
            summary="Agent 运行未正常完成",
            error_text=error_text,
            ctx=ctx,
            context_lines=[
                f"- Final Step: {ctx.step}",
                "- Source: run completion",
            ],
        )

    async def on_feedback(
        self, ctx: HookContext, feedback_type: str, data: dict[str, object]
    ) -> None:
        if feedback_type == "feature_request":
            capability = str(data.get("capability") or data.get("message") or "").strip()
            if capability:
                self.record_feature_request(capability=capability, ctx=ctx)
            return

        if feedback_type not in {"reject", "edit"}:
            return

        reason = str(data.get("reason") or data.get("message") or "收到用户纠正").strip()
        dedupe_key = f"feedback:{feedback_type}:{reason}"
        if dedupe_key in self._logged_keys:
            return
        self._logged_keys.add(dedupe_key)

        task = self._extract_latest_user_message(ctx)
        self.record_correction(feedback_type=feedback_type, reason=reason, task=task)

    def record_correction(
        self,
        feedback_type: str,
        reason: str,
        task: str = "N/A",
        area: str = "runtime",
    ) -> None:
        self._ensure_learning_files()
        entry_id = self._build_entry_id("LRN")
        timestamp = self._now()
        body = (
            f"## [{entry_id}] correction\n\n"
            f"**Logged**: {timestamp}\n"
            f"**Priority**: medium\n"
            f"**Status**: pending\n"
            f"**Area**: {area}\n\n"
            "### Summary\n"
            f"收到用户反馈：{reason}\n\n"
            "### Details\n"
            f"- Feedback Type: `{feedback_type}`\n"
            f"- Task: {task}\n\n"
            "### Suggested Action\n"
            "复盘导致纠正的假设，并在相近任务里优先检查同类问题。\n\n"
            "### Metadata\n"
            "- Source: user_feedback\n"
            "- Related Files: N/A\n\n"
            "---\n\n"
        )
        self._append(self._learnings_dir / "LEARNINGS.md", body)

    def record_feature_request(
        self,
        capability: str,
        ctx: HookContext | None = None,
        area: str = "runtime",
        complexity: str = "medium",
    ) -> None:
        self._ensure_learning_files()

        dedupe_key = f"feat:{capability[:100]}"
        if dedupe_key in self._logged_keys:
            return
        self._logged_keys.add(dedupe_key)

        entry_id = self._build_entry_id("FEAT")
        timestamp = self._now()
        task = self._extract_latest_user_message(ctx) if ctx else "N/A"
        body = (
            f"## [{entry_id}] {capability[:80]}\n\n"
            f"**Logged**: {timestamp}\n"
            f"**Priority**: medium\n"
            f"**Status**: pending\n"
            f"**Area**: {area}\n\n"
            "### Requested Capability\n"
            f"{capability}\n\n"
            "### User Context\n"
            f"{task}\n\n"
            "### Complexity Estimate\n"
            f"{complexity}\n\n"
            "### Suggested Implementation\n"
            "待分析\n\n"
            "### Metadata\n"
            "- Frequency: first_time\n"
            "- Related Features: N/A\n\n"
            "---\n\n"
        )
        self._append(self._learnings_dir / "FEATURE_REQUESTS.md", body)

    def record_learning(
        self,
        category: str,
        summary: str,
        details: str,
        suggested_action: str = "",
        area: str = "runtime",
        priority: str = "medium",
        source: str = "conversation",
        related_files: str = "N/A",
        pattern_key: str = "",
    ) -> None:
        self._ensure_learning_files()
        entry_id = self._build_entry_id("LRN")
        timestamp = self._now()

        metadata_lines = [
            f"- Source: {source}",
            f"- Related Files: {related_files}",
        ]
        if pattern_key:
            metadata_lines.append(f"- Pattern-Key: {pattern_key}")

        body = (
            f"## [{entry_id}] {category}\n\n"
            f"**Logged**: {timestamp}\n"
            f"**Priority**: {priority}\n"
            f"**Status**: pending\n"
            f"**Area**: {area}\n\n"
            "### Summary\n"
            f"{summary}\n\n"
            "### Details\n"
            f"{details}\n\n"
            "### Suggested Action\n"
            f"{suggested_action or '待分析'}\n\n"
            "### Metadata\n" + "\n".join(metadata_lines) + "\n\n---\n\n"
        )
        self._append(self._learnings_dir / "LEARNINGS.md", body)

    def _ensure_learning_files(self) -> None:
        self._learnings_dir.mkdir(parents=True, exist_ok=True)
        for filename, header in FILE_HEADERS.items():
            file_path = self._learnings_dir / filename
            if not file_path.exists():
                file_path.write_text(header, encoding="utf-8")

    def _inject_reminder(self, ctx: HookContext) -> None:
        for msg in ctx.state.messages:
            if isinstance(msg.content, str) and REMINDER_SENTINEL in msg.content:
                return

        reminder = Message(
            role="system",
            content=REMINDER_MESSAGE.replace("`self-improvement`", f"`{self._skill_name}`"),
        )

        insert_at = 0
        while (
            insert_at < len(ctx.state.messages) and ctx.state.messages[insert_at].role == "system"
        ):
            insert_at += 1
        ctx.state.messages.insert(insert_at, reminder)

    def _append_error_entry(
        self,
        dedupe_key: str,
        summary: str,
        error_text: str,
        ctx: HookContext,
        context_lines: list[str],
        priority: str = "medium",
        pattern_key: str = "",
        recurrence_count: int = 0,
    ) -> None:
        if dedupe_key in self._logged_keys:
            return
        self._logged_keys.add(dedupe_key)

        entry_id = self._build_entry_id("ERR")
        timestamp = self._now()
        task = self._extract_latest_user_message(ctx)

        metadata_lines = [
            "- Reproducible: unknown",
            "- Related Files: N/A",
        ]
        if pattern_key:
            metadata_lines.append(f"- Pattern-Key: {pattern_key}")
            metadata_lines.append(f"- Recurrence-Count: {recurrence_count}")

        body = (
            f"## [{entry_id}] auto_logged_error\n\n"
            f"**Logged**: {timestamp}\n"
            f"**Priority**: {priority}\n"
            f"**Status**: pending\n"
            f"**Area**: runtime\n\n"
            "### Summary\n"
            f"{summary}\n\n"
            "### Error\n"
            "```text\n"
            f"{error_text}\n"
            "```\n\n"
            "### Context\n" + "\n".join(context_lines) + f"\n- Task: {task}\n\n"
            "### Suggested Fix\n"
            "判断这次失败是否属于可复用模式；若是，补充到 skill 或项目约束中。\n\n"
            "### Metadata\n" + "\n".join(metadata_lines) + "\n\n---\n\n"
        )
        self._append(self._learnings_dir / "ERRORS.md", body)

    def _append(self, file_path: Path, content: str) -> None:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content)

    def _build_entry_id(self, prefix: str) -> str:
        return f"{prefix}-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:6].upper()}"

    def _extract_latest_user_message(self, ctx: HookContext) -> str:
        for msg in reversed(ctx.state.messages):
            if msg.role == "user" and isinstance(msg.content, str) and msg.content.strip():
                return msg.content.strip()[:200]
        return "N/A"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def is_feature_request(text: str) -> bool:
        return any(p.search(text) for p in _FEATURE_REQUEST_PATTERNS)


def create_self_improvement_hook(workspace_dir: str) -> SelfImprovementHook:
    return SelfImprovementHook(workspace_dir=workspace_dir)
