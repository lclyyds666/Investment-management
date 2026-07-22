"""操作审计端点（仅超级管理员可查询/导出）。

数据来源见 models/audit.py + core/audit.py（中间件自动采集 + 认证埋点）。
"""
import csv
import io
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_superuser
from app.core.enums import role_label
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogOut, AuditLogPage
from app.schemas.common import Response

router = APIRouter()

# 供前端筛选下拉的枚举（与 core/audit.py 的采集口径一致）
_ACTIONS = [
    ("login", "登录"), ("login_failed", "登录失败"), ("logout", "退出"),
    ("create", "新建"), ("update", "修改"), ("delete", "删除"),
    ("submit", "提交"), ("approve", "通过"), ("reject", "驳回"),
    ("upload", "上传"), ("export", "导出"), ("ai", "AI"),
    ("reset_password", "重置密码"), ("toggle_active", "启停用"), ("op", "其他"),
]
_MODULES = [
    ("auth", "认证"), ("user", "用户"), ("contract", "合同"), ("approval", "业务审批"),
    ("operation", "经营数据"), ("customer", "客户"), ("channel", "渠道"),
    ("invoice", "发票"), ("knowledge", "知识库"), ("ticket_ledger", "核销台账"),
    ("audit", "审计"),
]


def _end_of_day(d: datetime) -> datetime:
    return d.replace(hour=23, minute=59, second=59, microsecond=999999)


def _build_query(
    keyword: str | None, module: str | None, action: str | None,
    status_: str | None, method: str | None,
    start: datetime | None, end: datetime | None,
):
    conds = []
    if keyword:
        kw = f"%{keyword.strip()}%"
        conds.append(or_(
            AuditLog.username.like(kw),
            AuditLog.full_name.like(kw),
            AuditLog.path.like(kw),
            AuditLog.target_desc.like(kw),
            AuditLog.ip.like(kw),
        ))
    if module:
        conds.append(AuditLog.module == module)
    if action:
        conds.append(AuditLog.action == action)
    if status_ in ("success", "fail"):
        conds.append(AuditLog.status == status_)
    if method:
        conds.append(AuditLog.method == method.upper())
    if start:
        conds.append(AuditLog.created_at >= start)
    if end:
        conds.append(AuditLog.created_at <= _end_of_day(end))
    return conds


@router.get("/audit/meta", response_model=Response[dict], summary="审计筛选枚举(动作/模块)")
def audit_meta(_: User = Depends(require_superuser)):
    return Response.ok({
        "actions": [{"value": v, "label": l} for v, l in _ACTIONS],
        "modules": [{"value": v, "label": l} for v, l in _MODULES],
    })


@router.get("/audit/logs", response_model=Response[AuditLogPage], summary="操作审计查询(分页+筛选)")
def list_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
    keyword: str | None = Query(None, description="用户/路径/目标/IP 关键词"),
    module: str | None = Query(None),
    action: str | None = Query(None),
    status: str | None = Query(None, description="success/fail"),
    method: str | None = Query(None),
    start: datetime | None = Query(None, description="开始日期"),
    end: datetime | None = Query(None, description="结束日期"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    conds = _build_query(keyword, module, action, status, method, start, end)
    total = db.scalar(select(func.count(AuditLog.id)).where(*conds)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(*conds)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return Response.ok(AuditLogPage(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total, page=page, size=size,
    ))


@router.get("/audit/logs/export", summary="导出操作审计(CSV，按同筛选条件)")
def export_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
    keyword: str | None = Query(None),
    module: str | None = Query(None),
    action: str | None = Query(None),
    status: str | None = Query(None),
    method: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
):
    conds = _build_query(keyword, module, action, status, method, start, end)
    rows = db.scalars(
        select(AuditLog).where(*conds).order_by(AuditLog.id.desc()).limit(50000)
    ).all()

    act_map = dict(_ACTIONS)
    mod_map = dict(_MODULES)
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM，Excel 直开不乱码
    w = csv.writer(buf)
    w.writerow(["时间", "账号", "姓名", "角色", "模块", "动作", "目标", "方法", "路径", "IP", "结果", "响应码"])
    for r in rows:
        w.writerow([
            str(r.created_at)[:19] if r.created_at else "",
            r.username, r.full_name, role_label(r.role) if r.role else "",
            mod_map.get(r.module, r.module), act_map.get(r.action, r.action),
            r.target_desc, r.method, r.path, r.ip,
            "成功" if r.status == "success" else "失败", r.http_status,
        ])
    data = buf.getvalue().encode("utf-8")
    fname = quote(f"操作审计_{str(datetime.now())[:10]}.csv")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )
