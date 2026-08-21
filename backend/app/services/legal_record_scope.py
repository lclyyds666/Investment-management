from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, false, or_, select, true
from sqlalchemy.orm import Session

from app.core.enums import OrganizationType, WorkflowTargetType
from app.models.approval import Approval
from app.models.contract import Contract
from app.models.legal_risk import LegalCase, LegalCaseCollaborator
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowTask, WorkflowTaskAction
from app.services.assignment_permissions import active_assignments
from app.services.legal_clock import legal_now


@dataclass(frozen=True)
class LegalRecordScope:
    user_id: int
    global_access: bool
    company_codes: frozenset[str]
    organization_codes: frozenset[str]


def legal_record_scope(db: Session, user: User) -> LegalRecordScope:
    assignments = active_assignments(db, user.id)
    legal_department = any(
        assignment.organization.code == "investment.legal_risk"
        for assignment in assignments
    )
    company_codes = frozenset(
        assignment.organization.company_code
        for assignment in assignments
        if assignment.organization.company_code
        and assignment.organization.code != "investment.legal_risk"
        and (
            assignment.organization.organization_type == OrganizationType.COMPANY
            or assignment.organization.company_code != "investment"
        )
    )
    organization_codes = frozenset(
        assignment.organization.code
        for assignment in assignments
        if assignment.organization.organization_type == OrganizationType.DEPARTMENT
        and assignment.organization.code != "investment.legal_risk"
    )
    return LegalRecordScope(
        user_id=user.id,
        global_access=bool(user.is_active and user.is_superuser) or legal_department,
        company_codes=company_codes,
        organization_codes=organization_codes,
    )


def _contract_workflow_participation(scope: LegalRecordScope):
    return exists().where(
        WorkflowInstance.target_type == WorkflowTargetType.CONTRACT,
        WorkflowInstance.target_id == Contract.id,
        or_(
            WorkflowInstance.submitted_by == scope.user_id,
            exists().where(
                WorkflowTask.instance_id == WorkflowInstance.id,
                or_(
                    WorkflowTask.designated_user_id == scope.user_id,
                    exists().where(
                        WorkflowTaskAction.task_id == WorkflowTask.id,
                        WorkflowTaskAction.actor_id == scope.user_id,
                    ),
                ),
            ),
        ),
    )


def contract_access_predicate(scope: LegalRecordScope):
    if scope.global_access:
        return true()
    predicates = [
        exists().where(
            Approval.contract_id == Contract.id,
            Approval.approver_id == scope.user_id,
        ),
        _contract_workflow_participation(scope),
    ]
    if scope.company_codes:
        predicates.append(Contract.company_code.in_(scope.company_codes))
    if scope.organization_codes:
        predicates.append(Contract.organization_code.in_(scope.organization_codes))
    return or_(*predicates) if predicates else false()


def case_access_predicate(scope: LegalRecordScope):
    if scope.global_access:
        return true()
    now = legal_now()
    predicates = [
        exists().where(
            LegalCaseCollaborator.case_id == LegalCase.id,
            LegalCaseCollaborator.user_id == scope.user_id,
            LegalCaseCollaborator.effective_at <= now,
            or_(
                LegalCaseCollaborator.expires_at.is_(None),
                LegalCaseCollaborator.expires_at > now,
            ),
        )
    ]
    if scope.company_codes:
        predicates.append(LegalCase.company_code.in_(scope.company_codes))
    if scope.organization_codes:
        predicates.append(LegalCase.organization_code.in_(scope.organization_codes))
    return or_(*predicates) if predicates else false()


def can_access_contract(db: Session, contract: Contract, scope: LegalRecordScope) -> bool:
    return bool(db.scalar(select(exists().where(
        Contract.id == contract.id,
        contract_access_predicate(scope),
    ))))


def can_access_case(db: Session, case: LegalCase, scope: LegalRecordScope) -> bool:
    return bool(db.scalar(select(exists().where(
        LegalCase.id == case.id,
        LegalCase.deleted_at.is_(None),
        case_access_predicate(scope),
    ))))
