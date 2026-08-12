from datetime import date
from typing import Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_superuser
from app.db.session import get_db
from app.models.organization import Organization, Permission, Position, PositionPermission, UserAssignment
from app.models.user import User
from app.schemas.organization_admin import (
    OrganizationWrite,
    PositionPermissionWrite,
    PositionWrite,
    UserAssignmentsReplace,
)
from app.services.assignment_permissions import PermissionContext, has_permission
from app.services.organization_admin import (
    AuthorizationConflictError,
    create_organization,
    create_position,
    replace_position_permissions,
    replace_user_assignments,
    update_organization,
    update_position,
)


router = APIRouter()
Result = TypeVar("Result")


def _directory_reader(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if current_user.is_superuser or has_permission(
        db,
        current_user,
        "organization.directory.view",
        PermissionContext(company_code="supplymanagement"),
    ):
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


def _conflict_boundary(operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except AuthorizationConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": error.code,
                "message": error.message,
                "user_id": error.user_id,
                "assignment_ids": error.assignment_ids,
                "conflicting_client_refs": error.conflicting_client_refs,
            },
        ) from error


def _required_reason(reason: str = Query(..., min_length=1)) -> str:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="reason must not be blank")
    return normalized_reason


def _organization_summary(organization: Organization) -> dict:
    return {
        "id": organization.id,
        "code": organization.code,
        "name": organization.name,
        "organization_type": organization.organization_type,
        "parent_id": organization.parent_id,
        "company_code": organization.company_code,
        "sort_order": organization.sort_order,
    }


def _position_summary(position: Position) -> dict:
    return {
        "id": position.id,
        "code": position.code,
        "name": position.name,
        "category": position.category,
    }


def _assignment_summary(assignment: UserAssignment) -> dict:
    return {
        "id": assignment.id,
        "user_id": assignment.user_id,
        "organization": _organization_summary(assignment.organization),
        "position": _position_summary(assignment.position),
        "valid_from": assignment.valid_from,
        "valid_until": assignment.valid_until,
        "status": assignment.status,
        "source": assignment.source,
        "governance_scopes": [
            {"scope_type": scope.scope_type, "scope_ref": scope.scope_ref}
            for scope in assignment.governance_scopes
        ],
        "external": (
            {
                "provider_name": assignment.external_detail.provider_name,
                "service_scopes": assignment.external_detail.service_scopes,
            }
            if assignment.external_detail else None
        ),
    }


@router.get("/tree")
def directory_tree(
    _: User = Depends(_directory_reader),
    db: Session = Depends(get_db),
) -> list[dict]:
    today = date.today()
    organizations = db.scalars(
        select(Organization)
        .where(Organization.is_active.is_(True))
        .order_by(Organization.sort_order, Organization.code)
    ).all()
    assignments = db.scalars(
        select(UserAssignment)
        .join(UserAssignment.organization)
        .join(UserAssignment.position)
        .join(UserAssignment.user)
        .where(
            UserAssignment.status == "active",
            UserAssignment.valid_from <= today,
            or_(UserAssignment.valid_until.is_(None), UserAssignment.valid_until >= today),
            Organization.is_active.is_(True),
            Position.is_active.is_(True),
            User.is_active.is_(True),
        )
        .options(
            selectinload(UserAssignment.organization),
            selectinload(UserAssignment.position),
            selectinload(UserAssignment.user),
        )
    ).all()
    positions_by_organization: dict[int, list[dict]] = {organization.id: [] for organization in organizations}
    for assignment in assignments:
        positions_by_organization[assignment.organization_id].append({
            **_position_summary(assignment.position),
            "personnel": {"id": assignment.user.id, "full_name": assignment.user.full_name},
        })
    return [
        {
            **_organization_summary(organization),
            "positions": positions_by_organization[organization.id],
        }
        for organization in organizations
    ]


