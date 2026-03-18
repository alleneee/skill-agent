"""Ralph 执行模式实现.

Ralph Loop 是一种迭代开发方法论，通过重复执行相同的 prompt，
让 AI 看到自己之前在文件中的工作并逐步改进，直到任务完成。

核心组件:
    - RalphConfig: Ralph 模式配置
    - ToolResultCache: 工具结果缓存（摘要 + 原始数据）
    - WorkingMemory: 结构化工作记忆
    - ContextManager: 上下文管理协调器
    - CompletionDetector: 完成检测器
"""

import json
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class ContextStrategy(Enum):
    """上下文管理策略."""

    ITERATION_BOUNDARY = "iteration_boundary"  # 迭代边界概括
    TOKEN_THRESHOLD = "token_threshold"  # Token 阈值触发
    TOOL_LEVEL_CACHE = "tool_level_cache"  # 工具级别缓存
    ALL = "all"  # 全部策略组合


class CompletionCondition(Enum):
    """完成检测条件."""

    PROMISE_TAG = "promise_tag"  # Promise 标签检测
    MAX_ITERATIONS = "max_iterations"  # 最大迭代次数
    IDLE_THRESHOLD = "idle_threshold"  # 空闲阈值（无文件修改）


@dataclass
class RalphConfig:
    """Ralph 模式配置.

    Attributes:
        enabled: 是否启用（通过 ralph=True 自动设置）
        max_iterations: 最大迭代次数
        completion_promise: 完成标记文本
        idle_threshold: 连续无文件修改的迭代次数阈值
        context_strategy: 上下文管理策略
        completion_conditions: 启用的完成检测条件
        memory_dir: 工作记忆存储目录
        summarize_token_threshold: 触发摘要的 token 阈值
    """

    enabled: bool = False
    max_iterations: int = 20
    completion_promise: str = "TASK COMPLETE"
    idle_threshold: int = 3
    context_strategy: ContextStrategy = ContextStrategy.ALL
    completion_conditions: list[CompletionCondition] = field(
        default_factory=lambda: [
            CompletionCondition.PROMISE_TAG,
            CompletionCondition.MAX_ITERATIONS,
            CompletionCondition.IDLE_THRESHOLD,
        ]
    )
    memory_dir: str = ".ralph"
    summarize_token_threshold: int = 50000

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_iterations": self.max_iterations,
            "completion_promise": self.completion_promise,
            "idle_threshold": self.idle_threshold,
            "context_strategy": self.context_strategy.value,
            "completion_conditions": [c.value for c in self.completion_conditions],
            "memory_dir": self.memory_dir,
            "summarize_token_threshold": self.summarize_token_threshold,
        }


@dataclass
class CachedToolResult:
    """缓存的工具执行结果.

    同时保存完整内容和摘要，支持按需获取。
    """

    tool_call_id: str  # 工具调用 ID
    tool_name: str  # 工具名称
    arguments: dict[str, Any]  # 调用参数
    full_content: str  # 完整结果内容
    summary: str  # 摘要内容
    timestamp: float = field(default_factory=time.time)  # 执行时间戳
    iteration: int = 0  # 所属迭代

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "iteration": self.iteration,
        }


