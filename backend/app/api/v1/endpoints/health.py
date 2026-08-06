"""健康检查端点。"""
from fastapi import APIRouter

from app.core.store import backend_name
from app.schemas.common import Response

router = APIRouter()


@router.get("/health", summary="健康检查")
def health_check():
    shared_store = "ready" if backend_name() == "redis" else "not_configured"
    return Response.ok(data={"status": "ok", "ai_shared_store": shared_store})
