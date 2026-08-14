from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import AssignmentStatus, DataScope
from app.models.organization import Organization, Permission, Position, PositionPermission, UserAssignment
from app.models.user import User


@dataclass(frozen=True)
class PermissionContext:
    company_code: str | None = None
    department_code: str | None = None
    business_domain: str | None = None
    owner_id: int | None = None
    participant_ids: frozenset[int] = frozenset()
    assigned_user_id: int | None = None


@dataclass(frozen=True)
class EffectiveGrant:
    code: str
    data_scope: DataScope
    scope_ref: str
    assignment_id: int
    position_code: str
    organization_code: str


def _effective_assignment_filters(on_date: date):
    return (
        UserAssignment.status == AssignmentStatus.ACTIVE,
        UserAssignment.valid_from <= on_date,
        or_(UserAssignment.valid_until.is_(None), UserAssignment.valid_until >= on_date),
        Organization.is_active.is_(True),
        Position.is_active.is_(True),
    )


def active_assignments(
    db: Session, user_id: int, on_date: date | None = None
) -> list[UserAssignment]:
    target_date = on_date or date.today()
    statement = (
        select(UserAssignment)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .where(UserAssignment.user_id == user_id, *_effective_assignment_filters(target_date))
        .options(joinedload(UserAssignment.organization), joinedload(UserAssignment.position))
    )
    return list(db.scalars(statement))


def permission_grants(
    db: Session, user_id: int, on_date: date | None = None
) -> tuple[EffectiveGrant, ...]:
    target_date = on_date or date.today()
    statement = (
        select(UserAssignment, Organization, Position, PositionPermission, Permission)
        .join(Organization, UserAssignment.organization_id == Organization.id)
        .join(Position, UserAssignment.position_id == Position.id)
        .join(PositionPermission, PositionPermission.position_id == Position.id)
        .join(Permission, PositionPermission.permission_id == Permission.id)
        .where(
            UserAssignment.user_id == user_id,
            *_effective_assignment_filters(target_date),
            Permission.is_active.is_(True),
        )
    )
    return tuple(
        EffectiveGrant(
            code=permission.code,
            data_scope=position_permission.data_scope,
            scope_ref=position_permission.scope_ref,
            assignment_id=assignment.id,
            position_code=position.code,
            organization_code=organization.code,
        )
        for assignment, organization, position, position_permission, permission in db.execute(statement)
    )


def has_position(
    db: Session, user_id: int, position_code: str, on_date: date | None = None
) -> bool:
    user = db.get(User, user_id)
    if user is None or user.is_superuser:
        return False
    return any(
        assignment.position.code == position_code
        for assignment in active_assignments(db, user_id, on_date)
    )


def _scope_matches(grant: EffectiveGrant, user_id: int, context: PermissionContext) -> bool:
    if grant.data_scope == DataScope.PLATFORM:
        return True
    if grant.data_scope == DataScope.COMPANY:
        return context.company_code is not None and context.company_code == grant.scope_ref
    if grant.data_scope == DataScope.DEPARTMENT:
        return context.department_code is not None and context.department_code == grant.scope_ref
    if grant.data_scope == DataScope.BUSINESS_DOMAIN:
        return context.business_domain is not None and context.business_domain == grant.scope_ref
    if grant.data_scope == DataScope.OWN:
        return context.owner_id is not None and context.owner_id == user_id
    if grant.data_scope == DataScope.PARTICIPATED:
        return user_id in context.participant_ids
    if grant.data_scope == DataScope.ASSIGNED:
        return context.assigned_user_id is not None and context.assigned_user_id == user_id
    return False


def has_permission(
    db: Session,
    user: User,
    permission_code: str,
    context: PermissionContext | None = None,
) -> bool:
    if user.is_superuser:
        return bool(user.is_active)
    permission_context = context or PermissionContext()
    return any(
        _scope_matches(grant, user.id, permission_context)
        for grant in permission_grants(db, user.id)
        if grant.code == permission_code
    )
