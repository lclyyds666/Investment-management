"""法务风控能力矩阵与案件数据范围。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import Role
from app.db.session import get_db
from app.models.legal_risk import LegalCase
from app.models.user import User
from app.services.assignment_permissions import PermissionContext, active_assignments, has_permission
from app.services.legal_record_scope import LegalRecordScope, case_access_predicate, legal_record_scope
from app.services.permissions import (
    INVESTMENT_BUSINESS_POSITION_CODES,
    INVESTMENT_COUNSEL_POSITION_CODES,
    INVESTMENT_MANAGEMENT_POSITION_CODES,
)


class LegalCapability(str, Enum):
    VIEW_CASE = "view_case"
    CREATE_CASE = "create_case"
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
    record_scope: LegalRecordScope | None = None

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


CAPABILITY_PERMISSION_CODES = {
    LegalCapability.VIEW_CASE: ("investment.legal.cases.view",),
    LegalCapability.CREATE_CASE: ("investment.legal.cases.create",),
    LegalCapability.EDIT_CASE: ("investment.legal.cases.update",),
    LegalCapability.ACTIVATE_CASE: ("investment.legal.cases.update",),
    LegalCapability.MANAGE_DETAIL: ("investment.legal.cases.update",),
    LegalCapability.ADD_COUNSEL_CONTENT: ("investment.legal.cases.review",),
    LegalCapability.UPLOAD_ATTACHMENT: (
        "investment.legal.cases.update",
        "investment.legal.cases.review",
    ),
    LegalCapability.DELETE_ATTACHMENT: (
        "investment.legal.cases.delete",
        "investment.legal.cases.review",
    ),
    LegalCapability.MANAGE_ALERT: ("investment.legal.alerts.update",),
    LegalCapability.ARCHIVE_CASE: ("investment.legal.cases.delete",),
    LegalCapability.VIEW_STATISTICS: ("investment.legal.statistics.view",),
    LegalCapability.IMPORT_EXPORT: ("investment.legal.cases.import",),
    LegalCapability.EXPORT_MANAGEMENT: ("investment.legal.cases.export",),
    LegalCapability.ADMIN: ("investment.legal.admin.view",),
}


def _permission_contexts(db: Session, user: User) -> tuple[PermissionContext, ...]:
    contexts = [
        PermissionContext(
            company_code="investment",
            assigned_user_id=user.id,
            participant_ids=frozenset({user.id}),
        )
    ]
    for assignment in active_assignments(db, user.id):
        organization = assignment.organization
        contexts.append(PermissionContext(
            company_code=organization.company_code,
            department_code=(
                organization.code
                if organization.organization_type.value == "department"
                else None
            ),
            assigned_user_id=user.id,
            participant_ids=frozenset({user.id}),
        ))
    return tuple(contexts)


def capabilities_from_permissions(db: Session, user: User) -> frozenset[LegalCapability]:
    if user.is_superuser:
        return FULL_CAPABILITIES if user.is_active else frozenset()
    contexts = _permission_contexts(db, user)
    return frozenset(
        capability
        for capability, permission_codes in CAPABILITY_PERMISSION_CODES.items()
        if any(
            has_permission(db, user, permission_code, context)
            for permission_code in permission_codes
            for context in contexts
        )
    )


def access_context(db: Session, user: User) -> LegalAccessContext:
    assignments = active_assignments(db, user.id)
    position_codes = frozenset(assignment.position.code for assignment in assignments)
    capabilities = capabilities_from_permissions(db, user)
    if not capabilities:
        raise HTTPException(status_code=403, detail="权限不足")
    return LegalAccessContext(
        user_id=user.id,
        role=None,
        is_superuser=user.is_superuser,
        capabilities=capabilities,
        position_codes=position_codes,
        record_scope=legal_record_scope(db, user),
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
    scope = context.record_scope or LegalRecordScope(
        user_id=context.user_id,
        global_access=context.is_superuser,
        company_codes=frozenset(),
        organization_codes=frozenset(),
    )
    return case_access_predicate(scope)


def can_access_case(db: Session, case: LegalCase, context: LegalAccessContext) -> bool:
    from app.services.legal_record_scope import can_access_case as scope_can_access_case

    scope = context.record_scope or LegalRecordScope(
        user_id=context.user_id,
        global_access=context.is_superuser,
        company_codes=frozenset(),
        organization_codes=frozenset(),
    )
    return scope_can_access_case(db, case, scope)
