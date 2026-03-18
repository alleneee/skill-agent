from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EvalCase:
    id: str
    task: str
    setup: dict[str, Any] = field(default_factory=dict)
    grading: dict[str, Any] = field(default_factory=dict)
    max_steps: int = 10
    timeout: int = 60
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalCase:
        return cls(
            id=data["id"],
            task=data["task"],
            setup=data.get("setup", {}),
            grading=data.get("grading", {}),
            max_steps=data.get("max_steps", 10),
            timeout=data.get("timeout", 60),
            tags=data.get("tags", []),
        )


class EvalDataset:
    def __init__(self, cases: list[EvalCase], name: str = "") -> None:
        self.cases = cases
        self.name = name

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.cases)

    @classmethod
    def from_yaml(cls, path: Path) -> EvalDataset:
        with open(path) as f:
            raw = yaml.safe_load(f)

        cases_data = raw if isinstance(raw, list) else raw.get("cases", [])
        cases = [EvalCase.from_dict(c) for c in cases_data]
        return cls(cases=cases, name=path.stem)

    @classmethod
    def from_directory(cls, directory: Path) -> EvalDataset:
        all_cases: list[EvalCase] = []
        for yaml_file in sorted(directory.rglob("*.yaml")):
            ds = cls.from_yaml(yaml_file)
            all_cases.extend(ds.cases)
        for yml_file in sorted(directory.rglob("*.yml")):
            ds = cls.from_yaml(yml_file)
            all_cases.extend(ds.cases)
        return cls(cases=all_cases, name=directory.name)

    def filter_by_tags(self, tags: list[str]) -> EvalDataset:
        tag_set = set(tags)
        filtered = [c for c in self.cases if tag_set.intersection(c.tags)]
        return EvalDataset(cases=filtered, name=f"{self.name}[{','.join(tags)}]")

    def filter_by_ids(self, ids: list[str]) -> EvalDataset:
        id_set = set(ids)
        filtered = [c for c in self.cases if c.id in id_set]
        return EvalDataset(cases=filtered, name=f"{self.name}[ids]")
