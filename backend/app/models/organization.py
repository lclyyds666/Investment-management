from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AssignmentStatus,
    DataScope,
    OrganizationType,
    PermissionAction,
    PositionCategory,
)
from app.db.base import Base


class Organization(Base):
    __tablename__ = "sys_organization"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    organization_type: Mapped[OrganizationType] = mapped_column(
        SAEnum(
            OrganizationType,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_organization.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    company_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent = relationship("Organization", remote_side=[id], back_populates="children")
    children = relationship("Organization", back_populates="parent")
    assignments = relationship("UserAssignment", back_populates="organization")


class Position(Base):
    __tablename__ = "sys_position"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[PositionCategory] = mapped_column(
        SAEnum(
            PositionCategory,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    assignments = relationship("UserAssignment", back_populates="position")
    permission_links = relationship(
        "PositionPermission", back_populates="position", cascade="all, delete-orphan"
    )


class UserAssignment(Base):
    __tablename__ = "sys_user_assignment"
    __table_args__ = (
        Index("idx_assignment_user_status_dates", "user_id", "status", "valid_from", "valid_until"),
        Index("idx_assignment_org_position", "organization_id", "position_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("sys_organization.id", ondelete="RESTRICT"), nullable=False
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("sys_position.id", ondelete="RESTRICT"), nullable=False
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(
            AssignmentStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=AssignmentStatus.ACTIVE,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)

    user = relationship("User", back_populates="assignments")
    organization = relationship("Organization", back_populates="assignments")
    position = relationship("Position", back_populates="assignments")
    governance_scopes = relationship(
        "GovernanceScope", back_populates="assignment", cascade="all, delete-orphan"
    )
    external_detail = relationship(
        "ExternalAssignment",
        back_populates="assignment",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def is_effective_on(self, target: date) -> bool:
        return (
            self.status == AssignmentStatus.ACTIVE
            and self.valid_from <= target
            and (self.valid_until is None or self.valid_until >= target)
        )


class Permission(Base):
    __tablename__ = "sys_permission"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    action: Mapped[PermissionAction] = mapped_column(
        SAEnum(
            PermissionAction,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PositionPermission(Base):
    __tablename__ = "sys_position_permission"
    __table_args__ = (
        UniqueConstraint(
            "position_id", "permission_id", "data_scope", "scope_ref",
            name="uq_position_permission_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("sys_position.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("sys_permission.id", ondelete="CASCADE"), nullable=False
    )
    data_scope: Mapped[DataScope] = mapped_column(
        SAEnum(
            DataScope,
            native_enum=False,
            length=24,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    scope_ref: Mapped[str] = mapped_column(String(96), default="", nullable=False)

    position = relationship("Position", back_populates="permission_links")
    permission = relationship("Permission")


class GovernanceScope(Base):
    __tablename__ = "sys_governance_scope"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "scope_type", "scope_ref",
            name="uq_assignment_governance_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user_assignment.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_ref: Mapped[str] = mapped_column(String(96), nullable=False)

    assignment = relationship("UserAssignment", back_populates="governance_scopes")


class ExternalAssignment(Base):
    __tablename__ = "sys_external_assignment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user_assignment.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    provider_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    service_scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    assignment = relationship("UserAssignment", back_populates="external_detail")


from app.models.portal import UserCompanyRole  # noqa: E402,F401
from app.models.user import User  # noqa: E402,F401
