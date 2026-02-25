"""健康检查端点。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查端点，返回服务运行状态。"""
    return {"status": "healthy"}


@router.get("/")
async def root() -> dict[str, str | dict[str, str]]:
    """根端点，返回 API 基本信息和可用端点列表。"""
    return {
        "name": "Omni Agent",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "agents": "/api/v1/agents/run",
            "tools": "/api/v1/tools",
            "docs": "/docs",
        },
    }