class ToolResultCache:
    """工具结果缓存.

    使用 LRU 策略管理缓存，同时存储摘要和完整内容。
    Agent 默认看到摘要，需要时可通过 get_cached_result 工具获取完整内容。
    """

    def __init__(self, max_cache_size: int = 100) -> None:
        self._cache: dict[str, CachedToolResult] = {}
        self._max_size = max_cache_size
        self._access_order: list[str] = []  # LRU 访问顺序

    def store(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        full_content: str,
        summary: str,
        iteration: int = 0,
    ) -> None:
        if (
            len(self._cache) >= self._max_size
            and tool_call_id not in self._cache
            and self._access_order
        ):
            oldest_id = self._access_order.pop(0)
            self._cache.pop(oldest_id, None)

        self._cache[tool_call_id] = CachedToolResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            full_content=full_content,
            summary=summary,
            iteration=iteration,
        )

        if tool_call_id in self._access_order:
            self._access_order.remove(tool_call_id)
        self._access_order.append(tool_call_id)

    def get_summary(self, tool_call_id: str) -> str | None:
        result = self._cache.get(tool_call_id)
        return result.summary if result else None

    def get_full_content(self, tool_call_id: str) -> str | None:
        result = self._cache.get(tool_call_id)
        if result and tool_call_id in self._access_order:
            self._access_order.remove(tool_call_id)
            self._access_order.append(tool_call_id)
        return result.full_content if result else None

    def get_by_tool_name(self, tool_name: str) -> list[CachedToolResult]:
        return [r for r in self._cache.values() if r.tool_name == tool_name]

    def get_iteration_results(self, iteration: int) -> list[CachedToolResult]:
        return [r for r in self._cache.values() if r.iteration == iteration]

    def clear(self) -> None:
        self._cache.clear()
        self._access_order.clear()

    def to_summaries_dict(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in self._cache.items()}


@dataclass
class MemoryEntry:
    """工作记忆条目."""

    key: str  # 条目键
    value: Any  # 条目值
    category: str  # 分类
    iteration: int  # 创建时的迭代
    timestamp: float = field(default_factory=time.time)  # 时间戳


