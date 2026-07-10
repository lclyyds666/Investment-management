"""审批记录模型（合规审计日志 + 电子签章快照）。

每条记录代表某一级角色对某合同的一次审批动作，
保留全部审批历史，构成详情页流转时间轴与打印审批单的签章来源。
"""
from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ApprovalAction
from app.db.base import Base

# 与用户签名同宽，容纳真实扫描签名图快照
SignatureText = Text().with_variant(MEDIUMTEXT, "mysql")


class Approval(Base):
    __tablename__ = "biz_approval"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("biz_contract.id", ondelete="CASCADE"), index=True, comment="关联合同"
    )
    approver_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id"), nullable=False, comment="审批人"
    )
    step: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="审批步序（APPROVAL_CHAIN 下标）"
    )
    approver_role: Mapped[str] = mapped_column(
        String(32), default="", comment="审批人当时的角色值"
    )
    action: Mapped[ApprovalAction] = mapped_column(
        SAEnum(ApprovalAction, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=False, comment="动作",
    )
    comment: Mapped[str] = mapped_column(Text, default="", comment="审批意见/驳回原因")
    # 审批时附加的电子签名快照（取自审批人 signature，实现"自动电子签章"）
    signature_snapshot: Mapped[str | None] = mapped_column(
        SignatureText, nullable=True, comment="电子签名快照"
    )

    contract = relationship("Contract", back_populates="approvals")
    approver = relationship("User")
