"""健康检查端点。"""
from fastapi import APIRouter

from app.schemas.common import Response

router = APIRouter()


@router.get("/health", summary="健康检查")
def health_check():
    return Response.ok(data={"status": "ok"})
