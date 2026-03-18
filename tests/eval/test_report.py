from __future__ import annotations

import pytest

from omni_agent.eval.grader import GradeResult
from omni_agent.eval.report import EvalReport, EvalResult


class TestEvalResult:
    def test_passed_when_grade_passes(self):
        r = EvalResult(case_id="t1", grade=GradeResult.success())
        assert r.passed is True

    def test_failed_when_grade_fails(self):
        r = EvalResult(case_id="t1", grade=GradeResult.failure("bad"))
        assert r.passed is False

    def test_failed_when_error(self):
        r = EvalResult(
            case_id="t1",
            grade=GradeResult.success(),
            error="timeout",
        )
        assert r.passed is False

    def test_to_dict(self):
        r = EvalResult(
            case_id="t1",
            grade=GradeResult.success(reason="ok"),
            duration=1.5,
            steps=3,
            input_tokens=100,
            output_tokens=50,
        )
        d = r.to_dict()
        assert d["case_id"] == "t1"
        assert d["passed"] is True
        assert d["duration"] == 1.5


class TestEvalReport:
    def test_empty_report(self):
        report = EvalReport()
        assert report.total == 0
        assert report.accuracy == 0.0

    def test_accuracy(self):
        report = EvalReport()
        report.add(EvalResult(case_id="t1", grade=GradeResult.success()))
        report.add(EvalResult(case_id="t2", grade=GradeResult.failure("bad")))
        report.add(EvalResult(case_id="t3", grade=GradeResult.success()))
        assert report.total == 3
        assert report.passed == 2
        assert report.failed == 1
        assert report.accuracy == pytest.approx(2 / 3)

    def test_summary(self):
        report = EvalReport(dataset_name="test")
        report.add(EvalResult(case_id="t1", grade=GradeResult.success(), duration=2.0, steps=3))
        report.finalize()
        s = report.summary()
        assert s["dataset"] == "test"
        assert s["total"] == 1
        assert s["passed"] == 1

    def test_to_terminal(self):
        report = EvalReport(dataset_name="test")
        report.add(EvalResult(case_id="t1", grade=GradeResult.success()))
        report.finalize()
        output = report.to_terminal()
        assert "PASS" in output
        assert "t1" in output

    def test_save_json(self, tmp_path):
        report = EvalReport(dataset_name="test")
        report.add(EvalResult(case_id="t1", grade=GradeResult.success()))
        report.finalize()
        path = tmp_path / "report.json"
        report.save_json(path)
        assert path.exists()
        import json

        data = json.loads(path.read_text())
        assert data["summary"]["total"] == 1
