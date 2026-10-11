"""台账期次与合同的唯一关联及景区最近合同偏好。"""

from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import InvoiceSourceKind
from app.db.base import Base


class LedgerContractLink(Base):
    __tablename__ = "biz_ledger_contract_link"
    __table_args__ = (
        UniqueConstraint(
            "scenic_id",
            "source_kind",
            "period_key",
            name="uq_ledger_contract_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[InvoiceSourceKind] = mapped_column(
        SAEnum(
            InvoiceSourceKind,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    period_key: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("biz_contract.id", ondelete="RESTRICT"), nullable=False
    )
    contract_no_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_by: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False
    )

    contract = relationship("Contract", foreign_keys=[contract_id])
    selector = relationship("User", foreign_keys=[selected_by])


class ScenicContractPreference(Base):
    __tablename__ = "biz_scenic_contract_preference"
    __table_args__ = (
        UniqueConstraint(
            "scenic_id",
            "source_kind",
            name="uq_scenic_contract_preference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[InvoiceSourceKind] = mapped_column(
        SAEnum(
            InvoiceSourceKind,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    last_contract_id: Mapped[int] = mapped_column(
        ForeignKey("biz_contract.id", ondelete="RESTRICT"), nullable=False
    )

    last_contract = relationship("Contract", foreign_keys=[last_contract_id])
