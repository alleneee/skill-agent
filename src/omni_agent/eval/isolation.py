from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any


class IsolatedWorkspace:
    def __init__(self, setup: dict[str, Any]) -> None:
        self._setup = setup
        self._tmpdir: str = ""
        self.path: Path = Path()

    async def __aenter__(self) -> IsolatedWorkspace:
        self._tmpdir = tempfile.mkdtemp(prefix="eval_")
        self.path = Path(self._tmpdir)
        self._apply_setup()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._tmpdir and Path(self._tmpdir).exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _apply_setup(self) -> None:
        files = self._setup.get("files", {})
        for filepath, content in files.items():
            target = self.path / filepath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

        dirs = self._setup.get("dirs", [])
        for d in dirs:
            (self.path / d).mkdir(parents=True, exist_ok=True)
