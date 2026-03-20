"""GAIA (General AI Assistants) benchmark adapter.

Loads GAIA validation questions from HuggingFace and evaluates the agent's
ability to answer real-world questions using tools.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omni_agent.eval.grader import GradeResult
from omni_agent.eval.report import EvalReport, EvalResult

logger = logging.getLogger(__name__)


@dataclass
class GAIACase:
    task_id: str
    question: str
    level: int
    final_answer: str
    file_name: str = ""
    file_path: str = ""


@dataclass
class GAIAConfig:
    levels: list[int] = field(default_factory=lambda: [1])
    max_cases_per_level: int = 20
    max_steps: int = 15
    timeout: int = 120
    cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".omni-agent" / "benchmarks" / "gaia"
    )


def _load_gaia_dataset(config: GAIAConfig) -> list[GAIACase]:
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets library required: uv add datasets")
        return []

    cases: list[GAIACase] = []

    try:
        logger.info("Loading GAIA dataset from HuggingFace...")
        dataset = load_dataset("gaia-benchmark/GAIA", "2023_all")

        if "validation" not in dataset:
            logger.error("GAIA validation split not found. Available: %s", list(dataset.keys()))
            return []

        validation = dataset["validation"]
        logger.info("GAIA validation set: %d questions", len(validation))

        for row in validation:
            level = int(row.get("Level", row.get("level", 1)))
            if level not in config.levels:
                continue

            if len([c for c in cases if c.level == level]) >= config.max_cases_per_level:
                continue

            cases.append(
                GAIACase(
                    task_id=row.get("task_id", ""),
                    question=row.get("Question", row.get("question", "")),
                    level=level,
                    final_answer=str(row.get("Final answer", row.get("final_answer", ""))),
                    file_name=row.get("file_name", "") or "",
                    file_path=row.get("file_path", "") or "",
                )
            )

    except Exception as e:
        logger.error("Failed to load GAIA dataset: %s", e)
        return []

    logger.info("Loaded %d GAIA cases across levels %s", len(cases), config.levels)
    return cases


def _normalize_str(s: str) -> str:
    import string

    s = re.sub(r"\s", "", s).lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    return s


def _normalize_number(s: str) -> float | None:
    s = s.replace("$", "").replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _is_number(s: str) -> bool:
    return _normalize_number(s) is not None


def _grade_gaia_answer(result: str, expected: str) -> GradeResult:
    if not expected:
        return GradeResult.failure(reason="no expected answer available")

    result = result.strip()
    expected = expected.strip()

    if _is_number(expected):
        result_num = _normalize_number(result)
        expected_num = _normalize_number(expected)
        if result_num is not None and expected_num is not None and result_num == expected_num:
            return GradeResult.success(reason=f"numeric match: {result_num}")
        numbers_in_result = re.findall(r"-?[\d,]+\.?\d*", result)
        for num_str in numbers_in_result:
            n = _normalize_number(num_str)
            if n is not None and n == expected_num:
                return GradeResult.success(reason=f"numeric found in text: {n}")
        return GradeResult.failure(
            reason=f"numeric mismatch: expected '{expected}', got '{result[:200]}'",
        )

    if "," in expected or ";" in expected:
        sep = "," if "," in expected else ";"
        expected_parts = [p.strip() for p in expected.split(sep)]
        result_parts = [p.strip() for p in result.split(sep)]
        if len(expected_parts) != len(result_parts):
            return GradeResult.failure(
                reason=f"list length mismatch: expected {len(expected_parts)}, got {len(result_parts)}",
            )
        all_match = True
        for ep, rp in zip(expected_parts, result_parts, strict=False):
            if _is_number(ep):
                en, rn = _normalize_number(ep), _normalize_number(rp)
                if en is None or rn is None or en != rn:
                    all_match = False
                    break
            elif _normalize_str(ep) != _normalize_str(rp):
                all_match = False
                break
        if all_match:
            return GradeResult.success(reason="list match")
        return GradeResult.failure(
            reason=f"list mismatch: expected '{expected}', got '{result[:200]}'",
        )

    if _normalize_str(expected) == _normalize_str(result):
        return GradeResult.success(reason="exact string match")

    if _normalize_str(expected) in _normalize_str(result):
        return GradeResult.success(reason=f"answer contains expected: '{expected}'")

    return GradeResult.failure(
        reason=f"answer mismatch: expected '{expected}', got '{result[:200]}'",
    )


async def run_gaia(
    llm_client: Any,
    tools: list[Any] | None = None,
    config: GAIAConfig | None = None,
) -> EvalReport:
    from omni_agent.core.agent import Agent
    from omni_agent.eval.isolation import IsolatedWorkspace
    from omni_agent.eval.runner import _create_base_tools

    config = config or GAIAConfig()
    report = EvalReport(dataset_name="GAIA")

    if not tools:
        try:
            from omni_agent.tools.mcp_loader import load_mcp_tools_async

            mcp_tools = await load_mcp_tools_async()
            tools = mcp_tools
            logger.info("Loaded %d MCP tools for GAIA", len(mcp_tools))
        except Exception as e:
            logger.warning("Failed to load MCP tools: %s", e)

    cases = _load_gaia_dataset(config)
    if not cases:
        logger.error("No GAIA cases loaded")
        return report

    logger.info("Running GAIA benchmark: %d cases", len(cases))

    data_dir = Path(config.cache_dir / "data")
    needs_files = any(c.file_name and c.file_path for c in cases)
    if needs_files:
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id="gaia-benchmark/GAIA",
                repo_type="dataset",
                local_dir=str(data_dir),
            )
        except Exception as e:
            logger.warning("Could not download GAIA dataset: %s", e)

    for case in cases:
        start = time.time()
        try:
            setup: dict[str, Any] = {"files": {}, "dirs": []}

            if case.file_name and case.file_path:
                try:
                    src = data_dir / case.file_path
                    if src.exists():
                        setup["files"][case.file_name] = src.read_bytes()
                except Exception as e:
                    logger.warning("Could not load attachment for %s: %s", case.task_id, e)

            async with IsolatedWorkspace(setup) as workspace:
                ws_tools = _create_base_tools(str(workspace.path))
                if tools:
                    ws_tools.extend(tools)

                task_prompt = (
                    f"{case.question}\n\n"
                    "IMPORTANT: Your final response must contain ONLY the answer, "
                    "as concisely as possible. No explanation needed."
                )

                if case.file_name:
                    task_prompt += f"\n\nA file '{case.file_name}' is available in your workspace."

                agent = Agent(
                    llm_client=llm_client,
                    tools=ws_tools,
                    max_steps=config.max_steps,
                    workspace_dir=str(workspace.path),
                    enable_logging=False,
                )
                agent.add_user_message(task_prompt)

                result_text, logs = await asyncio.wait_for(
                    agent.run(),
                    timeout=config.timeout,
                )

                grade = _grade_gaia_answer(result_text, case.final_answer)

                steps = len(logs) if logs else 0
                input_tokens = sum(
                    log.get("input_tokens", 0) for log in logs if isinstance(log, dict)
                )
                output_tokens = sum(
                    log.get("output_tokens", 0) for log in logs if isinstance(log, dict)
                )

                eval_result = EvalResult(
                    case_id=f"gaia_L{case.level}_{case.task_id[:8]}",
                    grade=grade,
                    duration=time.time() - start,
                    steps=steps,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

        except TimeoutError:
            eval_result = EvalResult(
                case_id=f"gaia_L{case.level}_{case.task_id[:8]}",
                grade=GradeResult.failure(reason="timeout"),
                duration=time.time() - start,
                error=f"exceeded {config.timeout}s timeout",
            )
        except Exception as e:
            logger.exception("GAIA case %s failed", case.task_id)
            eval_result = EvalResult(
                case_id=f"gaia_L{case.level}_{case.task_id[:8]}",
                grade=GradeResult.failure(reason=str(e)),
                duration=time.time() - start,
                error=str(e),
            )

        report.add(eval_result)
        status = "PASS" if eval_result.passed else "FAIL"
        logger.info(
            "GAIA L%d %s: %s (%.1fs)",
            case.level,
            case.task_id[:8],
            status,
            eval_result.duration,
        )

    try:
        from omni_agent.tools.mcp_loader import cleanup_mcp_connections

        await cleanup_mcp_connections()
    except Exception:
        pass

    report.finalize()
    return report