class WorkingMemory:
    """结构化工作记忆.

    持久化到 workspace/.ralph/memory.json，跨迭代保留上下文。
    支持进度记录、发现、待办、决策、错误等分类。
    """

    CATEGORY_PROGRESS = "progress"  # 进度记录
    CATEGORY_FINDINGS = "findings"  # 发现/洞察
    CATEGORY_TODO = "todo"  # 待办事项
    CATEGORY_DECISIONS = "decisions"  # 决策记录
    CATEGORY_ERRORS = "errors"  # 错误记录

    def __init__(self, workspace_dir: Path, memory_dir: str = ".ralph") -> None:
        self._workspace = workspace_dir
        self._memory_path = workspace_dir / memory_dir
        self._memory_file = self._memory_path / "memory.json"
        self._entries: dict[str, MemoryEntry] = {}
        self._current_iteration = 0
        self._files_modified: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self._memory_file.exists():
            try:
                data = json.loads(self._memory_file.read_text(encoding="utf-8"))
                self._current_iteration = data.get("current_iteration", 0)
                self._files_modified = set(data.get("files_modified", []))
                for key, entry_data in data.get("entries", {}).items():
                    self._entries[key] = MemoryEntry(
                        key=entry_data["key"],
                        value=entry_data["value"],
                        category=entry_data["category"],
                        iteration=entry_data["iteration"],
                        timestamp=entry_data.get("timestamp", time.time()),
                    )
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        self._memory_path.mkdir(parents=True, exist_ok=True)
        data = {
            "current_iteration": self._current_iteration,
            "files_modified": list(self._files_modified),
            "entries": {
                k: {
                    "key": v.key,
                    "value": v.value,
                    "category": v.category,
                    "iteration": v.iteration,
                    "timestamp": v.timestamp,
                }
                for k, v in self._entries.items()
            },
        }
        self._memory_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def set_entry(self, key: str, value: Any, category: str = "general") -> None:
        self._entries[key] = MemoryEntry(
            key=key,
            value=value,
            category=category,
            iteration=self._current_iteration,
        )
        self._save()

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        return entry.value if entry else None

    def get_by_category(self, category: str) -> list[MemoryEntry]:
        return [e for e in self._entries.values() if e.category == category]

    def add_progress(self, description: str) -> None:
        key = f"progress_{self._current_iteration}_{uuid4().hex[:8]}"
        self.set_entry(key, description, self.CATEGORY_PROGRESS)

    def add_finding(self, finding: str) -> None:
        key = f"finding_{self._current_iteration}_{uuid4().hex[:8]}"
        self.set_entry(key, finding, self.CATEGORY_FINDINGS)

    def add_todo(self, task: str, completed: bool = False) -> str:
        key = f"todo_{uuid4().hex[:8]}"
        self.set_entry(key, {"task": task, "completed": completed}, self.CATEGORY_TODO)
        return key

    def complete_todo(self, key: str) -> bool:
        entry = self._entries.get(key)
        if entry and entry.category == self.CATEGORY_TODO:
            entry.value["completed"] = True
            entry.iteration = self._current_iteration
            self._save()
            return True
        return False

    def add_decision(self, decision: str, reason: str) -> None:
        key = f"decision_{self._current_iteration}_{uuid4().hex[:8]}"
        self.set_entry(key, {"decision": decision, "reason": reason}, self.CATEGORY_DECISIONS)

    def add_error(self, error: str, context: str | None = None) -> None:
        key = f"error_{self._current_iteration}_{uuid4().hex[:8]}"
        self.set_entry(key, {"error": error, "context": context}, self.CATEGORY_ERRORS)

    def record_file_modified(self, file_path: str) -> None:
        self._files_modified.add(file_path)
        self._save()

    def get_files_modified(self) -> set[str]:
        return self._files_modified.copy()

    def clear_iteration_files(self) -> None:
        self._files_modified.clear()
        self._save()

    def increment_iteration(self) -> int:
        self._current_iteration += 1
        self._save()
        return self._current_iteration

    @property
    def current_iteration(self) -> int:
        return self._current_iteration

    def get_summary(self) -> dict[str, Any]:
        todos = self.get_by_category(self.CATEGORY_TODO)
        pending_todos = [e for e in todos if not e.value.get("completed", False)]
        completed_todos = [e for e in todos if e.value.get("completed", False)]

        return {
            "iteration": self._current_iteration,
            "files_modified_count": len(self._files_modified),
            "total_entries": len(self._entries),
            "pending_todos": len(pending_todos),
            "completed_todos": len(completed_todos),
            "recent_progress": [e.value for e in self.get_by_category(self.CATEGORY_PROGRESS)[-5:]],
            "recent_findings": [e.value for e in self.get_by_category(self.CATEGORY_FINDINGS)[-5:]],
            "errors": [e.value for e in self.get_by_category(self.CATEGORY_ERRORS)],
        }

    def to_context_string(self) -> str:
        summary = self.get_summary()
        lines = [
            f"## Working Memory (Iteration {summary['iteration']})",
            "",
            f"Files Modified: {summary['files_modified_count']}",
            f"Pending Tasks: {summary['pending_todos']}",
            f"Completed Tasks: {summary['completed_todos']}",
        ]

        if summary["recent_progress"]:
            lines.extend(["", "### Recent Progress"])
            for p in summary["recent_progress"]:
                lines.append(f"- {p}")

        if summary["recent_findings"]:
            lines.extend(["", "### Key Findings"])
            for f in summary["recent_findings"]:
                lines.append(f"- {f}")

        pending = [
            e
            for e in self.get_by_category(self.CATEGORY_TODO)
            if not e.value.get("completed", False)
        ]
        if pending:
            lines.extend(["", "### Pending Tasks"])
            for t in pending:
                lines.append(f"- [ ] {t.value['task']}")

        if summary["errors"]:
            lines.extend(["", "### Errors to Address"])
            for e in summary["errors"]:
                lines.append(f"- {e['error']}")

        return "\n".join(lines)

    def clear(self) -> None:
        self._entries.clear()
        self._files_modified.clear()
        self._current_iteration = 0
        if self._memory_file.exists():
            self._memory_file.unlink()


@dataclass
class CompletionResult:
    """完成检测结果."""

    completed: bool  # 是否完成
    reason: CompletionCondition | None = None  # 完成原因
    message: str = ""  # 详细消息
    confidence: float = 1.0  # 置信度


