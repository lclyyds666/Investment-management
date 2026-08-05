from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Role
from app.db.base import Base


class UserCompanyRole(Base):
    __tablename__ = "sys_user_company_role"
    __table_args__ = (
        UniqueConstraint("user_id", "company_code", name="uq_user_company_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(
        SAEnum(
            Role,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    user = relationship("User", back_populates="company_roles")
