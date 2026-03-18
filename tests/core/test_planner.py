from __future__ import annotations

from omni_agent.core.planner import Plan, PlanStatus, PlanStep


class TestPlan:
    def test_create_basic(self):
        plan = Plan(
            task_summary="Build auth module",
            steps=[
                PlanStep(description="Create models"),
                PlanStep(description="Add routes"),
                PlanStep(description="Write tests"),
            ],
        )
        assert plan.status == PlanStatus.DRAFT
        assert plan.progress == 0.0
        assert plan.current_step_index == 0

    def test_mark_step_done(self):
        plan = Plan(
            task_summary="Test",
            steps=[
                PlanStep(description="Step 1"),
                PlanStep(description="Step 2"),
            ],
        )
        plan.mark_step_done(0)
        assert plan.steps[0].done is True
        assert plan.progress == 0.5
        assert plan.current_step_index == 1

    def test_auto_complete(self):
        plan = Plan(
            task_summary="Test",
            steps=[PlanStep(description="Only step")],
        )
        plan.mark_step_done(0)
        assert plan.status == PlanStatus.COMPLETED
        assert plan.current_step_index is None

    def test_approve_and_start(self):
        plan = Plan(
            task_summary="Test",
            steps=[PlanStep(description="Step 1")],
        )
        plan.approve()
        assert plan.status == PlanStatus.APPROVED
        plan.start()
        assert plan.status == PlanStatus.IN_PROGRESS

    def test_to_markdown_and_back(self):
        plan = Plan(
            task_summary="Refactor utils",
            steps=[
                PlanStep(description="Extract helpers", done=True),
                PlanStep(description="Update imports"),
            ],
            constraints=["No breaking changes"],
            done_when=["All tests pass"],
            status=PlanStatus.IN_PROGRESS,
        )
        md = plan.to_markdown()
        restored = Plan.from_markdown(md)

        assert restored.task_summary == "Refactor utils"
        assert len(restored.steps) == 2
        assert restored.steps[0].done is True
        assert restored.steps[1].done is False
        assert restored.constraints == ["No breaking changes"]
        assert restored.done_when == ["All tests pass"]
        assert restored.status == PlanStatus.IN_PROGRESS

    def test_save_and_load(self, tmp_path):
        plan = Plan(
            task_summary="Save test",
            steps=[PlanStep(description="Do something")],
        )
        plan.save(tmp_path)
        assert (tmp_path / ".agent" / "plan.md").exists()

        loaded = Plan.load(tmp_path)
        assert loaded is not None
        assert loaded.task_summary == "Save test"
        assert len(loaded.steps) == 1

    def test_load_nonexistent(self, tmp_path):
        result = Plan.load(tmp_path)
        assert result is None

    def test_progress_empty_steps(self):
        plan = Plan(task_summary="Empty", steps=[])
        assert plan.progress == 0.0
