from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from omni_agent.eval.config import EvalConfig
from omni_agent.eval.dataset import EvalCase, EvalDataset
from omni_agent.eval.grader import BaseGrader, GradeResult, OutcomeGrader
from omni_agent.eval.isolation import IsolatedWorkspace
from omni_agent.eval.report import EvalReport, EvalResult

logger = logging.getLogger(__name__)


def _create_base_tools(workspace_dir: str) -> list[Any]:
    from omni_agent.tools.bash_tool import BashTool
    from omni_agent.tools.file_tools import EditTool, ReadTool, WriteTool

    return [
        ReadTool(workspace_dir=workspace_dir),
        WriteTool(workspace_dir=workspace_dir),
        EditTool(workspace_dir=workspace_dir),
        BashTool(),
    ]


class EvalRunner:
    def __init__(
        self,
        llm_client: Any,
        tools: list[Any] | None = None,
        config: EvalConfig | None = None,
        grader: BaseGrader | None = None,
    ) -> None:
        self._llm = llm_client
        self._extra_tools = tools or []
        self._config = config or EvalConfig()
        self._grader = grader or OutcomeGrader()

    async def run_case(self, case: EvalCase) -> EvalResult:
        timeout = case.timeout or self._config.default_timeout
        max_steps = case.max_steps or self._config.default_max_steps
        start = time.time()

        try:
            async with IsolatedWorkspace(case.setup) as workspace:
                from omni_agent.core.agent import Agent

                ws_tools = _create_base_tools(str(workspace.path))
                ws_tools.extend(self._extra_tools)

                agent = Agent(
                    llm_client=self._llm,
                    tools=ws_tools,
                    max_steps=max_steps,
                    workspace_dir=str(workspace.path),
                    enable_logging=False,
                )
                agent.add_user_message(case.task)

                result_text, logs = await asyncio.wait_for(
                    agent.run(),
                    timeout=timeout,
                )

                grade = await self._grader.grade(case, workspace.path, result_text)

                steps = self._extract_steps(logs)
                input_tokens, output_tokens = self._extract_tokens(logs)

                return EvalResult(
                    case_id=case.id,
                    grade=grade,
                    duration=time.time() - start,
                    steps=steps,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

        except asyncio.TimeoutError:
            return EvalResult(
                case_id=case.id,
                grade=GradeResult.failure(reason="timeout"),
                duration=time.time() - start,
                error=f"exceeded {timeout}s timeout",
            )
        except Exception as e:
            logger.exception("eval case %s failed", case.id)
            return EvalResult(
                case_id=case.id,
                grade=GradeResult.failure(reason=str(e)),
                duration=time.time() - start,
                error=str(e),
            )

    async def run_dataset(self, dataset: EvalDataset) -> EvalReport:
        report = EvalReport(dataset_name=dataset.name)
        semaphore = asyncio.Semaphore(self._config.parallel)

        async def run_with_semaphore(case: EvalCase) -> EvalResult:
            async with semaphore:
                logger.info("running eval case: %s", case.id)
                result = await self.run_case(case)
                status = "PASS" if result.passed else "FAIL"
                logger.info(
                    "eval case %s: %s (%.1fs)",
                    case.id, status, result.duration,
                )
                return result

        tasks = [run_with_semaphore(case) for case in dataset]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for result in results:
            report.add(result)

        report.finalize()
        return report

    def _extract_steps(self, logs: list[Any]) -> int:
        if not logs:
            return 0
        return len(logs)

    def _extract_tokens(self, logs: list[Any]) -> tuple[int, int]:
        input_tokens = 0
        output_tokens = 0
        for log_entry in logs:
            if isinstance(log_entry, dict):
                input_tokens += log_entry.get("input_tokens", 0)
                output_tokens += log_entry.get("output_tokens", 0)
        return input_tokens, output_tokens
