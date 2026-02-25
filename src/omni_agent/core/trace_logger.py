"""增强型追踪日志，用于多 Agent 工作流.

提供多 Agent 协作场景的追踪和可视化，支持装饰器模式。

追踪事件类型:
    - WORKFLOW_START/END: 工作流生命周期
    - AGENT_START/END: Agent 执行（含嵌套深度）
    - TASK_START/END: 依赖任务执行
    - DELEGATION: Leader → Member 委派
    - TOOL_CALL: 工具调用
    - LLM_CALL: LLM API 调用
    - MESSAGE_PASS: 任务间消息传递

输出文件:
    - ~/.omni-agents/traces/trace_<type>_<timestamp>_<id>.jsonl (事件流)
    - ~/.omni-agents/traces/trace_*.summary.json (执行摘要)

装饰器:
    - @traced.workflow: 追踪整个工作流
    - @traced.agents: 追踪 Agent 执行
    - @traced.delegation: 追踪任务委派
    - @traced.task: 追踪依赖任务

使用示例:
    @traced.workflow(trace_type="team")
    async def run_team(message: str):
        ...

    # 或手动使用
    trace = TraceLogger()
    trace.start_trace("team", {"team_name": "research"})
    trace.log_agent_start("leader", "coordinator", "analyze task")
    ...
    trace.end_trace(success=True)
"""
import json
import logging
import time
import uuid
import functools
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, ParamSpec
from enum import Enum

P = ParamSpec("P")
T = TypeVar("T")

logger = logging.getLogger("omni_agent.trace")

_current_trace: ContextVar[Optional["TraceLogger"]] = ContextVar("current_trace", default=None)


def get_current_trace() -> Optional["TraceLogger"]:
    return _current_trace.get()


def set_current_trace(trace: Optional["TraceLogger"]) -> None:
    _current_trace.set(trace)


class TraceEventType(str, Enum):
    """Trace event types."""
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TASK_START = "task_start"
    TASK_END = "task_end"
    DELEGATION = "delegation"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    MESSAGE_PASS = "message_pass"
    ERROR = "error"


