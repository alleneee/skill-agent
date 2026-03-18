from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class PlanStatus(Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class PlanStep:
    description: str
    done: bool = False


@dataclass
class Plan:
    task_summary: str
    steps: list[PlanStep]
    constraints: list[str] = field(default_factory=list)
    done_when: list[str] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT

    def mark_step_done(self, index: int) -> None:
        if 0 <= index < len(self.steps):
            self.steps[index].done = True
            if all(s.done for s in self.steps):
                self.status = PlanStatus.COMPLETED

    def approve(self) -> None:
        self.status = PlanStatus.APPROVED

    def start(self) -> None:
        if self.status in (PlanStatus.APPROVED, PlanStatus.DRAFT):
            self.status = PlanStatus.IN_PROGRESS

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.done) / len(self.steps)

    @property
    def current_step_index(self) -> Optional[int]:
        for i, step in enumerate(self.steps):
            if not step.done:
                return i
        return None

    def to_markdown(self) -> str:
        lines = [
            f"# Plan: {self.task_summary}",
            "",
            f"**Status**: {self.status.value}",
            f"**Progress**: {self.progress:.0%}",
            "",
            "## Steps",
        ]
        for step in self.steps:
            marker = "x" if step.done else " "
            lines.append(f"- [{marker}] {step.description}")

        if self.constraints:
            lines.append("")
            lines.append("## Constraints")
            for c in self.constraints:
                lines.append(f"- {c}")

        if self.done_when:
            lines.append("")
            lines.append("## Done When")
            for d in self.done_when:
                lines.append(f"- {d}")

        lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, content: str) -> Plan:
        title_match = re.search(r"^# Plan:\s*(.+)$", content, re.MULTILINE)
        task_summary = title_match.group(1).strip() if title_match else ""

        status_match = re.search(r"\*\*Status\*\*:\s*(\w+)", content)
        status = PlanStatus(status_match.group(1)) if status_match else PlanStatus.DRAFT

        steps: list[PlanStep] = []
        in_steps = False
        in_constraints = False
        in_done_when = False
        constraints: list[str] = []
        done_when: list[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "## Steps":
                in_steps = True
                in_constraints = False
                in_done_when = False
                continue
            elif stripped == "## Constraints":
                in_steps = False
                in_constraints = True
                in_done_when = False
                continue
            elif stripped == "## Done When":
                in_steps = False
                in_constraints = False
                in_done_when = True
                continue
            elif stripped.startswith("## "):
                in_steps = False
                in_constraints = False
                in_done_when = False
                continue

            if in_steps and stripped.startswith("- ["):
                done = stripped[3] == "x"
                desc = stripped[6:].strip()
                steps.append(PlanStep(description=desc, done=done))
            elif in_constraints and stripped.startswith("- "):
                constraints.append(stripped[2:])
            elif in_done_when and stripped.startswith("- "):
                done_when.append(stripped[2:])

        return cls(
            task_summary=task_summary,
            steps=steps,
            constraints=constraints,
            done_when=done_when,
            status=status,
        )

    def save(self, workspace: Path) -> None:
        plan_dir = workspace / ".agent"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text(self.to_markdown())

    @classmethod
    def load(cls, workspace: Path) -> Optional[Plan]:
        path = workspace / ".agent" / "plan.md"
        if path.exists():
            return cls.from_markdown(path.read_text())
        return None
