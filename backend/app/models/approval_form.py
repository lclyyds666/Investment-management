"""审批单模型（审批中心两套独立工作流：业务付款审批单 / 业务审批单）。

与合同模块（biz_contract）完全独立：审批单是「审批中心」的主数据，合同模块仅作为
AI 合同校对的比对目标源。审批链按 form_type 分派（见 enums.FORM_CHAINS）。

- ``ApprovalForm``      审批单主表（payment 比 business 多付款/银行字段）。
- ``ApprovalFormAction`` 逐级审批流转/电子签章审计日志（与合同的 biz_approval 同构但独立）。
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ApprovalAction, ContractStatus, ContractType
from app.db.base import Base

# 电子签名以图片 data-URI 存储，与 sys_user.signature 同宽
SignatureText = Text().with_variant(MEDIUMTEXT, "mysql")


class ApprovalForm(Base):
    __tablename__ = "biz_approval_form"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    form_type: Mapped[ContractType] = mapped_column(
        SAEnum(ContractType, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=False, comment="单据类型：payment=业务付款审批单 / business=业务审批单",
    )

    # ---- 通用字段（两类共有）----
    department: Mapped[str] = mapped_column(String(64), default="", comment="申请部门")
    apply_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="申请日期")
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_customer.id", ondelete="SET NULL"), nullable=True, comment="客户(外键关联客户资料库)"
    )
    customer_name: Mapped[str] = mapped_column(String(200), default="", comment="客户名称(快照)")
    business_type: Mapped[str] = mapped_column(String(64), default="", comment="业务类型")
    business_desc: Mapped[str] = mapped_column(String(500), default="详见合同", comment="业务情况")
    contract_no: Mapped[str] = mapped_column(String(64), default="", index=True, comment="合同编号")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")

    # ---- 付款审批单专有字段 ----
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="付款金额(元)")
    amount_words: Mapped[str] = mapped_column(String(128), default="", comment="付款金额大写(自动转换)")
    bank_name: Mapped[str] = mapped_column(String(128), default="", comment="开户行")
    bank_account: Mapped[str] = mapped_column(String(64), default="", comment="银行账号")

    # ---- 合同附件（PDF，真实落盘）----
    attachment_name: Mapped[str] = mapped_column(String(255), default="", comment="合同附件原始文件名")
    attachment_stored: Mapped[str] = mapped_column(String(255), default="", comment="合同附件磁盘存储名")

    # ---- 工作流状态 ----
    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=ContractStatus.DRAFT, nullable=False, comment="状态",
    )
    current_step: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="当前待审批步序（对应链下标），pending 时有效",
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id"), nullable=False, comment="创建人(业务经办)"
    )

    actions: Mapped[list["ApprovalFormAction"]] = relationship(
        back_populates="form", cascade="all, delete-orphan"
    )


class ApprovalFormAction(Base):
    __tablename__ = "biz_approval_form_action"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    form_id: Mapped[int] = mapped_column(
        ForeignKey("biz_approval_form.id", ondelete="CASCADE"), index=True, comment="关联审批单"
    )
    approver_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id"), nullable=False, comment="审批人"
    )
    step: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="审批步序（链下标）")
    approver_role: Mapped[str] = mapped_column(String(32), default="", comment="审批人当时的角色值")
    action: Mapped[ApprovalAction] = mapped_column(
        SAEnum(ApprovalAction, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=False, comment="动作",
    )
    comment: Mapped[str] = mapped_column(Text, default="", comment="审批意见/驳回原因")
    signature_snapshot: Mapped[str | None] = mapped_column(
        SignatureText, nullable=True, comment="电子签名快照"
    )

    form = relationship("ApprovalForm", back_populates="actions")
    approver = relationship("User")
