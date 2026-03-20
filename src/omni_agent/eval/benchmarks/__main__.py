"""Benchmark runner CLI.

Usage:
    uv run python -m omni_agent.eval.benchmarks bfcl --categories simple --max-cases 20
    uv run python -m omni_agent.eval.benchmarks gaia --levels 1 --max-cases 10
    uv run python -m omni_agent.eval.benchmarks all
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="External Benchmark Runner (BFCL / GAIA)",
        prog="python -m omni_agent.eval.benchmarks",
    )
    parser.add_argument(
        "benchmark",
        choices=["bfcl", "gaia", "all"],
        help="which benchmark to run",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="simple",
        help="BFCL categories, comma-separated (default: simple)",
    )
    parser.add_argument(
        "--levels",
        type=str,
        default="1",
        help="GAIA difficulty levels, comma-separated (default: 1)",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=20,
        help="max cases per category/level (default: 20)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="max agent steps per GAIA case (default: 15)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="timeout per GAIA case in seconds (default: 120)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval_results"),
        help="output directory (default: eval_results)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="verbose logging",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="enable thinking/reasoning mode",
    )
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=8000,
        help="thinking budget tokens (default: 8000)",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from omni_agent.core.config import settings
    from omni_agent.core.llm_client import LLMClient

    llm_client = LLMClient(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        api_base=settings.LLM_API_BASE or None,
        thinking=args.thinking,
        thinking_budget=args.thinking_budget,
    )

    args.output.mkdir(parents=True, exist_ok=True)

    reports = []

    if args.benchmark in ("bfcl", "all"):
        from omni_agent.eval.benchmarks.bfcl import BFCLConfig, run_bfcl

        bfcl_config = BFCLConfig(
            categories=args.categories.split(","),
            max_cases_per_category=args.max_cases,
        )
        print(
            f"Running BFCL benchmark: categories={bfcl_config.categories}, max={bfcl_config.max_cases_per_category}"
        )
        report = await run_bfcl(llm_client, bfcl_config)
        print(report.to_terminal())
        report.save_json(args.output / "benchmark_bfcl_latest.json")
        reports.append(report)

    if args.benchmark in ("gaia", "all"):
        from omni_agent.eval.benchmarks.gaia import GAIAConfig, run_gaia

        gaia_config = GAIAConfig(
            levels=[int(x) for x in args.levels.split(",")],
            max_cases_per_level=args.max_cases,
            max_steps=args.max_steps,
            timeout=args.timeout,
        )
        print(
            f"Running GAIA benchmark: levels={gaia_config.levels}, max={gaia_config.max_cases_per_level}"
        )
        report = await run_gaia(llm_client, config=gaia_config)
        print(report.to_terminal())
        report.save_json(args.output / "benchmark_gaia_latest.json")
        reports.append(report)

    total_passed = sum(r.passed for r in reports)
    total_cases = sum(r.total for r in reports)

    if total_cases > 0:
        print(f"\nOverall: {total_passed}/{total_cases} ({total_passed / total_cases:.1%})")

    return 0 if all(r.failed == 0 for r in reports) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
