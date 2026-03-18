"""Memory API 端点"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from omni_agent.core import MemoryManager

router = APIRouter()

manager = MemoryManager()


class MemoryFileResponse(BaseModel):
    type: str
    content: str


class SessionSummaryResponse(BaseModel):
    user_id: str
    session_id: str
    round_count: int
    created_at: str
    updated_at: str
    profile_preview: str
    habit_preview: str
    context_preview: str


class SessionListResponse(BaseModel):
    user_id: str
    sessions: list[str]


class StatsResponse(BaseModel):
    users: int
    sessions: int


class WriteMemoryRequest(BaseModel):
    content: str


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    stats = manager.get_stats()
    return StatsResponse(**stats)


@router.get("/users")
async def list_users() -> list[str]:
    return manager.list_users()


@router.get("/users/{user_id}/sessions", response_model=SessionListResponse)
async def list_sessions(user_id: str) -> SessionListResponse:
    sessions = manager.list_sessions(user_id)
    return SessionListResponse(user_id=user_id, sessions=sessions)


@router.get(
    "/users/{user_id}/sessions/{session_id}",
    response_model=SessionSummaryResponse,
)
async def get_session_summary(user_id: str, session_id: str) -> SessionSummaryResponse:
    memory = manager.get_memory(user_id, session_id)
    if not memory.exists():
        raise HTTPException(status_code=404, detail="Memory not found")

    meta = memory.meta
    return SessionSummaryResponse(
        user_id=user_id,
        session_id=session_id,
        round_count=meta.get("round_count", 0),
        created_at=meta.get("created_at", ""),
        updated_at=meta.get("updated_at", ""),
        profile_preview=memory.read_profile()[:200],
        habit_preview=memory.read_habit()[:200],
        context_preview=memory.read_context()[:200],
    )


@router.get("/users/{user_id}/profile", response_model=MemoryFileResponse)
async def get_profile(user_id: str) -> MemoryFileResponse:
    memory = manager.get_memory(user_id, "__placeholder__")
    return MemoryFileResponse(type="profile", content=memory.read_profile())


@router.put("/users/{user_id}/profile")
async def update_profile(user_id: str, request: WriteMemoryRequest) -> dict:
    memory = manager.get_memory(user_id, "__placeholder__")
    memory.write_profile(request.content)
    return {"success": True}


@router.get("/users/{user_id}/habit", response_model=MemoryFileResponse)
async def get_habit(user_id: str) -> MemoryFileResponse:
    memory = manager.get_memory(user_id, "__placeholder__")
    return MemoryFileResponse(type="habit", content=memory.read_habit())


@router.put("/users/{user_id}/habit")
async def update_habit(user_id: str, request: WriteMemoryRequest) -> dict:
    memory = manager.get_memory(user_id, "__placeholder__")
    memory.write_habit(request.content)
    return {"success": True}


@router.get(
    "/users/{user_id}/sessions/{session_id}/context",
    response_model=MemoryFileResponse,
)
async def get_context(user_id: str, session_id: str) -> MemoryFileResponse:
    memory = manager.get_memory(user_id, session_id)
    return MemoryFileResponse(type="context", content=memory.read_context())


@router.delete("/users/{user_id}/sessions/{session_id}")
async def delete_session_memory(user_id: str, session_id: str) -> dict:
    success = manager.delete_session(user_id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": f"Deleted memory for {user_id}/{session_id}"}


@router.delete("/users/{user_id}")
async def delete_user_memory(user_id: str) -> dict:
    success = manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "message": f"Deleted all memories for user {user_id}"}


@router.post("/cleanup")
async def cleanup_expired(max_age_days: int = Query(30, ge=1, le=365)) -> dict:
    removed = manager.cleanup_expired(max_age_days=max_age_days)
    return {"success": True, "removed_sessions": removed}
