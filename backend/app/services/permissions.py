from sqlalchemy.orm import Session

from app.core.enums import CompanyCode, ResourceCode, Role
from app.models.user import User
from app.services.assignment_permissions import PermissionContext, has_permission, has_position
from app.services.legacy_assignment_migration import LEGACY_TARGETS


RESOURCE_VIEW_PERMISSIONS: dict[ResourceCode, str] = {
    ResourceCode.SUPPLY_DASHBOARD: "supply.dashboard.view",
    ResourceCode.SUPPLY_OPERATION: "supply.operation.view",
    ResourceCode.SCENIC_ANALYTICS: "supply.scenic.view",
    ResourceCode.SUPPLY_FINANCE: "supply.finance.view",
    ResourceCode.SUPPLY_CONTRACT: "supply.contract.view",
    ResourceCode.SUPPLY_APPROVAL: "supply.approval.view",
    ResourceCode.SUPPLY_CUSTOMER: "supply.customer.view",
}


def get_company_role(db: Session, user: User, company: CompanyCode) -> Role | None:
    if company != CompanyCode.SUPPLY_MANAGEMENT:
        return None
    for role, target in LEGACY_TARGETS.items():
        if has_position(db, user.id, target.position_code):
            return role
    return None


def allowed_resources(
    db: Session, user: User, company: CompanyCode
) -> frozenset[ResourceCode]:
    if company != CompanyCode.SUPPLY_MANAGEMENT:
        return frozenset()
    return frozenset(
        resource
        for resource, permission_code in RESOURCE_VIEW_PERMISSIONS.items()
        if has_permission(
            db,
            user,
            permission_code,
            PermissionContext(company_code=company.value),
        )
    )


def has_resource(
    db: Session, user: User, company: CompanyCode, resource: ResourceCode
) -> bool:
    return resource in allowed_resources(db, user, company)
