from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omni_agent.eval.dataset import EvalCase


@dataclass
class GradeResult:
    passed: bool
    score: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @classmethod
    def success(cls, reason: str = "", **details: Any) -> GradeResult:
        return cls(passed=True, score=1.0, reason=reason, details=details)

    @classmethod
    def failure(cls, reason: str, **details: Any) -> GradeResult:
        return cls(passed=False, score=0.0, reason=reason, details=details)


class BaseGrader(ABC):
    @abstractmethod
    async def grade(self, case: EvalCase, workspace: Path, result: str) -> GradeResult: ...


class OutcomeGrader(BaseGrader):
    async def grade(self, case: EvalCase, workspace: Path, result: str) -> GradeResult:
        checks = case.grading.get("checks", [])
        if not checks:
            return GradeResult.success(reason="no checks defined")

        failures: list[str] = []
        for check in checks:
            ok, msg = await self._evaluate_check(check, workspace, result)
            if not ok:
                failures.append(msg)

        if failures:
            return GradeResult.failure(
                reason="; ".join(failures),
                total_checks=len(checks),
                failed_checks=len(failures),
            )

        return GradeResult.success(
            reason="all checks passed",
            total_checks=len(checks),
        )

    async def _evaluate_check(
        self, check: dict[str, Any], workspace: Path, result: str
    ) -> tuple[bool, str]:
        if "file_contains" in check:
            return self._check_file_contains(check["file_contains"], workspace)
        if "file_exists" in check:
            return self._check_file_exists(check["file_exists"], workspace)
        if "file_not_contains" in check:
            return self._check_file_not_contains(check["file_not_contains"], workspace)
        if "result_contains" in check:
            return self._check_result_contains(check["result_contains"], result)
        if "result_matches" in check:
            return self._check_result_matches(check["result_matches"], result)
        if "file_matches" in check:
            return self._check_file_matches(check["file_matches"], workspace)
        return False, f"unknown check type: {list(check.keys())}"

    def _check_file_contains(self, args: list[str], workspace: Path) -> tuple[bool, str]:
        filepath, pattern = args[0], args[1]
        target = workspace / filepath
        if not target.exists():
            return False, f"file {filepath} not found"
        content = target.read_text()
        if pattern in content:
            return True, ""
        return False, f"file {filepath} does not contain '{pattern}'"

    def _check_file_exists(self, filepath: str, workspace: Path) -> tuple[bool, str]:
        target = workspace / filepath
        if target.exists():
            return True, ""
        return False, f"file {filepath} not found"

    def _check_file_not_contains(self, args: list[str], workspace: Path) -> tuple[bool, str]:
        filepath, pattern = args[0], args[1]
        target = workspace / filepath
        if not target.exists():
            return True, ""
        content = target.read_text()
        if pattern not in content:
            return True, ""
        return False, f"file {filepath} unexpectedly contains '{pattern}'"

    def _check_result_contains(self, pattern: str, result: str) -> tuple[bool, str]:
        if pattern in result:
            return True, ""
        return False, f"result does not contain '{pattern}'"

    def _check_result_matches(self, pattern: str, result: str) -> tuple[bool, str]:
        if re.search(pattern, result):
            return True, ""
        return False, f"result does not match pattern '{pattern}'"

    def _check_file_matches(self, args: list[str], workspace: Path) -> tuple[bool, str]:
        filepath, pattern = args[0], args[1]
        target = workspace / filepath
        if not target.exists():
            return False, f"file {filepath} not found"
        content = target.read_text()
        if re.search(pattern, content):
            return True, ""
        return False, f"file {filepath} does not match pattern '{pattern}'"


class LLMGrader(BaseGrader):
    def __init__(self, llm_client: Any, model: str = "") -> None:
        self._llm = llm_client
        self._model = model

    async def grade(self, case: EvalCase, workspace: Path, result: str) -> GradeResult:
        dimensions = case.grading.get("dimensions", ["completeness", "correctness"])
        criteria = case.grading.get("criteria", "")

        prompt = self._build_judge_prompt(case.task, result, dimensions, criteria)
        response = await self._llm.call(
            messages=[{"role": "user", "content": prompt}],
            model=self._model or None,
        )

        return self._parse_judge_response(response, dimensions)

    def _build_judge_prompt(
        self,
        task: str,
        result: str,
        dimensions: list[str],
        criteria: str,
    ) -> str:
        dim_text = "\n".join(f"- {d}" for d in dimensions)
        return (
            f"You are an evaluation judge. Score the agent's output.\n\n"
            f"## Task\n{task}\n\n"
            f"## Agent Output\n{result}\n\n"
            f"## Dimensions\n{dim_text}\n\n"
            f"{f'## Additional Criteria{chr(10)}{criteria}{chr(10)}{chr(10)}' if criteria else ''}"
            f"## Instructions\n"
            f"For each dimension, give a score from 0.0 to 1.0.\n"
            f"Then give an overall_pass (true/false) and overall_score (0.0-1.0).\n\n"
            f"Respond in JSON:\n"
            f'{{"overall_pass": bool, "overall_score": float, '
            f'"dimensions": {{"dim_name": {{"score": float, "reason": str}}}}}}'
        )

    def _parse_judge_response(self, response: dict[str, Any], dimensions: list[str]) -> GradeResult:
        import json

        content = response.get("content", "")
        try:
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if not json_match:
                return GradeResult.failure(
                    reason=f"LLM judge returned unparseable: {content[:200]}"
                )
            data = json.loads(json_match.group())
            return GradeResult(
                passed=data.get("overall_pass", False),
                score=data.get("overall_score", 0.0),
                details=data.get("dimensions", {}),
                reason="LLM judge evaluation",
            )
        except (json.JSONDecodeError, KeyError) as e:
            return GradeResult.failure(reason=f"failed to parse LLM judge response: {e}")
