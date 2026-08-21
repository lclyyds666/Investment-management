from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import OrganizationType
from app.models.organization import Organization
from app.models.user import User
from app.services.assignment_permissions import active_assignments

LegalResource = Literal["contract", "case"]


@dataclass(frozen=True)
class LegalInitiatorOption:
    assignment_id: int | None
    company_code: str
    company_name: str
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


@dataclass(frozen=True)
class LegalOwnership:
    company_code: str
    organization_code: str
    initiator_assignment_id: int | None


class LegalOwnershipError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


CONTRACT_COMPANIES = frozenset({"investment", "supplymanagement", "fundmanagement", "zhanwei"})
CASE_COMPANIES = CONTRACT_COMPANIES | frozenset({"xinhuaproperty"})


def _allowed_companies(resource: LegalResource) -> frozenset[str]:
    if resource == "contract":
        return CONTRACT_COMPANIES
    if resource == "case":
        return CASE_COMPANIES
    raise LegalOwnershipError("invalid_resource", "不支持的法务资源类型")


def _company_names(db: Session, company_codes: set[str]) -> dict[str, str]:
    if not company_codes:
        return {}
    return {
        organization.code: organization.name
        for organization in db.scalars(
            select(Organization).where(
                Organization.code.in_(company_codes),
                Organization.organization_type == OrganizationType.COMPANY,
            )
        )
    }


def legal_initiator_options(
    db: Session, user: User, resource: LegalResource
) -> list[LegalInitiatorOption]:
    allowed_companies = _allowed_companies(resource)
    if not user.is_active:
        return []

    if user.is_superuser:
        organizations = db.scalars(
            select(Organization).where(
                Organization.is_active.is_(True),
                Organization.organization_type != OrganizationType.EXTERNAL,
                Organization.company_code.in_(allowed_companies),
                Organization.code != "investment",
            ).order_by(Organization.sort_order, Organization.code)
        ).all()
        company_names = _company_names(
            db,
            {
                organization.company_code
                for organization in organizations
                if organization.company_code is not None
            },
        )
        return [
            LegalInitiatorOption(
                assignment_id=None,
                company_code=organization.company_code,
                company_name=company_names.get(
                    organization.company_code, organization.name
                ),
                organization_code=organization.code,
                organization_name=organization.name,
                position_code="",
                position_name="",
            )
            for organization in organizations
        ]

    assignments = [
        assignment
        for assignment in active_assignments(db, user.id)
        if assignment.organization.organization_type != OrganizationType.EXTERNAL
        and assignment.organization.company_code in allowed_companies
    ]
    company_names = _company_names(
        db,
        {
            assignment.organization.company_code
            for assignment in assignments
            if assignment.organization.company_code is not None
        },
    )
    options = [
        LegalInitiatorOption(
            assignment_id=assignment.id,
            company_code=assignment.organization.company_code,
            company_name=company_names.get(
                assignment.organization.company_code, assignment.organization.name
            ),
            organization_code=assignment.organization.code,
            organization_name=assignment.organization.name,
            position_code=assignment.position.code,
            position_name=assignment.position.name,
        )
        for assignment in assignments
    ]
    return sorted(
        options,
        key=lambda item: (
            item.company_code,
            item.organization_code,
            item.position_code,
            item.assignment_id,
        ),
    )


def resolve_legal_ownership(
    db: Session,
    user: User,
    resource: LegalResource,
    initiator_assignment_id: int | None,
    organization_code: str | None,
) -> LegalOwnership:
    allowed_companies = _allowed_companies(resource)
    if not user.is_active:
        raise LegalOwnershipError("inactive_user", "当前用户已停用")

    if user.is_superuser:
        if initiator_assignment_id is not None:
            raise LegalOwnershipError(
                "invalid_initiator_assignment", "超级管理员代录不能指定用户任职"
            )
        organization = db.scalar(
            select(Organization).where(
                Organization.code == organization_code,
                Organization.is_active.is_(True),
                Organization.organization_type != OrganizationType.EXTERNAL,
            )
        )
        if (
            organization is None
            or organization.code == "investment"
            or organization.company_code not in allowed_companies
        ):
            raise LegalOwnershipError("invalid_organization", "发起组织不可用于该法务资源")
        return LegalOwnership(
            company_code=organization.company_code,
            organization_code=organization.code,
            initiator_assignment_id=None,
        )

    options = legal_initiator_options(db, user, resource)
    if initiator_assignment_id is None and len(options) == 1:
        initiator_assignment_id = options[0].assignment_id
    option = next(
        (
            item
            for item in options
            if item.assignment_id == initiator_assignment_id
        ),
        None,
    )
    if option is None:
        raise LegalOwnershipError(
            "invalid_initiator_assignment", "所选发起任职不属于当前用户或已失效"
        )
    if organization_code is not None and organization_code != option.organization_code:
        raise LegalOwnershipError("invalid_organization", "发起组织与所选任职不一致")
    return LegalOwnership(
        company_code=option.company_code,
        organization_code=option.organization_code,
        initiator_assignment_id=option.assignment_id,
    )
