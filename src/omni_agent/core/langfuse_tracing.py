"""Langfuse 追踪集成，用于 Agent 可观测性。

This module provides Langfuse-based tracing that replaces the legacy AgentLogger.
It integrates with LiteLLM for automatic LLM call tracing and provides decorators
for agents and tool execution tracing.

When Langfuse is disabled, falls back to basic console logging.
"""

import logging
import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

from omni_agent.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_client: Any | None = None
_langfuse_enabled: bool = False
_langfuse_initialized: bool = False

T = TypeVar("T")


def init_langfuse() -> bool:
    """Initialize Langfuse client and LiteLLM integration.

    Returns:
        True if initialization successful, False otherwise.
    """
    global _langfuse_enabled, _langfuse_initialized, _langfuse_client

    if _langfuse_initialized:
        return _langfuse_enabled

    if not settings.LANGFUSE_ENABLED:
        logger.info("Langfuse tracing disabled")
        _langfuse_initialized = True
        return False

    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning("Langfuse enabled but credentials not configured")
        _langfuse_initialized = True
        return False

    try:
        import litellm
        from langfuse import Langfuse

        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

        _langfuse_client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            sample_rate=settings.LANGFUSE_SAMPLE_RATE,
            flush_interval=settings.LANGFUSE_FLUSH_INTERVAL,
        )

        litellm.callbacks = ["langfuse"]
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]

        _langfuse_enabled = True
        _langfuse_initialized = True

        logger.info(f"Langfuse tracing initialized: host={settings.LANGFUSE_HOST}")
        return True

    except ImportError as e:
        logger.warning(f"Langfuse not installed: {e}. Run: pip install langfuse")
        _langfuse_initialized = True
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        _langfuse_initialized = True
        return False


def get_langfuse() -> Any | None:
    """Get the Langfuse client instance."""
    return _langfuse_client if _langfuse_enabled else None


def is_langfuse_enabled() -> bool:
    """Check if Langfuse tracing is enabled."""
    return _langfuse_enabled


def flush_langfuse() -> None:
    """Flush pending Langfuse events."""
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse: {e}")