@router.get("/positions")
def list_positions(
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[dict]:
    positions = db.scalars(
        select(Position)
        .options(selectinload(Position.permission_links).selectinload(PositionPermission.permission))
        .order_by(Position.code)
    ).all()
    return [
        {
            **_position_summary(position),
            "is_active": position.is_active,
            "permissions": [
                {
                    "permission_code": link.permission.code,
                    "data_scope": link.data_scope.value,
                    "scope_ref": link.scope_ref,
                }
                for link in sorted(
                    position.permission_links,
                    key=lambda link: (link.permission.code, link.data_scope.value, link.scope_ref),
                )
            ],
        }
        for position in positions
    ]


@router.get("/permissions")
def list_permissions(
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "id": permission.id,
            "code": permission.code,
            "name": permission.name,
            "resource": permission.resource,
            "action": permission.action,
            "is_active": permission.is_active,
        }
        for permission in db.scalars(select(Permission).order_by(Permission.code))
    ]


@router.get("/users/{user_id}/assignments")
def list_user_assignments(
    user_id: int,
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        _assignment_summary(assignment)
        for assignment in db.scalars(
            select(UserAssignment)
            .where(UserAssignment.user_id == user_id)
            .options(
                selectinload(UserAssignment.organization),
                selectinload(UserAssignment.position),
                selectinload(UserAssignment.governance_scopes),
                selectinload(UserAssignment.external_detail),
            )
            .order_by(UserAssignment.valid_from, UserAssignment.id)
        )
    ]


@router.post("")
def create_organization_endpoint(
    payload: OrganizationWrite,
    request: Request,
    reason: str = Depends(_required_reason),
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    organization = _conflict_boundary(
        lambda: create_organization(db, payload, actor=current_user, reason=reason)
    )
    request.state.explicit_authorization_audit = True
    return _organization_summary(organization)


@router.put("/{organization_id}")
def update_organization_endpoint(
    organization_id: int,
    payload: OrganizationWrite,
    request: Request,
    reason: str = Depends(_required_reason),
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    organization = _conflict_boundary(
        lambda: update_organization(db, organization_id, payload, actor=current_user, reason=reason)
    )
    request.state.explicit_authorization_audit = True
    return _organization_summary(organization)


@router.post("/positions")
def create_position_endpoint(
    payload: PositionWrite,
    request: Request,
    reason: str = Depends(_required_reason),
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    position = _conflict_boundary(
        lambda: create_position(db, payload, actor=current_user, reason=reason)
    )
    request.state.explicit_authorization_audit = True
    return _position_summary(position)


@router.put("/positions/{position_id}")
def update_position_endpoint(
    position_id: int,
    payload: PositionWrite,
    request: Request,
    reason: str = Depends(_required_reason),
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    position = _conflict_boundary(
        lambda: update_position(db, position_id, payload, actor=current_user, reason=reason)
    )
    request.state.explicit_authorization_audit = True
    return _position_summary(position)


@router.put("/positions/{position_id}/permissions")
def update_position_permissions_endpoint(
    position_id: int,
    payload: list[PositionPermissionWrite],
    request: Request,
    reason: str = Depends(_required_reason),
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[dict]:
    links = _conflict_boundary(
        lambda: replace_position_permissions(db, position_id, payload, actor=current_user, reason=reason)
    )
    request.state.explicit_authorization_audit = True
    return [
        {
            "id": link.id,
            "permission_id": link.permission_id,
            "data_scope": link.data_scope,
            "scope_ref": link.scope_ref,
        }
        for link in links
    ]


@router.put("/users/{user_id}/assignments")
def update_user_assignments_endpoint(
    user_id: int,
    payload: UserAssignmentsReplace,
    request: Request,
    reason: str = Depends(_required_reason),
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[dict]:
    assignments = _conflict_boundary(
        lambda: replace_user_assignments(db, user_id, payload, actor=current_user, reason=reason)
    )
    request.state.explicit_authorization_audit = True
    return [
        _assignment_summary(assignment)
        for assignment in assignments
    ]
