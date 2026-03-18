from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


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
        "--verbose", "-v",
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


async def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from omni_agent.eval.config import EvalConfig
    from omni_agent.eval.dataset import EvalDataset

    path: Path = args.path
    if path.is_file():
        dataset = EvalDataset.from_yaml(path)
    elif path.is_dir():
        dataset = EvalDataset.from_directory(path)
    else:
        print(f"Error: {path} not found")
        return 1

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

    config = EvalConfig(
        parallel=args.parallel,
        default_timeout=args.timeout,
        default_max_steps=args.max_steps,
        output_dir=args.output,
        verbose=args.verbose,
    )

    from omni_agent.core.config import settings
    from omni_agent.core.llm_client import LLMClient
    from omni_agent.eval.runner import EvalRunner

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        api_base=settings.LLM_API_BASE or None,
    )

    runner = EvalRunner(
        llm_client=llm_client,
        config=config,
    )

    report = await runner.run_dataset(dataset)

    print(report.to_terminal())

    import datetime

    from omni_agent.eval.report import EvalReport

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = config.output_dir / f"eval_{dataset.name}_{timestamp}.json"
    report.save_json(report_path)
    print(f"Report saved to {report_path}")

    if args.compare and args.compare.exists():
        print(EvalReport.compare(report_path, args.compare))

    latest_link = config.output_dir / f"eval_{dataset.name}_latest.json"
    report.save_json(latest_link)

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
