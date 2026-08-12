from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import AssignmentStatus, DataScope, PositionCategory, Role
from app.models.organization import (
    ExternalAssignment,
    GovernanceScope,
    Organization,
    Permission,
    Position,
    PositionPermission,
    UserAssignment,
)
from app.models.user import User
from app.schemas.organization_admin import (
    GOVERNANCE_POSITION_TARGETS,
    OrganizationWrite,
    PositionPermissionWrite,
    PositionWrite,
    UserAssignmentsReplace,
)


SUPPORTED_BUSINESS_DOMAINS = frozenset({"investment", "supply", "fund"})


STATIC_WORKFLOW_POSITION_SETS = (
    frozenset({"supply.business_handler", "supply.company_leader", "external.legal_counsel", "investment.duty.supply_risk_review", "governance.supply_leader"}),
    frozenset({"supply.business_handler", "supply.business_reviewer", "supply.finance_handler", "supply.company_leader", "investment.duty.supply_risk_review", "investment.duty.supply_finance_review", "governance.supply_leader"}),
    frozenset({"supply.business_handler", "supply.business_reviewer", "supply.company_leader", "investment.duty.supply_risk_review", "governance.supply_leader"}),
)


class AuthorizationConflictError(Exception):
    def __init__(self, code: str, message: str, *, user_id: int | None = None, assignment_ids: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.user_id = user_id
        self.assignment_ids = assignment_ids


def _active_assignments(db: Session, entity, entity_id: int):
    return db.scalars(select(UserAssignment).where(
        getattr(UserAssignment, entity) == entity_id,
        UserAssignment.status == AssignmentStatus.ACTIVE,
        or_(UserAssignment.valid_until.is_(None), UserAssignment.valid_until >= date.today()),
    )).all()


def _resolve_parent(db: Session, code: str | None) -> Organization | None:
    if code is None:
        return None
    parent = db.scalar(select(Organization).where(Organization.code == code))
    if parent is None:
        raise AuthorizationConflictError("organization_not_found", "Parent organization does not exist.")
    return parent


def create_organization(db: Session, payload: OrganizationWrite) -> Organization:
    if db.scalar(select(Organization).where(Organization.code == payload.code)):
        raise AuthorizationConflictError("organization_code_exists", "Organization code already exists.")
    parent = _resolve_parent(db, payload.parent_code)
    organization = Organization(
        code=payload.code, name=payload.name, organization_type=payload.organization_type,
        parent_id=parent.id if parent else None,
        company_code=payload.company_code.value if payload.company_code else None,
        sort_order=payload.sort_order, is_active=payload.is_active,
    )
    try:
        db.add(organization)
        db.commit()
        db.refresh(organization)
        return organization
    except Exception:
        db.rollback()
        raise


def update_organization(db: Session, organization_id: int, payload: OrganizationWrite) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise AuthorizationConflictError("organization_not_found", "Organization does not exist.")
    parent = _resolve_parent(db, payload.parent_code)
    cursor = parent
    while cursor is not None:
        if cursor.id == organization.id:
            raise AuthorizationConflictError("organization_cycle", "Organization hierarchy cannot contain a cycle.")
        cursor = cursor.parent
    if organization.is_active and not payload.is_active and _active_assignments(db, "organization_id", organization.id):
        raise AuthorizationConflictError("organization_has_active_assignments", "Organization has active assignments.")
    try:
        organization.code = payload.code
        organization.name = payload.name
        organization.organization_type = payload.organization_type
        organization.parent_id = parent.id if parent else None
        organization.company_code = payload.company_code.value if payload.company_code else None
        organization.sort_order = payload.sort_order
        organization.is_active = payload.is_active
        db.commit()
        db.refresh(organization)
        return organization
    except Exception:
        db.rollback()
        raise


def create_position(db: Session, payload: PositionWrite) -> Position:
    if db.scalar(select(Position).where(Position.code == payload.code)):
        raise AuthorizationConflictError("position_code_exists", "Position code already exists.")
    position = Position(**payload.model_dump())
    try:
        db.add(position)
        db.commit()
        db.refresh(position)
        return position
    except Exception:
        db.rollback()
        raise


def update_position(db: Session, position_id: int, payload: PositionWrite) -> Position:
    position = db.get(Position, position_id)
    if position is None:
        raise AuthorizationConflictError("position_not_found", "Position does not exist.")
    if payload.code != position.code:
        raise AuthorizationConflictError("position_code_immutable", "Position code cannot be changed.")
    if position.is_active and not payload.is_active and _active_assignments(db, "position_id", position.id):
        raise AuthorizationConflictError("position_has_active_assignments", "Position has active assignments.")
    try:
        position.name = payload.name
        position.category = payload.category
        position.is_active = payload.is_active
        db.commit()
        db.refresh(position)
        return position
    except Exception:
        db.rollback()
        raise


def _valid_scope(db: Session, scope: DataScope, scope_ref: str) -> bool:
    if scope == DataScope.COMPANY:
        return db.scalar(select(Organization.id).where(
            Organization.code == scope_ref,
            Organization.organization_type == "company",
            Organization.is_active.is_(True),
        )) is not None
    if scope == DataScope.DEPARTMENT:
        return db.scalar(select(Organization.id).where(
            Organization.code == scope_ref,
            Organization.organization_type == "department",
            Organization.is_active.is_(True),
        )) is not None
    if scope == DataScope.BUSINESS_DOMAIN:
        return scope_ref in SUPPORTED_BUSINESS_DOMAINS
    return not scope_ref


def replace_position_permissions(db: Session, position_id: int, payloads: list[PositionPermissionWrite]) -> list[PositionPermission]:
    position = db.get(Position, position_id)
    if position is None:
        raise AuthorizationConflictError("position_not_found", "Position does not exist.")
    permissions = {item.permission_code: db.scalar(select(Permission).where(Permission.code == item.permission_code)) for item in payloads}
    if any(permission is None for permission in permissions.values()):
        raise AuthorizationConflictError("permission_not_found", "One or more permissions do not exist.")
    if any(not _valid_scope(db, item.data_scope, item.scope_ref) for item in payloads):
        raise AuthorizationConflictError("invalid_permission_scope", "Permission scope and scope reference do not match.")
    try:
        db.query(PositionPermission).filter(PositionPermission.position_id == position.id).delete()
        links = [PositionPermission(position_id=position.id, permission_id=permissions[item.permission_code].id, data_scope=item.data_scope, scope_ref=item.scope_ref) for item in payloads]
        db.add_all(links)
        db.commit()
        return links
    except Exception:
        db.rollback()
        raise


def _periods_overlap(left: UserAssignment, right: UserAssignment) -> bool:
    left_end = left.valid_until or date.max
    right_end = right.valid_until or date.max
    return left.valid_from <= right_end and right.valid_from <= left_end


def validate_assignment_conflicts(user_id: int, assignments: list[UserAssignment]) -> None:
    active = [item for item in assignments if item.status == AssignmentStatus.ACTIVE]
    for workflow_set in STATIC_WORKFLOW_POSITION_SETS:
        candidates = [item for item in active if item.position.code in workflow_set]
        for index, left in enumerate(candidates):
            for right in candidates[index + 1:]:
                if left.position_id != right.position_id and _periods_overlap(left, right):
                    raise AuthorizationConflictError(
                        "assignment_workflow_conflict",
                        "Overlapping assignments conflict in a static workflow.",
                        user_id=user_id,
                        assignment_ids=tuple(item.id for item in (left, right) if item.id is not None),
                    )


def replace_user_assignments(db: Session, user_id: int, payload: UserAssignmentsReplace) -> list[UserAssignment]:
    try:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise AuthorizationConflictError("user_not_found", "User does not exist.", user_id=user_id)
        if user.is_superuser or user.role == Role.INFO_MAINTAINER:
            raise AuthorizationConflictError("information_maintainer_immutable", "Information-maintainer assignments cannot be changed.", user_id=user_id)
        organizations = {item.organization_code: db.scalar(select(Organization).where(Organization.code == item.organization_code)) for item in payload.assignments}
        positions = {item.position_code: db.scalar(select(Position).where(Position.code == item.position_code)) for item in payload.assignments}
        if any(item is None for item in organizations.values()) or any(item is None for item in positions.values()):
            raise AuthorizationConflictError("assignment_reference_not_found", "Every organization and position code must resolve before replacement.", user_id=user_id)
        existing_assignments = db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        replacements: list[UserAssignment] = []
        for item in payload.assignments:
            position = positions[item.position_code]
            target_company = GOVERNANCE_POSITION_TARGETS.get(position.code)
            organization = organizations[item.organization_code]
            if target_company is not None and (
                organization.code != target_company
                or organization.company_code != target_company
                or not any(
                    scope.scope_type == "company" and scope.scope_ref == target_company
                    for scope in item.governance_scopes
                )
            ):
                raise AuthorizationConflictError(
                    "governance_scope_required",
                    "Governance assignments require their target subsidiary organization and scope.",
                    user_id=user_id,
                )
            replacements.append(UserAssignment(user_id=user.id, organization_id=organizations[item.organization_code].id, position_id=position.id, valid_from=item.valid_from, valid_until=item.valid_until, status=item.status, source="manual"))
        db.add_all(replacements)
        for assignment, item in zip(replacements, payload.assignments):
            assignment.organization = organizations[item.organization_code]
            assignment.position = positions[item.position_code]
        validate_assignment_conflicts(user.id, replacements)
        for assignment in existing_assignments:
            db.delete(assignment)
        db.flush()
        db.flush()
        for assignment, item in zip(replacements, payload.assignments):
            db.add_all([GovernanceScope(assignment_id=assignment.id, scope_type=scope.scope_type, scope_ref=scope.scope_ref) for scope in item.governance_scopes])
            if item.external:
                db.add(ExternalAssignment(assignment_id=assignment.id, provider_name=item.external.provider_name.strip(), service_scopes=item.external.service_scopes))
        db.flush()
        db.commit()
        return db.scalars(
            select(UserAssignment)
            .where(UserAssignment.user_id == user.id)
            .options(joinedload(UserAssignment.organization), joinedload(UserAssignment.position))
            .order_by(UserAssignment.id)
        ).unique().all()
    except Exception:
        db.rollback()
        raise
