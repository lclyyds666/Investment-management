"""操作审计日志模型（登录日志 + 通用操作日志）。

采集来源：
- 认证埋点（登录成功/失败/锁定/退出，见 endpoints/auth.py）；
- 审计中间件自动采集所有写操作(POST/PUT/DELETE/PATCH)及导出类 GET
  （见 core/audit.py）。

设计要点：用户信息按快照存储（username/full_name/role），即便用户改名或删除，
历史日志仍可读；仅记录 method/path/status 等元数据，不记录请求体（天然不泄露密码）。
"""
from sqlalchemy import Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "sys_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    # 操作者快照（user_id 可空：登录失败/匿名请求可能无有效用户）
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True, comment="操作者ID")
    username: Mapped[str] = mapped_column(String(64), default="", comment="操作者账号(快照)")
    full_name: Mapped[str] = mapped_column(String(64), default="", comment="操作者姓名(快照)")
    role: Mapped[str] = mapped_column(String(32), default="", comment="操作者角色(快照)")

    action: Mapped[str] = mapped_column(String(32), index=True, default="", comment="动作(login/create/update/delete/approve/export...)")
    module: Mapped[str] = mapped_column(String(32), index=True, default="", comment="资源模块(auth/contract/approval/user...)")
    target_desc: Mapped[str] = mapped_column(String(255), default="", comment="目标对象描述")

    method: Mapped[str] = mapped_column(String(8), default="", comment="HTTP 方法")
    path: Mapped[str] = mapped_column(String(255), default="", comment="请求路径")
    ip: Mapped[str] = mapped_column(String(64), default="", comment="客户端IP")

    status: Mapped[str] = mapped_column(String(16), default="success", comment="结果(success/fail)")
    http_status: Mapped[int] = mapped_column(Integer, default=0, comment="HTTP 响应码")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="摘要/错误信息(不含敏感字段)")

    __table_args__ = (
        Index("idx_audit_created", "created_at"),
    )
