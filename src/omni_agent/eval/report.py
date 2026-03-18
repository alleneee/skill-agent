from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omni_agent.eval.grader import GradeResult


@dataclass
class EvalResult:
    case_id: str
    grade: GradeResult
    duration: float = 0.0
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.grade.passed and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "score": self.grade.score,
            "reason": self.grade.reason,
            "duration": round(self.duration, 2),
            "steps": self.steps,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "error": self.error,
            "details": self.grade.details,
        }


@dataclass
class EvalReport:
    results: list[EvalResult] = field(default_factory=list)
    dataset_name: str = ""
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    @property
    def avg_duration(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.duration for r in self.results) / len(self.results)

    @property
    def total_tokens(self) -> int:
        return sum(r.input_tokens + r.output_tokens for r in self.results)

    @property
    def avg_steps(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.steps for r in self.results) / len(self.results)

    def add(self, result: EvalResult) -> None:
        self.results.append(result)

    def finalize(self) -> None:
        self.ended_at = time.time()

    def summary(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "accuracy": f"{self.accuracy:.1%}",
            "avg_duration": f"{self.avg_duration:.2f}s",
            "avg_steps": f"{self.avg_steps:.1f}",
            "total_tokens": self.total_tokens,
            "elapsed": f"{self.ended_at - self.started_at:.1f}s" if self.ended_at else "running",
        }

    def to_terminal(self) -> str:
        lines = []
        lines.append(f"\n{'=' * 60}")
        lines.append(f"Eval Report: {self.dataset_name}")
        lines.append(f"{'=' * 60}")

        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"  [{status}] {r.case_id:30s} "
                f"{r.duration:6.1f}s  {r.steps:2d} steps  "
                f"{r.input_tokens + r.output_tokens:6d} tokens"
            )
            if not r.passed:
                reason = r.error or r.grade.reason
                lines.append(f"         -> {reason}")

        lines.append(f"{'-' * 60}")
        s = self.summary()
        lines.append(
            f"  Accuracy: {s['accuracy']}  "
            f"({s['passed']}/{s['total']})  "
            f"Avg: {s['avg_duration']}  "
            f"Tokens: {s['total_tokens']}"
        )
        lines.append(f"{'=' * 60}\n")
        return "\n".join(lines)

    def save_json(self, path: Path) -> None:
        data = {
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def compare(current_path: Path, previous_path: Path) -> str:
        with open(current_path) as f:
            current = json.load(f)
        with open(previous_path) as f:
            previous = json.load(f)

        cs = current["summary"]
        ps = previous["summary"]

        curr_results = {r["case_id"]: r for r in current["results"]}
        prev_results = {r["case_id"]: r for r in previous["results"]}

        lines = [
            f"\n{'=' * 60}",
            "Eval Comparison",
            f"{'=' * 60}",
            f"  {'Metric':<20s} {'Previous':>12s} {'Current':>12s} {'Delta':>10s}",
            f"  {'-' * 54}",
        ]

        def _delta(curr_str: str, prev_str: str) -> str:
            try:
                cv = float(curr_str.rstrip("s%"))
                pv = float(prev_str.rstrip("s%"))
                d = cv - pv
                sign = "+" if d > 0 else ""
                return f"{sign}{d:.1f}"
            except (ValueError, TypeError):
                return "-"

        for key in ["accuracy", "avg_duration", "avg_steps", "total_tokens"]:
            lines.append(
                f"  {key:<20s} {str(ps.get(key, '-')):>12s} "
                f"{str(cs.get(key, '-')):>12s} {_delta(str(cs.get(key, '0')), str(ps.get(key, '0'))):>10s}"
            )

        regressions = []
        improvements = []
        for case_id, cr in curr_results.items():
            pr = prev_results.get(case_id)
            if not pr:
                continue
            if pr["passed"] and not cr["passed"]:
                regressions.append(case_id)
            elif not pr["passed"] and cr["passed"]:
                improvements.append(case_id)

        if regressions:
            lines.append(f"\n  REGRESSIONS ({len(regressions)}):")
            for r in regressions:
                lines.append(f"    - {r}")
        if improvements:
            lines.append(f"\n  IMPROVEMENTS ({len(improvements)}):")
            for i in improvements:
                lines.append(f"    + {i}")
        if not regressions and not improvements:
            lines.append("\n  No regressions or improvements detected.")

        lines.append(f"{'=' * 60}\n")
        return "\n".join(lines)
