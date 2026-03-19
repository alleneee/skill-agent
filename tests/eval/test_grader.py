from __future__ import annotations

import pytest

from omni_agent.eval.dataset import EvalCase
from omni_agent.eval.grader import GradeResult, OutcomeGrader


class TestGradeResult:
    def test_success(self):
        r = GradeResult.success(reason="ok", extra="info")
        assert r.passed is True
        assert r.score == 1.0
        assert r.details == {"extra": "info"}

    def test_failure(self):
        r = GradeResult.failure(reason="bad", missing="data")
        assert r.passed is False
        assert r.score == 0.0
        assert r.details == {"missing": "data"}


class TestOutcomeGrader:
    @pytest.fixture
    def grader(self):
        return OutcomeGrader()

    async def test_no_checks(self, grader, tmp_path):
        case = EvalCase(id="t", task="t", grading={})
        result = await grader.grade(case, tmp_path, "output")
        assert result.passed is True

    async def test_file_exists_pass(self, grader, tmp_path):
        (tmp_path / "hello.py").write_text("pass")
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_exists": "hello.py"}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is True

    async def test_file_exists_fail(self, grader, tmp_path):
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_exists": "missing.py"}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is False

    async def test_file_contains_pass(self, grader, tmp_path):
        (tmp_path / "app.py").write_text("def hello():\n    return 'world'")
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_contains": ["app.py", "def hello"]}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is True

    async def test_file_contains_fail(self, grader, tmp_path):
        (tmp_path / "app.py").write_text("def goodbye():\n    pass")
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_contains": ["app.py", "def hello"]}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is False

    async def test_file_not_contains_pass(self, grader, tmp_path):
        (tmp_path / "cfg.py").write_text("DEBUG = True")
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_not_contains": ["cfg.py", "DEBUG = False"]}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is True

    async def test_result_contains_pass(self, grader, tmp_path):
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"result_contains": "success"}]},
        )
        result = await grader.grade(case, tmp_path, "operation success done")
        assert result.passed is True

    async def test_result_matches_pass(self, grader, tmp_path):
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"result_matches": r"\d+ files?"}]},
        )
        result = await grader.grade(case, tmp_path, "found 3 files")
        assert result.passed is True

    async def test_file_matches_pass(self, grader, tmp_path):
        (tmp_path / "report.txt").write_text("Found SQL injection vulnerability in line 5")
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_matches": ["report.txt", "(?i)sql.?inject"]}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is True

    async def test_file_matches_fail(self, grader, tmp_path):
        (tmp_path / "report.txt").write_text("No issues found")
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_matches": ["report.txt", "(?i)sql.?inject"]}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is False

    async def test_file_matches_missing_file(self, grader, tmp_path):
        case = EvalCase(
            id="t",
            task="t",
            grading={"checks": [{"file_matches": ["missing.txt", "pattern"]}]},
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is False

    async def test_multiple_checks_all_pass(self, grader, tmp_path):
        (tmp_path / "out.txt").write_text("hello world")
        case = EvalCase(
            id="t",
            task="t",
            grading={
                "checks": [
                    {"file_exists": "out.txt"},
                    {"file_contains": ["out.txt", "hello"]},
                    {"result_contains": "done"},
                ],
            },
        )
        result = await grader.grade(case, tmp_path, "done")
        assert result.passed is True

    async def test_multiple_checks_partial_fail(self, grader, tmp_path):
        (tmp_path / "out.txt").write_text("hello world")
        case = EvalCase(
            id="t",
            task="t",
            grading={
                "checks": [
                    {"file_exists": "out.txt"},
                    {"file_contains": ["out.txt", "goodbye"]},
                ],
            },
        )
        result = await grader.grade(case, tmp_path, "")
        assert result.passed is False
        assert result.details["failed_checks"] == 1
