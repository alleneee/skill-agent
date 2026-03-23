from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from omni_agent.eval.config import EvalConfig
from omni_agent.eval.report import EvalReport


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Omni Agent Evaluation Runner",
        prog="python -m omni_agent.eval",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="path to eval directory or YAML file",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="default timeout per case in seconds (default: 60)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="default max steps per case (default: 10)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=3,
        help="max parallel eval cases (default: 3)",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default="",
        help="comma-separated tags to filter cases",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval_results"),
        help="output directory for reports (default: eval_results)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="verbose logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list cases without running",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="path to previous eval report JSON for comparison",
    )
    return parser.parse_args()


def _is_memory_eval(path: Path) -> bool:
    yaml_files = (
        sorted(list(path.rglob("*.yaml")) + list(path.rglob("*.yml"))) if path.is_dir() else [path]
    )
    for f in yaml_files:
        try:
            head = f.read_text(errors="ignore")[:2000]
            if "conversation:" in head:
                return True
        except Exception:
            continue
    return False


async def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    path: Path = args.path
    if not path.exists():
        print(f"Error: {path} not found")
        return 1

    is_memory = _is_memory_eval(path)

    config = EvalConfig(
        parallel=args.parallel,
        default_timeout=args.timeout,
        default_max_steps=args.max_steps,
        output_dir=args.output,
        verbose=args.verbose,
    )

    if args.dry_run:
        if is_memory:
            return await _run_memory_eval(path, args, config, llm_client=None)
        return await _run_standard_eval(path, args, config, llm_client=None)

    from omni_agent.core.config import settings
    from omni_agent.core.llm_client import LLMClient

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        api_base=settings.LLM_API_BASE or None,
    )

    if is_memory:
        return await _run_memory_eval(path, args, config, llm_client)
    return await _run_standard_eval(path, args, config, llm_client)


async def _run_memory_eval(
    path: Path, args: argparse.Namespace, config: EvalConfig, llm_client: Any
) -> int:
    from omni_agent.eval.memory_runner import MemoryEvalDataset, MemoryEvalRunner

    dataset = (
        MemoryEvalDataset.from_yaml(path)
        if path.is_file()
        else MemoryEvalDataset.from_directory(path)
    )

    if args.tags:
        dataset = dataset.filter_by_tags(args.tags.split(","))

    if not dataset.cases:
        print("No memory eval cases found.")
        return 1

    print(f"Loaded {len(dataset)} memory eval cases from {dataset.name}")

    if args.dry_run:
        for case in dataset:
            tags = f" [{', '.join(case.base.tags)}]" if case.base.tags else ""
            print(f"  - {case.base.id} [{case.test_level}]: {case.query[:60]}...{tags}")
        return 0

    runner = MemoryEvalRunner(llm_client=llm_client, config=config)
    report = await runner.run_dataset(dataset)

    return _output_report(report, dataset.name, config, args)


async def _run_standard_eval(
    path: Path, args: argparse.Namespace, config: EvalConfig, llm_client: Any
) -> int:
    from omni_agent.eval.dataset import EvalDataset

    dataset = EvalDataset.from_yaml(path) if path.is_file() else EvalDataset.from_directory(path)

    if args.tags:
        dataset = dataset.filter_by_tags(args.tags.split(","))

    if not dataset.cases:
        print("No eval cases found.")
        return 1

    print(f"Loaded {len(dataset)} eval cases from {dataset.name}")

    if args.dry_run:
        for case in dataset:
            tags = f" [{', '.join(case.tags)}]" if case.tags else ""
            print(f"  - {case.id}: {case.task[:60]}...{tags}")
        return 0

    from omni_agent.eval.runner import EvalRunner

    runner = EvalRunner(llm_client=llm_client, config=config)
    report = await runner.run_dataset(dataset)

    return _output_report(report, dataset.name, config, args)


def _output_report(
    report: EvalReport, dataset_name: str, config: EvalConfig, args: argparse.Namespace
) -> int:
    import datetime

    print(report.to_terminal())

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = config.output_dir / f"eval_{dataset_name}_{timestamp}.json"
    report.save_json(report_path)
    print(f"Report saved to {report_path}")

    if args.compare and args.compare.exists():
        print(EvalReport.compare(report_path, args.compare))

    latest_link = config.output_dir / f"eval_{dataset_name}_latest.json"
    report.save_json(latest_link)

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
