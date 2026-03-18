"""追踪和运行日志查看端点。"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from omni_agent.core.config import settings
from omni_agent.core.run_log_storage import get_run_log_storage

router = APIRouter()

TRACE_DIR = Path.home() / ".omni-agents" / "traces"


class TraceListItem(BaseModel):
    """追踪列表项模型。"""

    filename: str
    trace_id: str
    trace_type: str
    duration_seconds: float
    total_events: int
    agent_count: int
    task_count: int
    total_tokens: int
    success: bool | None = None


class RunListItem(BaseModel):
    """运行记录列表项模型。"""

    run_id: str
    timestamp: str
    total_steps: int
    total_tool_calls: int
    total_events: int
    success: bool
    final_token_count: int


class TraceDetail(BaseModel):
    """追踪详情模型。"""

    summary: dict
    events: list[dict]


class RunDetail(BaseModel):
    """运行详情模型。"""

    run_id: str
    summary: dict
    events: list[dict]


@router.get("/runs/list")
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RunListItem]:
    """列出所有运行记录。"""
    storage = await get_run_log_storage()
    runs = await storage.list_runs(limit)
    return [RunListItem(**r) for r in runs]


@router.get("/runs/detail/{run_id}")
async def get_run_detail(run_id: str) -> RunDetail:
    """获取指定运行记录的详情。"""
    storage = await get_run_log_storage()
    events = await storage.get_events(run_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    summary = await storage.get_run_summary(run_id)
    return RunDetail(run_id=run_id, summary=summary or {}, events=events)


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict:
    """删除指定的运行记录。"""
    storage = await get_run_log_storage()
    deleted = await storage.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"deleted": True, "run_id": run_id}


@router.get("/list")
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    trace_type: str | None = Query(default=None),
) -> list[TraceListItem]:
    """列出所有追踪记录，支持按类型过滤。"""
    if not TRACE_DIR.exists():
        return []

    traces = sorted(TRACE_DIR.glob("trace_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

    if trace_type:
        traces = [t for t in traces if trace_type in t.name]

    result = []
    for trace_file in traces[:limit]:
        summary_file = trace_file.with_suffix(".summary.json")
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
                parts = trace_file.stem.split("_")
                t_type = parts[1] if len(parts) > 1 else "unknown"

                success = None
                with open(trace_file) as tf:
                    for line in tf:
                        event = json.loads(line)
                        if event.get("event_type") == "workflow_end":
                            success = event.get("success")
                            break

                result.append(
                    TraceListItem(
                        filename=trace_file.name,
                        trace_id=summary.get("trace_id", ""),
                        trace_type=t_type,
                        duration_seconds=summary.get("total_duration_seconds", 0),
                        total_events=summary.get("total_events", 0),
                        agent_count=len(summary.get("agents", [])),
                        task_count=len(summary.get("tasks", [])),
                        total_tokens=summary.get("total_tokens", 0),
                        success=success,
                    )
                )
    return result


@router.get("/detail/{trace_id}")
async def get_trace_detail(trace_id: str) -> TraceDetail:
    """获取指定追踪的详细信息。"""
    if not TRACE_DIR.exists():
        raise HTTPException(status_code=404, detail="Trace directory not found")

    trace_files = list(TRACE_DIR.glob(f"trace_*_{trace_id}.jsonl"))
    if not trace_files:
        trace_files = list(TRACE_DIR.glob(f"*{trace_id}*.jsonl"))

    if not trace_files:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    trace_file = trace_files[0]
    summary_file = trace_file.with_suffix(".summary.json")

    summary = {}
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)

    events = []
    with open(trace_file) as f:
        for line in f:
            events.append(json.loads(line))

    return TraceDetail(summary=summary, events=events)


@router.get("/by-filename/{filename}")
async def get_trace_by_filename(filename: str) -> TraceDetail:
    """根据文件名获取追踪详情。"""
    if not TRACE_DIR.exists():
        raise HTTPException(status_code=404, detail="Trace directory not found")

    trace_file = TRACE_DIR / filename
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail=f"Trace file {filename} not found")

    summary_file = trace_file.with_suffix(".summary.json")

    summary = {}
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)

    events = []
    with open(trace_file) as f:
        for line in f:
            events.append(json.loads(line))

    return TraceDetail(summary=summary, events=events)


@router.get("/config")
async def get_log_config() -> dict:
    """获取当前日志配置信息。"""
    return {
        "backend": settings.RUN_LOG_BACKEND,
        "log_dir": settings.RUN_LOG_DIR if settings.RUN_LOG_BACKEND == "file" else None,
        "redis_prefix": settings.RUN_LOG_REDIS_PREFIX
        if settings.RUN_LOG_BACKEND == "redis"
        else None,
        "retention_days": settings.RUN_LOG_RETENTION_DAYS,
    }
