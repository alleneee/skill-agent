"""Agent 钩子基类定义."""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from omni_agent.core.agent import AgentState


@dataclass
class HookContext:
    """Hook 执行上下文.

    传递给 AgentHook 的上下文信息，包含当前状态和元数据。
    """
    state: "AgentState"
    step: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentHook(ABC):
    """Agent 钩子基类.

    定义执行前、执行中、执行后的扩展点，允许自定义行为注入。
    通过 priority 属性控制多个钩子的执行顺序。
    """
    priority: int = 100

    async def before_run(self, ctx: HookContext) -> None:
        pass

    async def on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        pass

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        pass

    async def on_feedback(self, ctx: HookContext, feedback_type: str, data: dict[str, Any]) -> None:
        pass