class ConsoleTracer:
    """Fallback tracer that logs to console when Langfuse is disabled.

    Provides the same interface as LangfuseTracer but uses Python logging.
    """

    def __init__(
        self,
        name: str = "agents",
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ):
        self.name = name
        self.user_id = user_id
        self.session_id = session_id
        self.metadata = metadata or {}
        self.tags = tags or []
        self._start_time: float | None = None
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._task = ""

    @property
    def trace_id(self) -> str | None:
        return None

    def start_trace(self, task: str) -> "ConsoleTracer":
        self._start_time = time.time()
        self._task = task
        logger.info(f"[TRACE START] agents={self.name} task={task[:100]}...")
        return self

    def log_step(
        self,
        step: int,
        max_steps: int,
        token_count: int,
        token_limit: int,
    ) -> None:
        usage_pct = round((token_count / token_limit) * 100, 2)
        logger.info(
            f"[STEP] {step}/{max_steps} | tokens={token_count:,}/{token_limit:,} ({usage_pct}%)"
        )

    def log_llm_response(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str | None = None,
    ) -> None:
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        logger.debug(f"[LLM] input={input_tokens}, output={output_tokens}")

    def get_litellm_metadata(self) -> dict[str, Any]:
        return {}

    @contextmanager
    def span_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ):
        start_time = time.time()
        logger.info(f"[TOOL START] {tool_name}")
        try:
            yield None
        finally:
            execution_time = time.time() - start_time
            logger.info(f"[TOOL END] {tool_name} ({execution_time * 1000:.2f}ms)")

    def end_tool_span(
        self,
        span: Any,
        success: bool,
        content: str | None = None,
        error: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        pass

    def update_tool_span(
        self,
        span: Any,
        success: bool,
        content: str | None = None,
        error: str | None = None,
    ) -> None:
        if not success and error:
            logger.warning(f"[TOOL ERROR] {error}")

    def end_trace(
        self,
        success: bool,
        final_response: str,
        total_steps: int,
        reason: str = "completed",
    ) -> None:
        elapsed = time.time() - self._start_time if self._start_time else 0
        status = "SUCCESS" if success else "FAILED"
        logger.info(
            f"[TRACE END] {status} | steps={total_steps} | "
            f"tokens={self._total_input_tokens + self._total_output_tokens:,} | "
            f"elapsed={elapsed:.2f}s | reason={reason}"
        )


def get_tracer(
    name: str = "agents",
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
) -> "LangfuseTracer | ConsoleTracer":
    """Get appropriate tracer based on Langfuse availability.

    Returns LangfuseTracer if Langfuse is enabled, otherwise ConsoleTracer.
    """
    if _langfuse_enabled:
        return LangfuseTracer(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            tags=tags,
        )
    return ConsoleTracer(
        name=name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
        tags=tags,
    )


class LangfuseTracer:
    """Tracer class for managing Langfuse traces and spans.

    Correctly uses Langfuse's trace -> span hierarchy:
    - Creates root trace with client.trace()
    - Creates spans under trace for tool executions
    - LLM calls are linked via trace_id in metadata
    """

    def __init__(
        self,
        name: str = "agents",
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ):
        self.name = name
        self.user_id = user_id
        self.session_id = session_id
        self.metadata = metadata or {}
        self.tags = tags or []
        self._trace = None
        self._start_time: float | None = None
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    @property
    def trace_id(self) -> str | None:
        """Get current trace ID for linking LLM calls."""
        return self._trace.id if self._trace else None

    def start_trace(self, task: str) -> "LangfuseTracer":
        """Start a new trace for an agents run."""
        if not _langfuse_enabled or not _langfuse_client:
            return self

        try:
            self._start_time = time.time()
            self._trace = _langfuse_client.trace(
                name=self.name,
                user_id=self.user_id,
                session_id=self.session_id,
                input={"task": task},
                metadata=self.metadata,
                tags=self.tags,
            )
        except Exception as e:
            logger.warning(f"Failed to start Langfuse trace: {e}")

        return self

    def log_step(
        self,
        step: int,
        max_steps: int,
        token_count: int,
        token_limit: int,
    ) -> None:
        """Log agents step progress."""
        if not self._trace:
            return

        try:
            self._trace.update(
                metadata={
                    **self.metadata,
                    "current_step": step,
                    "max_steps": max_steps,
                    "token_count": token_count,
                    "token_limit": token_limit,
                    "token_usage_percent": round((token_count / token_limit) * 100, 2),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log step: {e}")

    def log_llm_response(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str | None = None,
    ) -> None:
        """Log LLM response token usage."""
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

    def get_litellm_metadata(self) -> dict[str, Any]:
        """Get metadata dict for LiteLLM calls to link with current trace.

        Usage:
            response = await llm.generate(
                messages=messages,
                tools=tools,
                metadata=tracer.get_litellm_metadata(),
            )
        """
        if not _langfuse_enabled or not self._trace:
            return {}

        return {
            "trace_id": self._trace.id,
        }

    @contextmanager
    def span_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ):
        """Context manager for tracing tool execution.

        Tool execution should be wrapped inside this context manager:

            with tracer.span_tool(name, args) as span:
                result = await tool.execute(...)
                # span will be auto-ended with timing
        """
        if not _langfuse_enabled or not self._trace:
            yield None
            return

        span = None
        start_time = time.time()

        try:
            span = self._trace.span(
                name=f"tool:{tool_name}",
                input={"arguments": arguments},
                metadata={"tool_name": tool_name},
            )
            yield span
        except Exception as e:
            logger.warning(f"Failed to create tool span: {e}")
            yield None
        finally:
            if span:
                try:
                    execution_time = time.time() - start_time
                    span.update(
                        metadata={
                            "tool_name": tool_name,
                            "execution_time_ms": round(execution_time * 1000, 2),
                        }
                    )
                    span.end()
                except Exception:
                    pass

    def end_tool_span(
        self,
        span: Any,
        success: bool,
        content: str | None = None,
        error: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        """End a tool span with result.

        Note: When using span_tool context manager, the span is auto-ended.
        This method is for cases where you need manual control.
        """
        if not span:
            return

        try:
            output = {"success": success}
            if success and content:
                output["result"] = content[:500] if len(content) > 500 else content
            elif error:
                output["error"] = error

            metadata = {"success": success}
            if execution_time is not None:
                metadata["execution_time_ms"] = round(execution_time * 1000, 2)

            span.update(
                output=output,
                metadata=metadata,
                level="ERROR" if not success else "DEFAULT",
            )
            span.end()
        except Exception as e:
            logger.warning(f"Failed to end tool span: {e}")

    def update_tool_span(
        self,
        span: Any,
        success: bool,
        content: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update tool span output without ending it (for use with context manager)."""
        if not span:
            return

        try:
            output = {"success": success}
            if success and content:
                output["result"] = content[:500] if len(content) > 500 else content
            elif error:
                output["error"] = error

            span.update(
                output=output,
                level="ERROR" if not success else "DEFAULT",
            )
        except Exception as e:
            logger.warning(f"Failed to update tool span: {e}")

    def end_trace(
        self,
        success: bool,
        final_response: str,
        total_steps: int,
        reason: str = "completed",
    ) -> None:
        """End the trace with final result."""
        if not self._trace:
            return

        try:
            elapsed = time.time() - self._start_time if self._start_time else 0

            self._trace.update(
                output={
                    "success": success,
                    "response": final_response[:1000]
                    if len(final_response) > 1000
                    else final_response,
                    "reason": reason,
                },
                metadata={
                    **self.metadata,
                    "total_steps": total_steps,
                    "elapsed_seconds": round(elapsed, 3),
                    "total_input_tokens": self._total_input_tokens,
                    "total_output_tokens": self._total_output_tokens,
                    "total_tokens": self._total_input_tokens + self._total_output_tokens,
                },
                level="ERROR" if not success else "DEFAULT",
            )

            flush_langfuse()

        except Exception as e:
            logger.warning(f"Failed to end trace: {e}")
        finally:
            self._trace = None


def trace_agent(
    name: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
):
    """Decorator for tracing agents execution.

    Usage:
        @trace_agent(name="my-agents")
        async def run(self, task: str):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            if not _langfuse_enabled:
                return await func(*args, **kwargs)

            agent_name = name
            if not agent_name and args:
                self_obj = args[0]
                agent_name = getattr(self_obj, "name", None) or "agents"

            tracer = LangfuseTracer(
                name=agent_name or "agents",
                user_id=user_id,
                session_id=session_id,
            )

            task = kwargs.get("task", "")
            if not task and len(args) > 1:
                task = str(args[1])

            tracer.start_trace(task)

            try:
                result = await func(*args, **kwargs)
                tracer.end_trace(
                    success=True,
                    final_response=str(result) if result else "",
                    total_steps=0,
                    reason="completed",
                )
                return result
            except Exception as e:
                tracer.end_trace(
                    success=False,
                    final_response=str(e),
                    total_steps=0,
                    reason="error",
                )
                raise

        return async_wrapper

    return decorator


def trace_tool(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for tracing tool execution.

    Usage:
        @trace_tool
        async def execute(self, **kwargs):
            ...
    """

    @wraps(func)
    async def async_wrapper(*args, **kwargs) -> T:
        return await func(*args, **kwargs)

    return async_wrapper
