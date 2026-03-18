from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalConfig:
    parallel: int = 3
    default_timeout: int = 60
    default_max_steps: int = 10
    llm_judge_model: str = ""
    output_dir: Path = field(default_factory=lambda: Path("eval_results"))
    verbose: bool = False

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
