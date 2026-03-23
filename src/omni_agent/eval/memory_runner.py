from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from omni_agent.eval.config import EvalConfig
from omni_agent.eval.dataset import EvalCase
from omni_agent.eval.grader import BaseGrader, GradeResult, LLMGrader
from omni_agent.eval.isolation import IsolatedWorkspace
from omni_agent.eval.memory_grader import FactRetentionGrader
from omni_agent.eval.report import EvalReport, EvalResult
from omni_agent.eval.runner import _create_base_tools
from omni_agent.schemas.message import Message

logger = logging.getLogger(__name__)


@dataclass
class MemoryEvalCase:
    base: EvalCase
    conversation: list[dict[str, str]]
    injected_facts: list[str]
    query: str
    test_level: str = "L1"
    compression_trigger: str = "rounds"


class MemoryEvalDataset:
    def __init__(self, cases: list[MemoryEvalCase], name: str = "") -> None:
        self.cases = cases
        self.name = name

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.cases)

    @classmethod
    def from_yaml(cls, path: Path) -> MemoryEvalDataset:
        with open(path) as f:
            raw = yaml.safe_load(f)

        cases_data = raw if isinstance(raw, list) else raw.get("cases", [])
        cases = [cls._parse_case(c) for c in cases_data]
        return cls(cases=cases, name=path.stem)

    @classmethod
    def from_directory(cls, directory: Path) -> MemoryEvalDataset:
        all_cases: list[MemoryEvalCase] = []
        for yaml_file in sorted(directory.rglob("*.yaml")):
            ds = cls.from_yaml(yaml_file)
            all_cases.extend(ds.cases)
        for yml_file in sorted(directory.rglob("*.yml")):
            ds = cls.from_yaml(yml_file)
            all_cases.extend(ds.cases)
        return cls(cases=all_cases, name=directory.name)

    @classmethod
    def _parse_case(cls, data: dict[str, Any]) -> MemoryEvalCase:
        base = EvalCase(
            id=data["id"],
            task=data.get("task", data.get("query", "")),
            setup=data.get("setup", {}),
            grading=data.get("grading", {}),
            max_steps=data.get("max_steps", 10),
            timeout=data.get("timeout", 120),
            tags=data.get("tags", []),
        )
        return MemoryEvalCase(
            base=base,
            conversation=data.get("conversation", []),
            injected_facts=data.get("injected_facts", []),
            query=data.get("query", ""),
            test_level=data.get("test_level", "L1"),
            compression_trigger=data.get("compression_trigger", "rounds"),
        )

    def filter_by_tags(self, tags: list[str]) -> MemoryEvalDataset:
        tag_set = set(tags)
        filtered = [c for c in self.cases if tag_set.intersection(c.base.tags)]
        return MemoryEvalDataset(cases=filtered, name=f"{self.name}[{','.join(tags)}]")


class MemoryEvalRunner:
    def __init__(
        self,
        llm_client: Any,
        config: EvalConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._config = config or EvalConfig()

    async def run_case(self, case: MemoryEvalCase) -> EvalResult:
        if case.test_level == "L1":
            return await self._run_l1(case)
        return await self._run_l2(case)

    async def _run_l1(self, case: MemoryEvalCase) -> EvalResult:
        start = time.time()
        try:
            from omni_agent.core.token_manager import TokenManager

            messages = [Message(role="system", content="You are a helpful assistant.")]
            for turn in case.conversation:
                messages.append(Message(role=turn["role"], content=turn["content"]))

            token_manager = TokenManager(
                llm_client=self._llm,
                token_limit=50000,
                summarize_after_rounds=2,
            )

            compressed = await token_manager.maybe_summarize_messages(messages)

            core_memory = token_manager.core_memory
            if not core_memory:
                core_memory = "\n".join(m.content for m in compressed if isinstance(m.content, str))

            grader = self._select_grader(case)
            grade = await grader.grade(case.base, Path(), core_memory)

            return EvalResult(
                case_id=case.base.id,
                grade=grade,
                duration=time.time() - start,
                steps=0,
            )

        except Exception as e:
            logger.exception("memory eval case %s (L1) failed", case.base.id)
            return EvalResult(
                case_id=case.base.id,
                grade=GradeResult.failure(reason=str(e)),
                duration=time.time() - start,
                error=str(e),
            )

    async def _run_l2(self, case: MemoryEvalCase) -> EvalResult:
        start = time.time()
        timeout = case.base.timeout or self._config.default_timeout
        max_steps = case.base.max_steps or self._config.default_max_steps

        try:
            from omni_agent.core.agent import Agent

            async with IsolatedWorkspace(case.base.setup) as workspace:
                tools = _create_base_tools(str(workspace.path))

                agent = Agent(
                    llm_client=self._llm,
                    tools=tools,
                    max_steps=max_steps,
                    workspace_dir=str(workspace.path),
                    enable_logging=False,
                    system_prompt=(
                        "你是一个有记忆能力的助手。你和用户之前有过对话，"
                        "对话历史已经被压缩为核心记忆注入到上下文中。"
                        "请基于核心记忆和上下文中的信息直接回答用户的问题。"
                        "优先使用你已有的对话记忆来回答，"
                        "只有在记忆中确实没有相关信息时才使用工具。"
                        "回答时请尽量详细地列出你记忆中的关键事实和数据。"
                    ),
                )

                for turn in case.conversation:
                    agent._state.messages.append(
                        Message(role=turn["role"], content=turn["content"])
                    )

                agent.token_manager.summarize_after_rounds = 2
                agent._state.messages = await agent.token_manager.maybe_summarize_messages(
                    agent._state.messages
                )

                agent.add_user_message(case.query)

                result_text, logs = await asyncio.wait_for(
                    agent.run(),
                    timeout=timeout,
                )

                grader = self._select_grader(case)
                grade = await grader.grade(case.base, workspace.path, result_text)

                return EvalResult(
                    case_id=case.base.id,
                    grade=grade,
                    duration=time.time() - start,
                    steps=len(logs) if logs else 0,
                )

        except TimeoutError:
            return EvalResult(
                case_id=case.base.id,
                grade=GradeResult.failure(reason="timeout"),
                duration=time.time() - start,
                error=f"exceeded {timeout}s timeout",
            )
        except Exception as e:
            logger.exception("memory eval case %s (L2) failed", case.base.id)
            return EvalResult(
                case_id=case.base.id,
                grade=GradeResult.failure(reason=str(e)),
                duration=time.time() - start,
                error=str(e),
            )

    def _select_grader(self, case: MemoryEvalCase) -> BaseGrader:
        grading_type = case.base.grading.get("type", "memory")
        if grading_type == "llm":
            return LLMGrader(self._llm)
        return FactRetentionGrader()

    async def run_dataset(self, dataset: MemoryEvalDataset) -> EvalReport:
        report = EvalReport(dataset_name=dataset.name)
        semaphore = asyncio.Semaphore(self._config.parallel)

        async def run_with_semaphore(case: MemoryEvalCase) -> EvalResult:
            async with semaphore:
                logger.info("running memory eval case: %s", case.base.id)
                result = await self.run_case(case)
                status = "PASS" if result.passed else "FAIL"
                logger.info(
                    "memory eval case %s: %s (%.1fs)",
                    case.base.id,
                    status,
                    result.duration,
                )
                return result

        tasks = [run_with_semaphore(case) for case in dataset]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for result in results:
            report.add(result)

        report.finalize()
        return report
