from sqlalchemy.orm import Session

from app.core.enums import CompanyCode, ResourceCode, Role
from app.models.user import User
from app.services.assignment_permissions import (
    PermissionContext,
    active_assignments,
    has_permission,
    has_position,
)
from app.services.legacy_assignment_migration import LEGACY_TARGETS


RESOURCE_VIEW_PERMISSIONS: dict[ResourceCode, str] = {
    ResourceCode.INVEST_LEGAL_DASHBOARD: "investment.legal.dashboard.view",
    ResourceCode.INVEST_LEGAL_CASES: "investment.legal.cases.view",
    ResourceCode.INVEST_LEGAL_CONTRACTS: "investment.legal.contracts.view",
    ResourceCode.INVEST_LEGAL_ALERTS: "investment.legal.alerts.view",
    ResourceCode.INVEST_LEGAL_STATISTICS: "investment.legal.statistics.view",
    ResourceCode.INVEST_LEGAL_ADMIN: "investment.legal.admin.view",
    ResourceCode.SUPPLY_DASHBOARD: "supply.dashboard.view",
    ResourceCode.SUPPLY_OPERATION: "supply.operation.view",
    ResourceCode.SCENIC_ANALYTICS: "supply.scenic.view",
    ResourceCode.SUPPLY_FINANCE: "supply.finance.view",
    ResourceCode.SUPPLY_CONTRACT: "supply.contract.view",
    ResourceCode.SUPPLY_APPROVAL: "supply.approval.view",
    ResourceCode.SUPPLY_CUSTOMER: "supply.customer.view",
}

COMPANY_RESOURCE_PERMISSIONS: dict[CompanyCode, dict[ResourceCode, str]] = {
    CompanyCode.INVESTMENT: {
        resource: permission_code
        for resource, permission_code in RESOURCE_VIEW_PERMISSIONS.items()
        if resource.value.startswith("invest.legal.")
    },
    CompanyCode.SUPPLY_MANAGEMENT: {
        resource: permission_code
        for resource, permission_code in RESOURCE_VIEW_PERMISSIONS.items()
        if resource.value.startswith("supply.")
    },
}

INVESTMENT_MANAGEMENT_POSITION_CODES = frozenset({
    "investment.executive.chairman",
    "investment.executive.general_manager",
    "investment.executive.deputy_general_manager",
    "governance.supply_leader",
})
INVESTMENT_BUSINESS_POSITION_CODES = frozenset({
    "investment.department.director",
    "investment.department.deputy_director",
    "investment.department.senior_manager",
    "investment.department.middle_manager",
    "investment.department.junior_manager",
    "supply.business_handler",
    "supply.business_reviewer",
    "supply.finance_handler",
    "supply.company_leader",
    "investment.duty.supply_risk_review",
    "investment.duty.supply_finance_review",
})
INVESTMENT_COUNSEL_POSITION_CODES = frozenset({"external.legal_counsel"})
INVESTMENT_LEGAL_POSITION_CODES = (
    INVESTMENT_MANAGEMENT_POSITION_CODES
    | INVESTMENT_BUSINESS_POSITION_CODES
    | INVESTMENT_COUNSEL_POSITION_CODES
)


def investment_role_for_assignments(assignments) -> Role | None:
    """Map normalized legal-risk assignments to the legacy capability profiles."""
    position_codes = {assignment.position.code for assignment in assignments}
    if position_codes & INVESTMENT_MANAGEMENT_POSITION_CODES:
        return Role.INVEST_DIRECTOR
    if position_codes & INVESTMENT_COUNSEL_POSITION_CODES:
        return Role.LEGAL_COUNSEL
    if position_codes & INVESTMENT_BUSINESS_POSITION_CODES:
        return Role.BUSINESS_HANDLER
    return None


def get_company_role(db: Session, user: User, company: CompanyCode) -> Role | None:
    if company == CompanyCode.INVESTMENT:
        return investment_role_for_assignments(active_assignments(db, user.id))
    if company == CompanyCode.SUPPLY_MANAGEMENT:
        for role, target in LEGACY_TARGETS.items():
            if has_position(db, user.id, target.position_code):
                return role
    return None


def allowed_resources(
    db: Session, user: User, company: CompanyCode
) -> frozenset[ResourceCode]:
    resource_permissions = COMPANY_RESOURCE_PERMISSIONS.get(company)
    if resource_permissions is None:
        return frozenset()
    if user.is_superuser and user.is_active:
        return frozenset(resource_permissions)
    return frozenset(
        resource
        for resource, permission_code in resource_permissions.items()
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
