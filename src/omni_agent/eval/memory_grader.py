from __future__ import annotations

from pathlib import Path

from omni_agent.eval.dataset import EvalCase
from omni_agent.eval.grader import BaseGrader, GradeResult


class FactRetentionGrader(BaseGrader):
    async def grade(self, case: EvalCase, workspace: Path, result: str) -> GradeResult:
        facts: list[str] = case.grading.get("injected_facts", [])
        test_level: str = case.grading.get("test_level", "L1")
        min_retention_rate: float = case.grading.get("min_retention_rate", 0.8)

        if not facts:
            return GradeResult.success(reason="no injected_facts defined")

        result_lower = result.lower()
        retained_facts: list[str] = []
        lost_facts: list[str] = []

        for fact in facts:
            if self._fact_retained(fact, result_lower):
                retained_facts.append(fact)
            else:
                lost_facts.append(fact)

        retained_count = len(retained_facts)
        retention_rate = retained_count / len(facts)

        return GradeResult(
            passed=retention_rate >= min_retention_rate,
            score=retention_rate,
            details={
                "retention_rate": retention_rate,
                "total_facts": len(facts),
                "retained_count": retained_count,
                "lost_facts": lost_facts,
                "retained_facts": retained_facts,
                "test_level": test_level,
            },
            reason=f"retention {retained_count}/{len(facts)} ({retention_rate:.0%}), min required: {min_retention_rate:.0%}",
        )

    def _fact_retained(self, fact: str, result_lower: str) -> bool:
        if fact.lower() in result_lower:
            return True
        return self._keyword_match(fact, result_lower)

    def _keyword_match(self, fact: str, result_lower: str) -> bool:
        keywords = [w for w in fact.lower().split() if len(w) > 1]
        if not keywords:
            return False
        matched = sum(1 for kw in keywords if kw in result_lower)
        return matched / len(keywords) >= 0.8
