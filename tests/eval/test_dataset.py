from __future__ import annotations

from omni_agent.eval.dataset import EvalCase, EvalDataset


class TestEvalCase:
    def test_from_dict_minimal(self):
        data = {"id": "test_001", "task": "do something"}
        case = EvalCase.from_dict(data)
        assert case.id == "test_001"
        assert case.task == "do something"
        assert case.max_steps == 10
        assert case.timeout == 60
        assert case.tags == []
        assert case.setup == {}
        assert case.grading == {}

    def test_from_dict_full(self):
        data = {
            "id": "test_002",
            "task": "edit a file",
            "setup": {"files": {"a.py": "print('hi')"}},
            "grading": {"type": "outcome", "checks": [{"file_exists": "a.py"}]},
            "max_steps": 5,
            "timeout": 30,
            "tags": ["tool", "quick"],
        }
        case = EvalCase.from_dict(data)
        assert case.id == "test_002"
        assert case.max_steps == 5
        assert case.tags == ["tool", "quick"]
        assert "files" in case.setup


class TestEvalDataset:
    def test_from_yaml(self, tmp_path):
        yaml_content = """
- id: "case_001"
  task: "hello"
  tags: ["a"]
- id: "case_002"
  task: "world"
  tags: ["b"]
"""
        yaml_file = tmp_path / "cases.yaml"
        yaml_file.write_text(yaml_content)

        ds = EvalDataset.from_yaml(yaml_file)
        assert len(ds) == 2
        assert ds.cases[0].id == "case_001"
        assert ds.cases[1].id == "case_002"

    def test_from_directory(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()

        (tmp_path / "a.yaml").write_text('- id: "a1"\n  task: "task a"')
        (sub / "b.yaml").write_text('- id: "b1"\n  task: "task b"')

        ds = EvalDataset.from_directory(tmp_path)
        assert len(ds) == 2

    def test_filter_by_tags(self, tmp_path):
        yaml_content = """
- id: "c1"
  task: "t1"
  tags: ["fast"]
- id: "c2"
  task: "t2"
  tags: ["slow"]
- id: "c3"
  task: "t3"
  tags: ["fast", "slow"]
"""
        f = tmp_path / "cases.yaml"
        f.write_text(yaml_content)
        ds = EvalDataset.from_yaml(f)

        fast = ds.filter_by_tags(["fast"])
        assert len(fast) == 2
        assert {c.id for c in fast} == {"c1", "c3"}

    def test_filter_by_ids(self, tmp_path):
        yaml_content = """
- id: "c1"
  task: "t1"
- id: "c2"
  task: "t2"
- id: "c3"
  task: "t3"
"""
        f = tmp_path / "cases.yaml"
        f.write_text(yaml_content)
        ds = EvalDataset.from_yaml(f)

        filtered = ds.filter_by_ids(["c1", "c3"])
        assert len(filtered) == 2
