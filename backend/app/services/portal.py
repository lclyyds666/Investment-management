"""统一门户应用注册表与当前用户权限快照。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import CompanyCode, DataScope
from app.models.organization import Permission
from app.models.user import User
from app.schemas.portal import (
    AssignmentSnapshotOut,
    PermissionGrantOut,
    PortalApplicationOut,
    PortalPermissionSnapshot,
)
from app.services.assignment_permissions import active_assignments, permission_grants
from app.services.legacy_assignment_migration import LEGACY_TARGETS
from app.services.permissions import RESOURCE_VIEW_PERMISSIONS

APPLICATIONS = (
    (
        "investment",
        "山东出版投资有限公司",
        "/investment",
        "construction",
        "investment.portal.enter",
    ),
    (
        "supplymanagement",
        "山东出版供应链管理有限公司",
        "/supplymanagement",
        "online",
        "supply.portal.enter",
    ),
    (
        "fundmanagement",
        "山东出版股权基金管理有限公司",
        "/fundmanagement",
        "construction",
        "fund.portal.enter",
    ),
)


def applications_for_user(db: Session, user: User) -> list[PortalApplicationOut]:
    platform_permissions = set()
    if not user.is_superuser:
        platform_permissions = {
            grant.code
            for grant in permission_grants(db, user.id)
            if grant.data_scope == DataScope.PLATFORM
        }
    enabled_superuser = bool(user.is_superuser and user.is_active)
    applications = []
    for code, company_name, route, status, enter_permission in APPLICATIONS:
        accessible = enabled_superuser or enter_permission in platform_permissions
        applications.append(
            PortalApplicationOut(
                code=code,
                company_name=company_name,
                route=route,
                status=status,
                accessible=accessible,
                denial_reason=None if accessible else "暂时无访问权限",
            )
        )
    return applications


def _legacy_company_roles(assignments) -> dict[str, str]:
    roles_by_company: dict[str, set[str]] = {}
    targets_by_position = {}
    for role, target in LEGACY_TARGETS.items():
        targets_by_position.setdefault(target.position_code, []).append((role, target))

    for assignment in assignments:
        legacy_targets = targets_by_position.get(assignment.position.code, [])
        if len(legacy_targets) != 1:
            continue
        role, _ = legacy_targets[0]
        roles_by_company.setdefault(CompanyCode.SUPPLY_MANAGEMENT.value, set()).add(
            role.value
        )

    return {
        company_code: next(iter(roles))
        for company_code, roles in roles_by_company.items()
        if len(roles) == 1
    }


def permission_snapshot_for_user(
    db: Session, user: User
) -> PortalPermissionSnapshot:
    if user.is_superuser:
        if user.is_active:
            permission_codes = list(db.scalars(
                select(Permission.code)
                .where(Permission.is_active.is_(True))
                .order_by(Permission.code)
            ))
            return PortalPermissionSnapshot(
                is_superuser=True,
                assignments=[],
                permissions=[
                    PermissionGrantOut(
                        code=code,
                        data_scope=DataScope.PLATFORM.value,
                        scope_ref="",
                    )
                    for code in permission_codes
                ],
                resources=sorted(resource.value for resource in RESOURCE_VIEW_PERMISSIONS),
                company_roles={},
            )
        return PortalPermissionSnapshot(
            is_superuser=True,
            assignments=[],
            permissions=[],
            resources=[],
            company_roles={},
        )

    assignments = sorted(
        active_assignments(db, user.id),
        key=lambda assignment: (
            assignment.organization.sort_order,
            assignment.position.code,
            assignment.id,
        ),
    )
    grants = sorted(
        {
            (grant.code, grant.data_scope.value, grant.scope_ref)
            for grant in permission_grants(db, user.id)
        }
    )
    view_resources = {
        permission_code: resource.value
        for resource, permission_code in RESOURCE_VIEW_PERMISSIONS.items()
    }

    return PortalPermissionSnapshot(
        is_superuser=False,
        assignments=[
            AssignmentSnapshotOut(
                assignment_id=assignment.id,
                organization_code=assignment.organization.code,
                organization_name=assignment.organization.name,
                position_code=assignment.position.code,
                position_name=assignment.position.name,
                valid_from=assignment.valid_from,
                valid_until=assignment.valid_until,
            )
            for assignment in assignments
        ],
        permissions=[
            PermissionGrantOut(
                code=code,
                data_scope=data_scope,
                scope_ref=scope_ref,
            )
            for code, data_scope, scope_ref in grants
        ],
        resources=sorted(
            {
                view_resources[code]
                for code, _, _ in grants
                if code in view_resources
            }
        ),
        company_roles=_legacy_company_roles(assignments),
    )
