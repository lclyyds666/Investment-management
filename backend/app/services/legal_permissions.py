"""法务风控能力矩阵与案件数据范围。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from fastapi import Depends, HTTPException
from sqlalchemy import exists, false, or_, true
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import CompanyCode, Role
from app.db.session import get_db
from app.models.legal_risk import LegalCase, LegalCaseCollaborator, LegalCollaboratorType
from app.models.user import User
from app.services.legal_clock import legal_now
from app.services.assignment_permissions import active_assignments
from app.services.permissions import (
    INVESTMENT_BUSINESS_POSITION_CODES,
    INVESTMENT_COUNSEL_POSITION_CODES,
    INVESTMENT_MANAGEMENT_POSITION_CODES,
    get_company_role,
)


class LegalCapability(str, Enum):
    VIEW_CASE = "view_case"
    EDIT_CASE = "edit_case"
    ACTIVATE_CASE = "activate_case"
    MANAGE_DETAIL = "manage_detail"
    ADD_COUNSEL_CONTENT = "add_counsel_content"
    UPLOAD_ATTACHMENT = "upload_attachment"
    DELETE_ATTACHMENT = "delete_attachment"
    MANAGE_ALERT = "manage_alert"
    ARCHIVE_CASE = "archive_case"
    VIEW_STATISTICS = "view_statistics"
    IMPORT_EXPORT = "import_export"
    EXPORT_MANAGEMENT = "export_management"
    ADMIN = "admin"


FULL_CAPABILITIES = frozenset(LegalCapability)
BUSINESS_CAPABILITIES = FULL_CAPABILITIES - frozenset({LegalCapability.ADMIN})
MANAGEMENT_CAPABILITIES = frozenset({
    LegalCapability.VIEW_CASE,
    LegalCapability.VIEW_STATISTICS,
    LegalCapability.EXPORT_MANAGEMENT,
})
COUNSEL_CAPABILITIES = frozenset({
    LegalCapability.VIEW_CASE,
    LegalCapability.ADD_COUNSEL_CONTENT,
    LegalCapability.UPLOAD_ATTACHMENT,
    LegalCapability.DELETE_ATTACHMENT,
    LegalCapability.MANAGE_ALERT,
})

GENERAL_ROLES = frozenset({
    Role.BUSINESS_HANDLER,
    Role.BUSINESS_REVIEWER,
    Role.RISK_AUDITOR,
    Role.FINANCE_HANDLER,
    Role.FINANCE_REVIEWER,
    Role.SCM_DIRECTOR,
})


@dataclass(frozen=True)
class LegalAccessContext:
    user_id: int
    role: Role | None
    is_superuser: bool
    capabilities: frozenset[LegalCapability]
    position_codes: frozenset[str] = frozenset()

    def has(self, capability: LegalCapability) -> bool:
        return capability in self.capabilities


def capabilities_for(role: Role | None, *, is_superuser: bool = False) -> frozenset[LegalCapability]:
    if is_superuser:
        return FULL_CAPABILITIES
    if role in GENERAL_ROLES:
        return BUSINESS_CAPABILITIES
    if role == Role.INVEST_DIRECTOR:
        return MANAGEMENT_CAPABILITIES
    if role == Role.LEGAL_COUNSEL:
        return COUNSEL_CAPABILITIES
    return frozenset()


def capabilities_for_positions(position_codes: set[str] | frozenset[str], *, is_superuser: bool = False) -> frozenset[LegalCapability]:
    if is_superuser:
        return FULL_CAPABILITIES
    capabilities: set[LegalCapability] = set()
    if position_codes & INVESTMENT_BUSINESS_POSITION_CODES:
        capabilities.update(BUSINESS_CAPABILITIES)
    if position_codes & INVESTMENT_MANAGEMENT_POSITION_CODES:
        capabilities.update(MANAGEMENT_CAPABILITIES)
    if position_codes & INVESTMENT_COUNSEL_POSITION_CODES:
        capabilities.update(COUNSEL_CAPABILITIES)
    return frozenset(capabilities)


def access_context(db: Session, user: User) -> LegalAccessContext:
    assignments = active_assignments(db, user.id)
    position_codes = frozenset(assignment.position.code for assignment in assignments)
    role = None if user.is_superuser else get_company_role(db, user, CompanyCode.INVESTMENT)
    capabilities = capabilities_for_positions(position_codes, is_superuser=user.is_superuser)
    if not capabilities:
        raise HTTPException(status_code=403, detail="权限不足")
    return LegalAccessContext(
        user_id=user.id,
        role=role,
        is_superuser=user.is_superuser,
        capabilities=capabilities,
        position_codes=position_codes,
    )


def require_legal_capability(capability: LegalCapability):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        context = access_context(db, current_user)
        if not context.has(capability):
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user

    return checker


def accessible_case_predicate(context: LegalAccessContext):
    if context.is_superuser or context.position_codes & (INVESTMENT_BUSINESS_POSITION_CODES | INVESTMENT_MANAGEMENT_POSITION_CODES):
        return true()
    if context.role == Role.LEGAL_COUNSEL:
        now = legal_now()
        return exists().where(
            LegalCaseCollaborator.case_id == LegalCase.id,
            LegalCaseCollaborator.user_id == context.user_id,
            LegalCaseCollaborator.collaborator_type == LegalCollaboratorType.LEGAL_COUNSEL,
            LegalCaseCollaborator.effective_at <= now,
            or_(
                LegalCaseCollaborator.expires_at.is_(None),
                LegalCaseCollaborator.expires_at > now,
            ),
        )
    return false()


def can_access_case(db: Session, case: LegalCase, context: LegalAccessContext) -> bool:
    if context.is_superuser or context.position_codes & (INVESTMENT_BUSINESS_POSITION_CODES | INVESTMENT_MANAGEMENT_POSITION_CODES):
        return True
    if context.role != Role.LEGAL_COUNSEL:
        return False
    now = legal_now()
    return bool(db.scalar(
        exists().where(
            LegalCaseCollaborator.case_id == case.id,
            LegalCaseCollaborator.user_id == context.user_id,
            LegalCaseCollaborator.collaborator_type == LegalCollaboratorType.LEGAL_COUNSEL,
            LegalCaseCollaborator.effective_at <= now,
            or_(
                LegalCaseCollaborator.expires_at.is_(None),
                LegalCaseCollaborator.expires_at > now,
            ),
        ).select()
    ))
