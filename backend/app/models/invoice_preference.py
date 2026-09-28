"""景区按发票方向记忆的默认合同。"""
from sqlalchemy import Enum as SAEnum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import InvoiceDirection
from app.db.base import Base


class ScenicInvoicePreference(Base):
    __tablename__ = "biz_scenic_invoice_preference"
    __table_args__ = (
        UniqueConstraint("scenic_id", "direction", name="uq_scenic_invoice_preference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    direction: Mapped[InvoiceDirection] = mapped_column(
        SAEnum(InvoiceDirection, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    last_contract_no: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    @property
    def contract_no(self) -> str:
        return self.last_contract_no

    @contract_no.setter
    def contract_no(self, value: str) -> None:
        self.last_contract_no = value or ""
