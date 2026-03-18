from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from omni_agent.core.hooks import AgentHook, HookContext


class FeedbackType(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    CANCEL = "cancel"
    RATING = "rating"


@dataclass
class UserFeedback:
    type: FeedbackType
    run_id: str
    step: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "run_id": self.run_id,
            "step": self.step,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class FeedbackHook(AgentHook):
    priority: int = 50

    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._feedbacks: list[UserFeedback] = []
        self._run_id: str = ""

    async def before_run(self, ctx: HookContext) -> None:
        self._feedbacks.clear()
        self._run_id = ctx.metadata.get("run_id", "")

    async def record(self, feedback: UserFeedback) -> None:
        self._feedbacks.append(feedback)
        self._append_to_log(feedback)

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        rejected = [f for f in self._feedbacks if f.type == FeedbackType.REJECT]
        if rejected:
            self._export_eval_case(ctx, result, rejected)

    def _append_to_log(self, feedback: UserFeedback) -> None:
        log_file = self._storage_dir / "feedback.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(feedback.to_dict(), ensure_ascii=False) + "\n")

    def _export_eval_case(
        self,
        ctx: HookContext,
        result: str,
        rejected: list[UserFeedback],
    ) -> None:
        import yaml

        eval_dir = self._storage_dir / "regression_cases"
        eval_dir.mkdir(parents=True, exist_ok=True)

        task = ""
        for msg in ctx.state.messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                task = msg.get("content", "")
                break

        if not task:
            return

        case = {
            "id": f"regression_{self._run_id}_{int(time.time())}",
            "task": task,
            "tags": ["regression", "auto_generated"],
            "max_steps": 10,
            "timeout": 60,
            "grading": {
                "type": "llm",
                "criteria": (
                    f"Previous attempt was rejected. "
                    f"Rejection reasons: {[f.data.get('reason', '') for f in rejected]}"
                ),
                "dimensions": ["completeness", "correctness"],
            },
        }

        case_file = eval_dir / f"{case['id']}.yaml"
        with open(case_file, "w") as f:
            yaml.dump([case], f, allow_unicode=True, default_flow_style=False)
