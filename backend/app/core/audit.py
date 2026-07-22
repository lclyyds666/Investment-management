"""操作审计采集：写日志助手 + 自动采集中间件。

设计原则：
- **绝不影响主请求**：所有写日志逻辑用 try/except 包裹并吞掉异常；
- **独立会话**：用独立 SessionLocal 写库，与请求会话解耦（登录失败要 raise，
  用请求会话会被回滚，故独立会话最稳）；
- **不记请求体**：仅记 method/path/status 等元数据，天然不泄露密码等敏感字段；
- GET 默认不记（避免读操作刷屏），仅白名单导出/下载类 GET 入库。
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal

# 路径前缀（去掉后按段解析 module/action）
_API_PREFIX = settings.API_V1_PREFIX.rstrip("/")

# module 归一：URL 段(复数/连字符) → 中文模块键
_MODULE_MAP = {
    "auth": "auth",
    "users": "user",
    "contracts": "contract",
    "approval-forms": "approval",
    "approval": "approval",
    "operation": "operation",
    "customers": "customer",
    "channels": "channel",
    "invoices": "invoice",
    "knowledge": "knowledge",
    "scenic-spots": "ticket_ledger",
    "audit": "audit",
}

# 末段 → 动作
_ACTION_BY_SUFFIX = {
    "submit": "submit",
    "approve": "approve",
    "reject": "reject",
    "attachment": "upload",
    "export": "export",
    "print": "export",
    "legal-doc": "export",
    "parse": "upload",
    "ai-review": "ai",
    "proofread": "ai",
    "ai-diagnose": "ai",
    "research": "ai",
    "reset-password": "reset_password",
    "active": "toggle_active",
    "password": "update",   # /users/me/password 改本人密码
    "username": "update",   # /users/me/username 改本人账号
}

# 白名单：这些 GET 也记录（导出/下载/生成文件类）
_GET_LOG_SUFFIX = {"export", "print", "legal-doc", "attachment", "download"}

# 完全跳过的路径（噪声/无意义）
_SKIP_PATHS = {
    f"{_API_PREFIX}/health",
    f"{_API_PREFIX}/auth/login",     # 登录在 auth.py 显式埋点
    f"{_API_PREFIX}/auth/logout",    # 退出在 auth.py 显式埋点
    f"{_API_PREFIX}/auth/captcha",
    f"{_API_PREFIX}/auth/me",
}


def client_ip(request: Request) -> str:
    """取真实客户端 IP：优先 X-Forwarded-For / X-Real-IP（经 Nginx 反代），兜底直连。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()[:64]
    return (request.client.host if request.client else "")[:64]


def derive_module_action(method: str, path: str) -> tuple[str, str, str]:
    """从 method + path 推断 (module, action, target_desc)。启发式，够用即可。"""
    p = path
    if p.startswith(_API_PREFIX):
        p = p[len(_API_PREFIX):]
    segs = [s for s in p.split("/") if s]
    module = _MODULE_MAP.get(segs[0], segs[0]) if segs else ""

    last = segs[-1] if segs else ""
    m = method.upper()
    if m == "GET":
        # GET 仅经导出/下载白名单进入日志，统一记为导出
        action = "export"
    else:
        action = _ACTION_BY_SUFFIX.get(last) or {
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }.get(m, "op")

    # 目标描述：取路径中的数字 id（如 /contracts/12/approve → 合同#12）
    target_id = next((s for s in segs[1:] if s.isdigit()), "")
    target_desc = f"{module}#{target_id}" if target_id else module
    return module, action, target_desc


def write_log(
    *,
    user_id: int | None = None,
    username: str = "",
    full_name: str = "",
    role: str = "",
    action: str = "",
    module: str = "",
    target_desc: str = "",
    method: str = "",
    path: str = "",
    ip: str = "",
    status: str = "success",
    http_status: int = 0,
    detail: str | None = None,
) -> None:
    """独立会话写入一条审计日志；任何异常都被吞掉，绝不影响主流程。"""
    from app.models.audit import AuditLog  # 延迟导入，避免循环

    db = None
    try:
        db = SessionLocal()
        db.add(AuditLog(
            user_id=user_id,
            username=(username or "")[:64],
            full_name=(full_name or "")[:64],
            role=(role or "")[:32],
            action=(action or "")[:32],
            module=(module or "")[:32],
            target_desc=(target_desc or "")[:255],
            method=(method or "")[:8],
            path=(path or "")[:255],
            ip=(ip or "")[:64],
            status=status if status in ("success", "fail") else "success",
            http_status=http_status or 0,
            detail=(detail[:512] if detail else None),
        ))
        db.commit()
    except Exception:  # noqa: BLE001 审计失败绝不影响业务
        if db is not None:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    finally:
        if db is not None:
            db.close()


class AuditMiddleware(BaseHTTPMiddleware):
    """自动采集所有写操作 + 白名单导出类 GET。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            self._maybe_log(request, response)
        except Exception:  # noqa: BLE001
            pass
        return response

    def _maybe_log(self, request: Request, response) -> None:
        path = request.url.path
        method = request.method.upper()

        # 只处理 API 路径
        if not path.startswith(_API_PREFIX):
            return
        if method == "OPTIONS" or path in _SKIP_PATHS:
            return

        # GET 仅记录白名单导出/下载类
        if method == "GET":
            last = path.rstrip("/").rsplit("/", 1)[-1]
            if last not in _GET_LOG_SUFFIX:
                return

        # 解析操作者（从 Authorization Bearer 解 token → 查用户快照）
        user_id = username = full_name = role = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            payload = decode_access_token(auth[7:].strip())
            if payload and payload.get("sub"):
                try:
                    user_id = int(payload["sub"])
                    role = payload.get("role") or ""
                except (TypeError, ValueError):
                    user_id = None
        if user_id is not None:
            db = None
            try:
                db = SessionLocal()
                from app.models.user import User
                u = db.get(User, user_id)
                if u:
                    username, full_name = u.username, u.full_name
                    role = u.role.value
            except Exception:  # noqa: BLE001
                pass
            finally:
                if db is not None:
                    db.close()

        module, action, target_desc = derive_module_action(method, path)
        http_status = getattr(response, "status_code", 0) or 0
        status = "success" if http_status < 400 else "fail"

        write_log(
            user_id=user_id,
            username=username or "",
            full_name=full_name or "",
            role=role or "",
            action=action,
            module=module,
            target_desc=target_desc,
            method=method,
            path=path,
            ip=client_ip(request),
            status=status,
            http_status=http_status,
        )
