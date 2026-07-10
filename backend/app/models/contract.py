"""合同模型（合同全生命周期 + 7 级审批流状态）。"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ContractStatus, ContractType
from app.db.base import Base


class Contract(Base):
    __tablename__ = "biz_contract"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    contract_no: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="合同编号"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="合同名称")
    party_a: Mapped[str] = mapped_column(String(200), default="", comment="甲方")
    party_b: Mapped[str] = mapped_column(String(200), default="", comment="乙方")
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="合同金额(元)"
    )
    sign_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="签订日期")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")

    # ---- 审批单打印所需的业务字段 ----
    contract_type: Mapped[ContractType] = mapped_column(
        SAEnum(ContractType, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=ContractType.PAYMENT,
        nullable=False,
        comment="单据类型：payment=付款审批单 / business=业务审批单",
    )
    department: Mapped[str] = mapped_column(String(64), default="", comment="申请部门")
    customer_name: Mapped[str] = mapped_column(String(200), default="", comment="客户名称")
    business_type: Mapped[str] = mapped_column(String(64), default="", comment="业务类型")

    # ---- 审批流状态 ----
    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=ContractStatus.DRAFT,
        nullable=False,
        comment="状态",
    )
    current_step: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="当前待审批步序（APPROVAL_CHAIN 下标），pending 时有效",
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id"), nullable=False, comment="创建人(业务经办)"
    )

    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )


from app.models.approval import Approval  # noqa: E402  解决前向引用
