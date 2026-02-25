"""检查点系统，用于 Agent 状态持久化和恢复.

支持 Agent 执行状态的保存和恢复，实现断点续传功能。

核心组件:
    - Checkpoint: 检查点数据结构，包含消息历史、工具调用、token 使用
    - CheckpointStorage: 存储协议，定义保存/加载接口
    - FileCheckpointStorage: 文件系统存储实现
    - MemoryCheckpointStorage: 内存存储实现（用于测试）
    - CheckpointConfig: 检查点配置

存储位置:
    默认存储在 ~/.omni-agents/checkpoints/<thread_id>/ckpt_*.json

使用场景:
    - 长时间运行的任务断点续传
    - 用户输入等待时保存状态
    - 工具执行失败后恢复

使用示例:
    storage = FileCheckpointStorage()
    checkpoint = Checkpoint.create(
        agent_id="agent_1",
        thread_id="thread_123",
        step=5,
        status="running",
        messages=messages,
    )
    await storage.save(checkpoint)

    # 恢复
    latest = await storage.load_latest("thread_123")
"""
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import uuid4

from omni_agent.schemas.message import Message, ToolCall, FunctionCall


@dataclass
class Checkpoint:
    id: str
    agent_id: str
    thread_id: str
    step: int
    status: str
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    token_usage: dict[str, int]
    metadata: dict[str, Any]
    created_at: str
    parent_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        agent_id: str,
        thread_id: str,
        step: int,
        status: str,
        messages: list[Message],
        pending_tool_calls: Optional[list[ToolCall]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> "Checkpoint":
        return cls(
            id=f"ckpt_{uuid4().hex[:12]}",
            agent_id=agent_id,
            thread_id=thread_id,
            step=step,
            status=status,
            messages=[cls._serialize_message(m) for m in messages],
            pending_tool_calls=[cls._serialize_tool_call(tc) for tc in (pending_tool_calls or [])],
            token_usage={"input": input_tokens, "output": output_tokens},
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
            parent_id=parent_id,
        )

    @staticmethod
    def _serialize_message(msg: Message) -> dict[str, Any]:
        data = {
            "role": msg.role,
            "content": msg.content,
        }
        if msg.thinking:
            data["thinking"] = msg.thinking
        if msg.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in msg.tool_calls
            ]
        if msg.tool_call_id:
            data["tool_call_id"] = msg.tool_call_id
        if msg.name:
            data["name"] = msg.name
        return data

    @staticmethod
    def _serialize_tool_call(tc: ToolCall) -> dict[str, Any]:
        return {
            "id": tc.id,
            "type": tc.type,
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
        }

    @staticmethod
    def _deserialize_message(data: dict[str, Any]) -> Message:
        tool_calls = None
        if "tool_calls" in data and data["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    type=tc["type"],
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    )
                )
                for tc in data["tool_calls"]
            ]
        return Message(
            role=data["role"],
            content=data.get("content", ""),
            thinking=data.get("thinking"),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
        )

    def get_messages(self) -> list[Message]:
        return [self._deserialize_message(m) for m in self.messages]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        return cls(**data)


@runtime_checkable
class CheckpointStorage(Protocol):

    async def save(self, checkpoint: Checkpoint) -> None:
        ...

    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        ...

    async def load_latest(self, thread_id: str) -> Optional[Checkpoint]:
        ...

    async def list_checkpoints(
        self,
        thread_id: str,
        limit: int = 10,
    ) -> list[Checkpoint]:
        ...

    async def delete(self, checkpoint_id: str) -> bool:
        ...

    async def delete_thread(self, thread_id: str) -> int:
        ...


