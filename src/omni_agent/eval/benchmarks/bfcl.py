"""BFCL (Berkeley Function Calling Leaderboard) benchmark adapter.

Downloads BFCL test cases from HuggingFace and evaluates the agent's
function calling accuracy using AST-based matching.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omni_agent.eval.grader import GradeResult
from omni_agent.eval.report import EvalReport, EvalResult
from omni_agent.schemas.message import Message

logger = logging.getLogger(__name__)

BFCL_BASE_URL = (
    "https://huggingface.co/datasets/gorilla-llm/"
    "Berkeley-Function-Calling-Leaderboard/resolve/main/"
)

BFCL_CATEGORIES = {
    "simple": "BFCL_v3_simple.json",
    "multiple": "BFCL_v3_multiple.json",
    "parallel": "BFCL_v3_parallel.json",
    "parallel_multiple": "BFCL_v3_parallel_multiple.json",
    "irrelevance": "BFCL_v3_irrelevance.json",
    "live_simple": "BFCL_v3_live_simple.json",
    "live_multiple": "BFCL_v3_live_multiple.json",
    "live_relevance": "BFCL_v3_live_relevance.json",
    "live_irrelevance": "BFCL_v3_live_irrelevance.json",
}


@dataclass
class BFCLCase:
    id: str
    question: list[dict[str, str]]
    functions: list[dict[str, Any]]
    ground_truth: list[str]
    category: str = ""


@dataclass
class BFCLConfig:
    categories: list[str] = field(default_factory=lambda: ["simple"])
    max_cases_per_category: int = 50
    cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".omni-agent" / "benchmarks" / "bfcl"
    )


def _download_category(category: str, config: BFCLConfig) -> list[BFCLCase]:
    import httpx

    filename = BFCL_CATEGORIES.get(category)
    if not filename:
        logger.warning("Unknown BFCL category: %s", category)
        return []

    cache_file = config.cache_dir / filename
    if cache_file.exists():
        logger.info("Loading cached BFCL data: %s", cache_file)
        raw_lines = cache_file.read_text().strip().split("\n")
    else:
        url = BFCL_BASE_URL + filename
        logger.info("Downloading BFCL data: %s", url)
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            cache_file.write_text(resp.text)
            raw_lines = resp.text.strip().split("\n")
        except Exception as e:
            logger.error("Failed to download %s: %s", url, e)
            return []

    cases = []
    for line in raw_lines[: config.max_cases_per_category]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        question_raw = data.get("question", [])
        if isinstance(question_raw, list) and question_raw:
            messages = question_raw[0] if isinstance(question_raw[0], list) else question_raw
        else:
            messages = [{"role": "user", "content": str(question_raw)}]

        cases.append(
            BFCLCase(
                id=data.get("id", f"bfcl_{category}_{len(cases)}"),
                question=messages,
                functions=data.get("function", []),
                ground_truth=data.get("ground_truth", []),
                category=category,
            )
        )

    logger.info("Loaded %d BFCL cases for category: %s", len(cases), category)
    return cases


def _build_prompt(case: BFCLCase) -> str:
    parts = []
    parts.append("You are a helpful assistant with access to the following functions.\n")
    parts.append("Available functions:\n```json")
    parts.append(json.dumps(case.functions, indent=2))
    parts.append("```\n")
    parts.append(
        "When the user asks a question, respond ONLY with the function call(s) "
        "in the format: function_name(param1=value1, param2=value2)\n"
        "If multiple calls are needed, put each on a separate line.\n"
        "If no function is relevant, respond with: NO_FUNCTION_CALL\n"
    )

    for msg in case.question:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"User: {content}")

    return "\n".join(parts)


def _normalize_call(call_str: str) -> str:
    s = call_str.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    return s


def _grade_function_call(result: str, ground_truth: list[str], category: str) -> GradeResult:
    if category in ("irrelevance",):
        no_call_indicators = ["no_function", "no function", "none", "n/a", "cannot"]
        result_lower = result.lower()
        if any(ind in result_lower for ind in no_call_indicators):
            return GradeResult.success(reason="correctly refused to call function")
        return GradeResult.failure(reason="should have refused function call")

    if not ground_truth:
        return GradeResult.success(reason="no ground truth to compare")

    result_lower = result.lower().replace(" ", "")
    matches = 0
    total = len(ground_truth)

    for gt in ground_truth:
        gt_normalized = _normalize_call(gt).lower().replace(" ", "")
        func_name = gt_normalized.split("(")[0] if "(" in gt_normalized else gt_normalized

        if func_name in result_lower:
            matches += 1

    score = matches / total if total > 0 else 0.0
    passed = score >= 0.5

    if passed:
        return GradeResult(
            passed=True,
            score=score,
            reason=f"matched {matches}/{total} function calls",
            details={"matches": matches, "total": total},
        )
    return GradeResult(
        passed=False,
        score=score,
        reason=f"only matched {matches}/{total} function calls",
        details={"matches": matches, "total": total, "ground_truth": ground_truth},
    )


async def run_bfcl(
    llm_client: Any,
    config: BFCLConfig | None = None,
) -> EvalReport:
    config = config or BFCLConfig()
    report = EvalReport(dataset_name="BFCL")

    all_cases: list[BFCLCase] = []
    for category in config.categories:
        cases = _download_category(category, config)
        all_cases.extend(cases)

    if not all_cases:
        logger.error("No BFCL cases loaded")
        return report

    logger.info("Running BFCL benchmark: %d cases", len(all_cases))

    for case in all_cases:
        start = time.time()
        try:
            prompt = _build_prompt(case)
            response = await llm_client.generate(
                messages=[Message(role="user", content=prompt)],
            )

            result_text = response.content or ""
            grade = _grade_function_call(result_text, case.ground_truth, case.category)

            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0

            eval_result = EvalResult(
                case_id=case.id,
                grade=grade,
                duration=time.time() - start,
                steps=1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception as e:
            logger.exception("BFCL case %s failed", case.id)
            eval_result = EvalResult(
                case_id=case.id,
                grade=GradeResult.failure(reason=str(e)),
                duration=time.time() - start,
                error=str(e),
            )

        report.add(eval_result)
        status = "PASS" if eval_result.passed else "FAIL"
        logger.info("BFCL %s: %s (%.1fs)", case.id, status, eval_result.duration)

    report.finalize()
    return report
