from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import CompanyCode, ResourceCode, Role
from app.models.portal import UserCompanyRole
from app.models.user import User


SUPPLY_RESOURCE_ROLES: dict[ResourceCode, frozenset[Role]] = {
    ResourceCode.SUPPLY_DASHBOARD: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR,
        Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_OPERATION: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.FINANCE_HANDLER,
        Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SCENIC_ANALYTICS: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.FINANCE_HANDLER,
        Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_FINANCE: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.FINANCE_HANDLER,
        Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_CONTRACT: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR, Role.LEGAL_COUNSEL,
    }),
    ResourceCode.SUPPLY_APPROVAL: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR,
        Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_CUSTOMER: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR,
        Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_ADMIN: frozenset({Role.INFO_MAINTAINER}),
}


def get_company_role(db: Session, user: User, company: CompanyCode) -> Role | None:
    return db.scalar(
        select(UserCompanyRole.role).where(
            UserCompanyRole.user_id == user.id,
            UserCompanyRole.company_code == company.value,
        )
    )


def allowed_resources(
    db: Session, user: User, company: CompanyCode
) -> frozenset[ResourceCode]:
    if user.is_superuser:
        return frozenset(SUPPLY_RESOURCE_ROLES)
    if company != CompanyCode.SUPPLY_MANAGEMENT:
        return frozenset()

    company_role = get_company_role(db, user, company)
    if company_role is None:
        return frozenset()

    return frozenset(
        resource
        for resource, allowed_roles in SUPPLY_RESOURCE_ROLES.items()
        if company_role in allowed_roles
    )


def has_resource(
    db: Session, user: User, company: CompanyCode, resource: ResourceCode
) -> bool:
    return resource in allowed_resources(db, user, company)