class FileCheckpointStorage:

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.expanduser("~/.omni-agent/checkpoints")
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _get_thread_dir(self, thread_id: str) -> Path:
        thread_dir = self._base_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    def _get_checkpoint_path(self, thread_id: str, checkpoint_id: str) -> Path:
        return self._get_thread_dir(thread_id) / f"{checkpoint_id}.json"

    async def save(self, checkpoint: Checkpoint) -> None:
        path = self._get_checkpoint_path(checkpoint.thread_id, checkpoint.id)
        data = checkpoint.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        for thread_dir in self._base_dir.iterdir():
            if not thread_dir.is_dir():
                continue
            path = thread_dir / f"{checkpoint_id}.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return Checkpoint.from_dict(data)
        return None

    async def load_latest(self, thread_id: str) -> Optional[Checkpoint]:
        thread_dir = self._get_thread_dir(thread_id)
        if not thread_dir.exists():
            return None

        checkpoints = []
        for path in thread_dir.glob("ckpt_*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                checkpoints.append(Checkpoint.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue

        if not checkpoints:
            return None

        return max(checkpoints, key=lambda c: c.created_at)

    async def list_checkpoints(
        self,
        thread_id: str,
        limit: int = 10,
    ) -> list[Checkpoint]:
        thread_dir = self._get_thread_dir(thread_id)
        if not thread_dir.exists():
            return []

        checkpoints = []
        for path in thread_dir.glob("ckpt_*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                checkpoints.append(Checkpoint.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue

        checkpoints.sort(key=lambda c: c.created_at, reverse=True)
        return checkpoints[:limit]

    async def delete(self, checkpoint_id: str) -> bool:
        for thread_dir in self._base_dir.iterdir():
            if not thread_dir.is_dir():
                continue
            path = thread_dir / f"{checkpoint_id}.json"
            if path.exists():
                path.unlink()
                return True
        return False

    async def delete_thread(self, thread_id: str) -> int:
        thread_dir = self._get_thread_dir(thread_id)
        if not thread_dir.exists():
            return 0

        count = 0
        for path in thread_dir.glob("ckpt_*.json"):
            path.unlink()
            count += 1

        if not any(thread_dir.iterdir()):
            thread_dir.rmdir()

        return count


class MemoryCheckpointStorage:

    def __init__(self):
        self._checkpoints: dict[str, Checkpoint] = {}
        self._thread_index: dict[str, list[str]] = {}

    async def save(self, checkpoint: Checkpoint) -> None:
        self._checkpoints[checkpoint.id] = checkpoint
        if checkpoint.thread_id not in self._thread_index:
            self._thread_index[checkpoint.thread_id] = []
        self._thread_index[checkpoint.thread_id].append(checkpoint.id)

    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        return self._checkpoints.get(checkpoint_id)

    async def load_latest(self, thread_id: str) -> Optional[Checkpoint]:
        checkpoint_ids = self._thread_index.get(thread_id, [])
        if not checkpoint_ids:
            return None

        checkpoints = [self._checkpoints[cid] for cid in checkpoint_ids if cid in self._checkpoints]
        if not checkpoints:
            return None

        return max(checkpoints, key=lambda c: c.created_at)

    async def list_checkpoints(
        self,
        thread_id: str,
        limit: int = 10,
    ) -> list[Checkpoint]:
        checkpoint_ids = self._thread_index.get(thread_id, [])
        checkpoints = [self._checkpoints[cid] for cid in checkpoint_ids if cid in self._checkpoints]
        checkpoints.sort(key=lambda c: c.created_at, reverse=True)
        return checkpoints[:limit]

    async def delete(self, checkpoint_id: str) -> bool:
        if checkpoint_id not in self._checkpoints:
            return False

        checkpoint = self._checkpoints.pop(checkpoint_id)
        if checkpoint.thread_id in self._thread_index:
            self._thread_index[checkpoint.thread_id] = [
                cid for cid in self._thread_index[checkpoint.thread_id]
                if cid != checkpoint_id
            ]
        return True

    async def delete_thread(self, thread_id: str) -> int:
        checkpoint_ids = self._thread_index.pop(thread_id, [])
        count = 0
        for cid in checkpoint_ids:
            if cid in self._checkpoints:
                del self._checkpoints[cid]
                count += 1
        return count


@dataclass
class CheckpointConfig:
    enabled: bool = True
    storage: Optional[CheckpointStorage] = None
    save_on_tool_execution: bool = True
    save_on_user_input: bool = True
    save_on_step: bool = False
    max_checkpoints_per_thread: int = 50

    def get_storage(self) -> CheckpointStorage:
        if self.storage is None:
            return FileCheckpointStorage()
        return self.storage