class CompletionDetector:
    """完成检测器.

    支持多条件检测：Promise 标签、最大迭代次数、空闲阈值。
    """

    PROMISE_PATTERN = re.compile(r"<promise>(.*?)</promise>", re.IGNORECASE | re.DOTALL)

    def __init__(self, config: RalphConfig) -> None:
        self._config = config
        self._idle_count = 0
        self._last_files_modified: set[str] = set()

    def check(
        self,
        content: str,
        iteration: int,
        files_modified: set[str],
    ) -> CompletionResult:
        conditions = self._config.completion_conditions

        if CompletionCondition.PROMISE_TAG in conditions:
            match = self.PROMISE_PATTERN.search(content)
            if match:
                promise_text = match.group(1).strip()
                if self._config.completion_promise.lower() in promise_text.lower():
                    return CompletionResult(
                        completed=True,
                        reason=CompletionCondition.PROMISE_TAG,
                        message=f"Completion promise detected: {promise_text}",
                    )

        if (
            CompletionCondition.MAX_ITERATIONS in conditions
            and iteration >= self._config.max_iterations
        ):
            return CompletionResult(
                completed=True,
                reason=CompletionCondition.MAX_ITERATIONS,
                message=f"Max iterations ({self._config.max_iterations}) reached",
            )

        if CompletionCondition.IDLE_THRESHOLD in conditions:
            if files_modified == self._last_files_modified:
                self._idle_count += 1
            else:
                self._idle_count = 0
                self._last_files_modified = files_modified.copy()

            if self._idle_count >= self._config.idle_threshold:
                return CompletionResult(
                    completed=True,
                    reason=CompletionCondition.IDLE_THRESHOLD,
                    message=f"No file changes for {self._idle_count} iterations",
                )

        return CompletionResult(completed=False)

    def reset(self) -> None:
        self._idle_count = 0
        self._last_files_modified.clear()


class ContextManager:
    """上下文管理器.

    协调工具结果缓存、工作记忆和迭代摘要，
    实现智能上下文压缩和按需扩展。
    """

    def __init__(
        self,
        config: RalphConfig,
        tool_cache: ToolResultCache,
        working_memory: WorkingMemory,
        summarize_fn: Callable[[str], Coroutine[Any, Any, str]] | None = None,
    ) -> None:
        self._config = config
        self._tool_cache = tool_cache
        self._memory = working_memory
        self._summarize_fn = summarize_fn
        self._iteration_summaries: dict[int, str] = {}

    async def summarize_tool_result(
        self,
        tool_name: str,
        content: str,
    ) -> str:
        if len(content) <= 500:
            return content

        if self._summarize_fn:
            return await self._summarize_fn(
                f"Summarize this {tool_name} result concisely:\n{content[:5000]}"
            )

        lines = content.split("\n")
        if len(lines) > 20:
            preview = "\n".join(lines[:10])
            return f"{preview}\n... ({len(lines) - 10} more lines)"

        if len(content) > 1000:
            return f"{content[:500]}... ({len(content) - 500} more chars)"

        return content

    async def process_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        content: str,
        iteration: int,
    ) -> str:
        strategy = self._config.context_strategy

        if strategy in (ContextStrategy.TOOL_LEVEL_CACHE, ContextStrategy.ALL):
            summary = await self.summarize_tool_result(tool_name, content)
            self._tool_cache.store(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=arguments,
                full_content=content,
                summary=summary,
                iteration=iteration,
            )
            return summary

        return content

    async def summarize_iteration(
        self,
        iteration: int,
        messages_content: str,
    ) -> str:
        if self._summarize_fn:
            summary = await self._summarize_fn(
                f"Summarize iteration {iteration} progress:\n{messages_content[:8000]}"
            )
        else:
            summary = f"Iteration {iteration} completed. See working memory for details."

        self._iteration_summaries[iteration] = summary
        return summary

    def build_context_prefix(self) -> str:
        parts = [self._memory.to_context_string()]

        if self._iteration_summaries:
            parts.append("\n## Previous Iterations")
            for it, summary in sorted(self._iteration_summaries.items())[-3:]:
                parts.append(f"\n### Iteration {it}\n{summary}")

        recent_tools = list(self._tool_cache._cache.values())[-10:]
        if recent_tools:
            parts.append("\n## Recent Tool Results (Summaries)")
            for result in recent_tools:
                parts.append(
                    f"\n- [{result.tool_name}] {result.summary[:200]}"
                    f"{'...' if len(result.summary) > 200 else ''}"
                )

        return "\n".join(parts)

    def get_full_tool_result(self, tool_call_id: str) -> str | None:
        return self._tool_cache.get_full_content(tool_call_id)

    def clear(self) -> None:
        self._tool_cache.clear()
        self._iteration_summaries.clear()


