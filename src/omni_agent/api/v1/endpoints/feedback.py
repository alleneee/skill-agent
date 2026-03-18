"""Agent 反馈端点."""
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class FeedbackRequest(BaseModel):
    run_id: str = Field(..., description="Run ID to attach feedback to")
    type: str = Field(..., description="Feedback type: approve, reject, edit, rating")
    reason: str = Field(default="", description="Reason for feedback")
    data: dict[str, Any] = Field(default_factory=dict, description="Additional feedback data")
    rating: int | None = Field(default=None, ge=1, le=5, description="Optional 1-5 rating")


class FeedbackResponse(BaseModel):
    success: bool
    message: str
    regression_case_created: bool = False


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Submit feedback for a completed agent run.

    Feedback types:
    - approve: Mark run output as satisfactory
    - reject: Mark run output as unsatisfactory (auto-generates regression eval case)
    - edit: User manually corrected the output
    - rating: Numerical quality rating (1-5)
    """
    from pathlib import Path

    from omni_agent.core.feedback_hook import FeedbackHook, FeedbackType, UserFeedback

    valid_types = {t.value for t in FeedbackType}
    if request.type not in valid_types:
        return FeedbackResponse(
            success=False,
            message=f"Invalid feedback type. Must be one of: {valid_types}",
        )

    storage_dir = Path(".agent_feedback")
    hook = FeedbackHook(storage_dir=storage_dir)

    feedback_data = {**request.data}
    if request.reason:
        feedback_data["reason"] = request.reason
    if request.rating is not None:
        feedback_data["rating"] = request.rating

    feedback = UserFeedback(
        type=FeedbackType(request.type),
        run_id=request.run_id,
        data=feedback_data,
    )
    await hook.record(feedback)

    regression_created = False
    if request.type == "reject" and request.reason:
        import time

        import yaml

        regression_dir = storage_dir / "regression_cases"
        regression_dir.mkdir(parents=True, exist_ok=True)

        case = {
            "id": f"regression_{request.run_id}_{int(time.time())}",
            "task": request.data.get("original_task", ""),
            "tags": ["regression", "auto_generated", "from_feedback"],
            "max_steps": 10,
            "timeout": 60,
            "grading": {
                "type": "llm",
                "criteria": f"Previous attempt was rejected. Reason: {request.reason}",
                "dimensions": ["completeness", "correctness"],
            },
        }

        if case["task"]:
            case_file = regression_dir / f"{case['id']}.yaml"
            with open(case_file, "w") as f:
                yaml.dump([case], f, allow_unicode=True, default_flow_style=False)
            regression_created = True

    return FeedbackResponse(
        success=True,
        message=f"Feedback recorded: {request.type}",
        regression_case_created=regression_created,
    )


@router.get("/feedback/stats")
async def feedback_stats() -> dict[str, Any]:
    """Get feedback statistics."""
    import json
    from collections import Counter
    from pathlib import Path

    log_file = Path(".agent_feedback") / "feedback.jsonl"
    if not log_file.exists():
        return {"total": 0, "by_type": {}, "avg_rating": None}

    feedbacks = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if line:
                feedbacks.append(json.loads(line))

    type_counts = Counter(f["type"] for f in feedbacks)
    ratings = [f["data"]["rating"] for f in feedbacks if "rating" in f.get("data", {})]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    regression_dir = Path(".agent_feedback") / "regression_cases"
    regression_count = len(list(regression_dir.glob("*.yaml"))) if regression_dir.exists() else 0

    return {
        "total": len(feedbacks),
        "by_type": dict(type_counts),
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "regression_cases": regression_count,
    }
