"""统一门户应用注册表与当前用户权限快照。"""
from sqlalchemy.orm import Session

from app.core.enums import CompanyCode, ResourceCode
from app.models.user import User
from app.schemas.portal import PortalApplicationOut, PortalPermissionSnapshot
from app.services.permissions import allowed_resources, get_company_role

APPLICATIONS = (
    ("investment", "山东出版投资有限公司", "/investment", "construction"),
    ("supplymanagement", "山东出版供应链管理有限公司", "/supplymanagement", "online"),
    ("fundmanagement", "山东出版股权基金管理有限公司", "/fundmanagement", "construction"),
)


def applications_for_user(db: Session, user: User) -> list[PortalApplicationOut]:
    applications = []
    for code, company_name, route, status in APPLICATIONS:
        accessible = user.is_superuser or (
            get_company_role(db, user, CompanyCode(code)) is not None
        )
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


def permission_snapshot_for_user(
    db: Session, user: User
) -> PortalPermissionSnapshot:
    company_roles = {}
    for company in CompanyCode:
        role = get_company_role(db, user, company)
        if role is not None:
            company_roles[company.value] = role.value

    resources = sorted(
        resource.value if isinstance(resource, ResourceCode) else str(resource)
        for resource in allowed_resources(db, user, CompanyCode.SUPPLY_MANAGEMENT)
    )
    return PortalPermissionSnapshot(
        is_superuser=user.is_superuser,
        company_roles=company_roles,
        resources=resources,
    )
