from __future__ import annotations

import pytest

from omni_agent.eval.isolation import IsolatedWorkspace


class TestIsolatedWorkspace:
    async def test_creates_files(self):
        setup = {
            "files": {
                "app.py": "print('hello')",
                "utils/helper.py": "def help(): pass",
            }
        }
        async with IsolatedWorkspace(setup) as ws:
            assert (ws.path / "app.py").exists()
            assert (ws.path / "app.py").read_text() == "print('hello')"
            assert (ws.path / "utils" / "helper.py").exists()

    async def test_creates_dirs(self):
        setup = {"dirs": ["output", "logs/daily"]}
        async with IsolatedWorkspace(setup) as ws:
            assert (ws.path / "output").is_dir()
            assert (ws.path / "logs" / "daily").is_dir()

    async def test_cleanup_on_exit(self):
        setup = {"files": {"test.txt": "data"}}
        async with IsolatedWorkspace(setup) as ws:
            path = ws.path
            assert path.exists()
        assert not path.exists()

    async def test_empty_setup(self):
        async with IsolatedWorkspace({}) as ws:
            assert ws.path.exists()
            assert ws.path.is_dir()