class TraceLogger:
    """多 Agent 工作流追踪器.

    记录工作流执行的完整事件流，支持：
    - 工作流生命周期追踪
    - Agent 嵌套执行追踪（含深度信息）
    - 任务委派关系追踪
    - 依赖任务执行追踪
    - Token 使用统计

    Attributes:
        trace_id: 追踪标识符
        trace_file: JSONL 事件文件路径
        events: 内存中的事件列表
        agent_stack: Agent 执行栈（用于追踪嵌套）
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        write_file: bool = True,
        write_log: bool = True,
    ):
        """Initialize trace logger.

        Args:
            log_dir: Log directory (defaults to ~/.omni-agents/traces/)
            write_file: Write trace events to JSONL file
            write_log: Output trace events to logging
        """
        self.write_file = write_file
        self.write_log = write_log

        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path.home() / ".omni-agents" / "traces"

        if self.write_file:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        self.trace_id: Optional[str] = None
        self.trace_file: Optional[Path] = None
        self.start_time: Optional[float] = None
        self.events: list[dict] = []
        self.agent_stack: list[dict] = []

    def start_trace(self, trace_type: str, metadata: Optional[dict] = None) -> str:
        """Start a new trace.

        Args:
            trace_type: Type of trace (team, dependency_workflow, single_agent)
            metadata: Additional metadata

        Returns:
            trace_id
        """
        self.trace_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trace_file = self.log_dir / f"trace_{trace_type}_{timestamp}_{self.trace_id}.jsonl"
        self.start_time = time.time()
        self.events = []
        self.agent_stack = []

        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.WORKFLOW_START,
            "timestamp": datetime.now().isoformat(),
            "trace_type": trace_type,
            "metadata": metadata or {}
        }
        self._write_event(event)
        return self.trace_id

    def end_trace(self, success: bool, result: Optional[str] = None):
        """End the current trace."""
        if not self.trace_id:
            return

        elapsed = time.time() - self.start_time if self.start_time else 0
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.WORKFLOW_END,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "elapsed_seconds": round(elapsed, 3),
            "result_preview": result[:200] if result else None,
            "total_events": len(self.events)
        }
        self._write_event(event)
        self._write_summary()

    def log_agent_start(
        self,
        agent_name: str,
        agent_role: str,
        task: str,
        parent_agent: Optional[str] = None,
        depth: int = 0
    ):
        """Log agents execution start."""
        agent_id = f"{agent_name}_{len(self.agent_stack)}"
        agent_info = {
            "agent_id": agent_id,
            "name": agent_name,
            "role": agent_role,
            "depth": depth,
            "parent": parent_agent,
            "start_time": time.time()
        }
        self.agent_stack.append(agent_info)

        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.AGENT_START,
            "timestamp": datetime.now().isoformat(),
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_role": agent_role,
            "task": task,
            "parent_agent": parent_agent,
            "depth": depth
        }
        self._write_event(event)

    def log_agent_end(
        self,
        agent_name: str,
        success: bool,
        result: Optional[str] = None,
        steps: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0
    ):
        """Log agents execution end."""
        if not self.agent_stack:
            return

        agent_info = self.agent_stack.pop()
        elapsed = time.time() - agent_info["start_time"]

        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.AGENT_END,
            "timestamp": datetime.now().isoformat(),
            "agent_id": agent_info["agent_id"],
            "agent_name": agent_name,
            "success": success,
            "steps": steps,
            "elapsed_seconds": round(elapsed, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "result_preview": result[:200] if result else None
        }
        self._write_event(event)

    def log_task_start(
        self,
        task_id: str,
        task_description: str,
        assigned_to: str,
        depends_on: list[str],
        layer: int
    ):
        """Log task execution start in dependency workflow."""
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.TASK_START,
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "task_description": task_description,
            "assigned_to": assigned_to,
            "depends_on": depends_on,
            "layer": layer,
            "start_time": time.time()
        }
        self._write_event(event)

    def log_task_end(
        self,
        task_id: str,
        status: str,
        result: Optional[str] = None,
        elapsed: Optional[float] = None
    ):
        """Log task execution end."""
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.TASK_END,
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "status": status,
            "elapsed_seconds": round(elapsed, 3) if elapsed else None,
            "result_preview": result[:200] if result else None
        }
        self._write_event(event)

    def log_delegation(
        self,
        from_agent: str,
        to_member: str,
        task: str
    ):
        """Log task delegation from leader to member."""
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.DELEGATION,
            "timestamp": datetime.now().isoformat(),
            "from_agent": from_agent,
            "to_member": to_member,
            "task_preview": task[:200]
        }
        self._write_event(event)

    def log_message_pass(
        self,
        from_task: str,
        to_task: str,
        message_preview: str
    ):
        """Log message passing between tasks."""
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.MESSAGE_PASS,
            "timestamp": datetime.now().isoformat(),
            "from_task": from_task,
            "to_task": to_task,
            "message_preview": message_preview[:200]
        }
        self._write_event(event)

    def log_tool_call(
        self,
        agent_name: str,
        tool_name: str,
        arguments: dict,
        success: bool,
        elapsed: float
    ):
        """Log tool execution."""
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.TOOL_CALL,
            "timestamp": datetime.now().isoformat(),
            "agent_name": agent_name,
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
            "elapsed_seconds": round(elapsed, 3)
        }
        self._write_event(event)

    def log_llm_call(
        self,
        agent_name: str,
        model: str,
        tokens: int,
        elapsed: float
    ):
        """Log LLM API call."""
        event = {
            "trace_id": self.trace_id,
            "event_type": TraceEventType.LLM_CALL,
            "timestamp": datetime.now().isoformat(),
            "agent_name": agent_name,
            "model": model,
            "tokens": tokens,
            "elapsed_seconds": round(elapsed, 3)
        }
        self._write_event(event)

    def _write_event(self, event: dict):
        """Write event to trace file and/or logging."""
        self.events.append(event)

        if self.write_log:
            self._log_event(event)

        if self.write_file and self.trace_file:
            with open(self.trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _log_event(self, event: dict):
        """Output event to logging."""
        event_type = event.get("event_type", "")
        trace_id = event.get("trace_id", "")

        if event_type == TraceEventType.WORKFLOW_START:
            logger.info(f"[{trace_id}] WORKFLOW START type={event.get('trace_type')}")

        elif event_type == TraceEventType.WORKFLOW_END:
            logger.info(
                f"[{trace_id}] WORKFLOW END success={event.get('success')} "
                f"duration={event.get('elapsed_seconds')}s"
            )

        elif event_type == TraceEventType.AGENT_START:
            logger.info(
                f"[{trace_id}] AGENT START name={event.get('agent_name')} "
                f"role={event.get('agent_role')} depth={event.get('depth')}"
            )

        elif event_type == TraceEventType.AGENT_END:
            logger.info(
                f"[{trace_id}] AGENT END name={event.get('agent_name')} "
                f"success={event.get('success')} steps={event.get('steps')} "
                f"tokens={event.get('total_tokens')} duration={event.get('elapsed_seconds')}s"
            )

        elif event_type == TraceEventType.TASK_START:
            logger.info(
                f"[{trace_id}] TASK START id={event.get('task_id')} "
                f"assigned_to={event.get('assigned_to')} layer={event.get('layer')}"
            )

        elif event_type == TraceEventType.TASK_END:
            logger.info(
                f"[{trace_id}] TASK END id={event.get('task_id')} "
                f"status={event.get('status')} duration={event.get('elapsed_seconds')}s"
            )

        elif event_type == TraceEventType.DELEGATION:
            logger.info(
                f"[{trace_id}] DELEGATION {event.get('from_agent')} -> {event.get('to_member')}"
            )

        elif event_type == TraceEventType.TOOL_CALL:
            logger.debug(
                f"[{trace_id}] TOOL {event.get('tool_name')} "
                f"success={event.get('success')} duration={event.get('elapsed_seconds')}s"
            )

        elif event_type == TraceEventType.LLM_CALL:
            logger.debug(
                f"[{trace_id}] LLM {event.get('model')} "
                f"tokens={event.get('tokens')} duration={event.get('elapsed_seconds')}s"
            )

    def _write_summary(self):
        """Write execution summary."""
        if not self.events:
            return

        summary = self._generate_summary()

        if self.write_log:
            logger.info(
                f"[{self.trace_id}] SUMMARY duration={summary.get('total_duration_seconds')}s "
                f"events={summary.get('total_events')} tokens={summary.get('total_tokens')} "
                f"agents={len(summary.get('agents', []))}"
            )

        if self.write_file and self.trace_file:
            summary_file = self.trace_file.with_suffix(".summary.json")
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

    def _generate_summary(self) -> dict:
        """Generate execution summary."""
        total_duration = 0
        if self.start_time:
            total_duration = time.time() - self.start_time

        event_counts = {}
        for event in self.events:
            event_type = event.get("event_type", "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        agents = []
        total_input_tokens = 0
        total_output_tokens = 0
        for event in self.events:
            if event.get("event_type") == TraceEventType.AGENT_END:
                input_tokens = event.get("input_tokens", 0)
                output_tokens = event.get("output_tokens", 0)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                agents.append({
                    "agent_id": event.get("agent_id"),
                    "agent_name": event.get("agent_name"),
                    "success": event.get("success"),
                    "steps": event.get("steps"),
                    "elapsed": event.get("elapsed_seconds"),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                })

        tasks = []
        for event in self.events:
            if event.get("event_type") == TraceEventType.TASK_END:
                tasks.append({
                    "task_id": event.get("task_id"),
                    "status": event.get("status"),
                    "elapsed": event.get("elapsed_seconds")
                })

        delegations = []
        for event in self.events:
            if event.get("event_type") == TraceEventType.DELEGATION:
                delegations.append({
                    "from": event.get("from_agent"),
                    "to": event.get("to_member"),
                    "timestamp": event.get("timestamp")
                })

        return {
            "trace_id": self.trace_id,
            "total_duration_seconds": round(total_duration, 3),
            "total_events": len(self.events),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "event_counts": event_counts,
            "agents": agents,
            "tasks": tasks,
            "delegations": delegations,
            "trace_file": str(self.trace_file)
        }

    def get_current_agent(self) -> Optional[str]:
        """Get current executing agents name."""
        if self.agent_stack:
            return self.agent_stack[-1]["agent_id"]
        return None


def trace_workflow(
    trace_type: str = "workflow",
    get_metadata: Optional[Callable[..., dict]] = None
):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = TraceLogger()
            metadata = get_metadata(*args, **kwargs) if get_metadata else {}
            trace.start_trace(trace_type, metadata)
            set_current_trace(trace)

            try:
                result = await func(*args, **kwargs)
                result_str = str(result) if result else None
                trace.end_trace(success=True, result=result_str)
                return result
            except Exception as e:
                trace.end_trace(success=False, result=str(e))
                raise
            finally:
                set_current_trace(None)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = TraceLogger()
            metadata = get_metadata(*args, **kwargs) if get_metadata else {}
            trace.start_trace(trace_type, metadata)
            set_current_trace(trace)

            try:
                result = func(*args, **kwargs)
                result_str = str(result) if result else None
                trace.end_trace(success=True, result=result_str)
                return result
            except Exception as e:
                trace.end_trace(success=False, result=str(e))
                raise
            finally:
                set_current_trace(None)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def trace_agent(
    name_attr: str = "name",
    role_attr: str = "role",
    task_param: str = "task",
    depth: int = 0
):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = get_current_trace()
            if not trace:
                return await func(*args, **kwargs)

            self_obj = args[0] if args else None
            agent_name = getattr(self_obj, name_attr, "unknown") if self_obj else "unknown"
            agent_role = getattr(self_obj, role_attr, "agents") if self_obj else "agents"
            task = kwargs.get(task_param, str(args[1]) if len(args) > 1 else "")

            trace.log_agent_start(agent_name, agent_role, task, depth=depth)
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                success = True
                if hasattr(result, "success"):
                    success = result.success
                result_str = str(result) if result else None
                trace.log_agent_end(agent_name, success, result_str, steps=0)
                return result
            except Exception as e:
                trace.log_agent_end(agent_name, False, str(e), steps=0)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = get_current_trace()
            if not trace:
                return func(*args, **kwargs)

            self_obj = args[0] if args else None
            agent_name = getattr(self_obj, name_attr, "unknown") if self_obj else "unknown"
            agent_role = getattr(self_obj, role_attr, "agents") if self_obj else "agents"
            task = kwargs.get(task_param, str(args[1]) if len(args) > 1 else "")

            trace.log_agent_start(agent_name, agent_role, task, depth=depth)

            try:
                result = func(*args, **kwargs)
                success = True
                if hasattr(result, "success"):
                    success = result.success
                result_str = str(result) if result else None
                trace.log_agent_end(agent_name, success, result_str, steps=0)
                return result
            except Exception as e:
                trace.log_agent_end(agent_name, False, str(e), steps=0)
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def trace_delegation(from_agent: str = "Leader"):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = get_current_trace()
            member_name = kwargs.get("member_name", args[1] if len(args) > 1 else "unknown")
            task = kwargs.get("task", args[2] if len(args) > 2 else "")

            if trace:
                trace.log_delegation(from_agent, member_name, task)

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = get_current_trace()
            member_name = kwargs.get("member_name", args[1] if len(args) > 1 else "unknown")
            task = kwargs.get("task", args[2] if len(args) > 2 else "")

            if trace:
                trace.log_delegation(from_agent, member_name, task)

            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def trace_task(task_id_param: str = "task_id", layer: int = 0):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            trace = get_current_trace()
            if not trace:
                return await func(*args, **kwargs)

            task_obj = kwargs.get("task", args[1] if len(args) > 1 else None)
            task_id = getattr(task_obj, "id", str(task_obj)) if task_obj else "unknown"
            task_desc = getattr(task_obj, "task", "") if task_obj else ""
            assigned_to = getattr(task_obj, "assigned_to", "") if task_obj else ""
            depends_on = getattr(task_obj, "depends_on", []) if task_obj else []

            trace.log_task_start(task_id, task_desc, assigned_to, depends_on, layer)
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                status = getattr(result, "status", "completed") if result else "completed"
                result_str = getattr(result, "result", str(result)) if result else None
                trace.log_task_end(task_id, status, result_str, elapsed)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                trace.log_task_end(task_id, "failed", str(e), elapsed)
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return func
    return decorator


class traced:
    @staticmethod
    def workflow(trace_type: str = "workflow", get_metadata: Optional[Callable] = None):
        return trace_workflow(trace_type, get_metadata)

    @staticmethod
    def agent(name_attr: str = "name", role_attr: str = "role", task_param: str = "task", depth: int = 0):
        return trace_agent(name_attr, role_attr, task_param, depth)

    @staticmethod
    def delegation(from_agent: str = "Leader"):
        return trace_delegation(from_agent)

    @staticmethod
    def task(task_id_param: str = "task_id", layer: int = 0):
        return trace_task(task_id_param, layer)
