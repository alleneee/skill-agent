"""Agent 基类定义

定义 Agent 的核心抽象接口
"""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from omni_agent.schemas.message import Message


class AgentStatus(Enum):
    """Agent 运行状态"""

    IDLE = "idle"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class AgentBase(ABC):
    """Agent 抽象基类

    定义 Agent 的核心接口：
    - run(): 执行任务
    - run_stream(): 流式执行任务
    - observe(): 接收外部消息
    - interrupt(): 中断执行
    """

    def __init__(
        self,
        name: Optional[str] = None,
        max_steps: int = 50,
    ) -> None:
        self.id = str(uuid4())
        self.name = name or "agent"
        self.max_steps = max_steps
        self._status = AgentStatus.IDLE
        self._current_task: Optional[asyncio.Task] = None
        self._cancel_event: Optional[asyncio.Event] = None
        self._subscribers: dict[str, list["AgentBase"]] = {}

    @property
    def status(self) -> AgentStatus:
        """获取当前状态"""
        return self._status

    @abstractmethod
    async def run(self, task: str) -> tuple[str, list[dict[str, Any]]]:
        """执行任务

        Args:
            task: 任务描述

        Returns:
            (结果文本, 执行日志列表)
        """
        raise NotImplementedError

    @abstractmethod
    async def run_stream(self, task: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行任务

        Args:
            task: 任务描述

        Yields:
            执行事件
        """
        raise NotImplementedError
        yield  # type: ignore

    async def observe(self, msg: Message | list[Message]) -> None:
        """接收外部消息（不生成回复）

        用于多 Agent 协作场景
        """
        pass

    async def interrupt(self) -> None:
        """中断当前执行"""
        if self._cancel_event:
            self._cancel_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    def add_subscriber(self, hub_name: str, agent: "AgentBase") -> None:
        """添加消息订阅者"""
        if hub_name not in self._subscribers:
            self._subscribers[hub_name] = []
        if agent not in self._subscribers[hub_name] and agent != self:
            self._subscribers[hub_name].append(agent)

    def remove_subscriber(self, hub_name: str, agent: "AgentBase") -> None:
        """移除消息订阅者"""
        if hub_name in self._subscribers and agent in self._subscribers[hub_name]:
            self._subscribers[hub_name].remove(agent)

    def clear_subscribers(self, hub_name: Optional[str] = None) -> None:
        """清除订阅者"""
        if hub_name:
            self._subscribers.pop(hub_name, None)
        else:
            self._subscribers.clear()

    async def _broadcast(self, msg: Message) -> None:
        """广播消息给所有订阅者"""
        for subscribers in self._subscribers.values():
            for subscriber in subscribers:
                await subscriber.observe(msg)

    async def __call__(self, task: str) -> tuple[str, list[dict[str, Any]]]:
        """调用 Agent 执行任务"""
        return await self.run(task)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"