@dataclass
class RalphState:
    """Ralph 执行状态.

    跟踪 Ralph 循环的运行时状态，包括迭代次数、完成状态和修改的文件。

    Attributes:
        iteration: 当前迭代次数
        started_at: 开始时间戳
        completed: 是否已完成
        completion_reason: 完成原因（如 max_iterations、promise_tag 等）
        total_steps: 总执行步骤数
        files_modified: 已修改的文件路径集合
    """

    iteration: int = 0
    started_at: float = field(default_factory=time.time)
    completed: bool = False
    completion_reason: str | None = None
    total_steps: int = 0
    files_modified: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "started_at": self.started_at,
            "completed": self.completed,
            "completion_reason": self.completion_reason,
            "total_steps": self.total_steps,
            "files_modified": list(self.files_modified),
        }


class RalphLoop:
    """Ralph 迭代循环控制器.

    协调 Ralph 模式的核心组件，管理迭代生命周期、工具结果处理和完成检测。

    核心职责:
        1. 管理迭代状态和生命周期
        2. 协调 ToolResultCache、WorkingMemory、ContextManager
        3. 处理工具执行结果并跟踪文件修改
        4. 检测任务完成条件

    Attributes:
        config: Ralph 配置
        state: 当前执行状态
        context_manager: 上下文管理器
        working_memory: 工作记忆
        tool_cache: 工具结果缓存
    """

    def __init__(
        self,
        config: RalphConfig,
        workspace_dir: Path,
        summarize_fn: Callable[[str], Coroutine[Any, Any, str]] | None = None,
    ) -> None:
        self._config = config
        self._workspace = workspace_dir
        self._tool_cache = ToolResultCache()
        self._memory = WorkingMemory(workspace_dir, config.memory_dir)
        self._context_manager = ContextManager(
            config=config,
            tool_cache=self._tool_cache,
            working_memory=self._memory,
            summarize_fn=summarize_fn,
        )
        self._completion_detector = CompletionDetector(config)
        self._state = RalphState()

    @property
    def config(self) -> RalphConfig:
        return self._config

    @property
    def state(self) -> RalphState:
        return self._state

    @property
    def context_manager(self) -> ContextManager:
        return self._context_manager

    @property
    def working_memory(self) -> WorkingMemory:
        return self._memory

    @property
    def tool_cache(self) -> ToolResultCache:
        return self._tool_cache

    def start_iteration(self) -> int:
        self._state.iteration = self._memory.increment_iteration()
        self._memory.clear_iteration_files()
        return self._state.iteration

    def record_file_modified(self, file_path: str) -> None:
        self._memory.record_file_modified(file_path)
        self._state.files_modified.add(file_path)

    async def process_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        content: str,
    ) -> str:
        if tool_name in ("write_file", "edit_file"):
            file_path = arguments.get("file_path") or arguments.get("path", "")
            if file_path:
                self.record_file_modified(file_path)

        return await self._context_manager.process_tool_result(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            content=content,
            iteration=self._state.iteration,
        )

    def check_completion(self, content: str) -> CompletionResult:
        result = self._completion_detector.check(
            content=content,
            iteration=self._state.iteration,
            files_modified=self._memory.get_files_modified(),
        )
        if result.completed:
            self._state.completed = True
            self._state.completion_reason = result.reason.value if result.reason else None
        return result

    def get_context_prefix(self) -> str:
        return self._context_manager.build_context_prefix()

    async def summarize_iteration(self, messages_content: str) -> str:
        return await self._context_manager.summarize_iteration(
            self._state.iteration,
            messages_content,
        )

    def reset(self) -> None:
        self._state = RalphState()
        self._completion_detector.reset()
        self._context_manager.clear()
        self._memory.clear()

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self._config.enabled,
            "state": self._state.to_dict(),
            "memory_summary": self._memory.get_summary(),
            "config": self._config.to_dict(),
        }
