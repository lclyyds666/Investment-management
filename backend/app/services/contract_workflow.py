from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.enums import AssignmentStatus, WorkflowAssigneeMode
from app.models.contract import Contract
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.models.workflow import WorkflowNode, WorkflowVersion
from app.schemas.workflow import (
    WorkflowCandidate,
    WorkflowSubmissionPlan,
    WorkflowSubmissionPlanNode,
)
from app.services.workflow_engine import (
    WorkflowValidationError,
    _active_assignments,
    _assignment_has_required_scope,
    _published_workflow,
)
from app.services.assignment_permissions import PermissionContext, has_permission


DEPARTMENT_WORKFLOW = "investment.contract.department.v1"
SUBSIDIARY_WORKFLOW = "investment.contract.subsidiary.v1"
LEGAL_RISK_WORKFLOW = "investment.contract.legal-risk.v1"

CONTRACT_WORKFLOW_CODES = frozenset({
    DEPARTMENT_WORKFLOW,
    SUBSIDIARY_WORKFLOW,
    LEGAL_RISK_WORKFLOW,
})


def contract_workflow_code(contract: Contract) -> str:
    if contract.organization_code == "investment.legal_risk":
        return LEGAL_RISK_WORKFLOW
    if contract.company_code == "investment":
        return DEPARTMENT_WORKFLOW
    if contract.company_code in {"supplymanagement", "fundmanagement", "zhanwei"}:
        return SUBSIDIARY_WORKFLOW
    raise WorkflowValidationError(
        "contract_workflow_not_available",
        "该发起组织不能提交合同审批。",
        {"organization_code": contract.organization_code},
    )


def _initiator_assignment(
    db: Session,
    contract: Contract,
    submitter: User,
    on_date: date,
) -> UserAssignment | None:
    if contract.initiator_assignment_id is None:
        if submitter.is_active and submitter.is_superuser:
            return None
        raise WorkflowValidationError(
            "invalid_contract_initiator_assignment",
            "合同发起任职已失效或与合同归属不一致，请重新选择发起组织。",
            {
                "initiator_assignment_id": None,
                "organization_code": contract.organization_code,
            },
        )
    assignment = db.scalar(
        select(UserAssignment)
        .where(UserAssignment.id == contract.initiator_assignment_id)
        .options(
            joinedload(UserAssignment.user),
            joinedload(UserAssignment.organization),
            joinedload(UserAssignment.position),
        )
    )
    if (
        assignment is None
        or assignment.user_id != submitter.id
        or assignment.status != AssignmentStatus.ACTIVE
        or not assignment.is_effective_on(on_date)
        or not assignment.user.is_active
        or not assignment.organization.is_active
        or not assignment.position.is_active
        or assignment.organization.code != contract.organization_code
        or assignment.organization.company_code != contract.company_code
    ):
        raise WorkflowValidationError(
            "invalid_contract_initiator_assignment",
            "合同发起任职已失效或与合同归属不一致，请重新选择发起组织。",
            {
                "initiator_assignment_id": contract.initiator_assignment_id,
                "organization_code": contract.organization_code,
            },
        )
    return assignment


def _workflow_node(
    db: Session,
    workflow_code: str,
    node_code: str,
) -> tuple[WorkflowVersion, WorkflowNode]:
    if workflow_code not in CONTRACT_WORKFLOW_CODES:
        raise WorkflowValidationError(
            "workflow_not_found",
            "合同审批流程不存在。",
            {"workflow_code": workflow_code},
        )
    _, version = _published_workflow(db, workflow_code)
    workflow_node = next((node for node in version.nodes if node.code == node_code), None)
    if workflow_node is None:
        raise WorkflowValidationError(
            "unknown_workflow_node",
            "The requested node is not part of the active workflow.",
            {"workflow_code": workflow_code, "node_code": node_code},
        )
    return version, workflow_node


def _matches_governance_scope(
    assignment: UserAssignment,
    scope_type: str,
    scope_ref: str,
) -> bool:
    return any(
        scope.scope_type == scope_type and scope.scope_ref == scope_ref
        for scope in assignment.governance_scopes
    )


def _matches_candidate_rule(
    assignment: UserAssignment,
    contract: Contract,
    candidate_rule: str,
) -> bool:
    if candidate_rule == "position":
        return True
    if candidate_rule == "same_department_head":
        return assignment.organization.code == contract.organization_code
    if candidate_rule == "external_legal_counsel":
        return _assignment_has_required_scope(assignment)
    if candidate_rule == "legal_risk_department":
        return assignment.organization.code == "investment.legal_risk"
    if candidate_rule == "department_governance":
        return _matches_governance_scope(
            assignment, "department", contract.organization_code
        )
    if candidate_rule == "company_head":
        return assignment.organization.code == contract.company_code
    if candidate_rule == "company_governance":
        return _matches_governance_scope(
            assignment, "company", contract.company_code
        )
    if candidate_rule == "investment_general_manager":
        return assignment.organization.code == "investment"
    if candidate_rule == "investment_chairman":
        return assignment.organization.code == "investment"
    raise WorkflowValidationError(
        "unknown_candidate_rule",
        "The workflow node has an unsupported candidate rule.",
        {"candidate_rule": candidate_rule},
    )


def _candidate_permission_code(node_code: str) -> str | None:
    if node_code in {"legal_counsel", "legal_risk"}:
        return "investment.legal.contracts.review"
    if node_code in {
        "department_head",
        "company_head",
        "governance_leader",
        "investment_general_manager",
        "investment_chairman",
    }:
        return "investment.legal.contracts.approve"
    return None


def contract_node_candidates(
    db: Session,
    contract: Contract,
    submitter: User,
    workflow_code: str,
    node_code: str,
    on_date: date,
    exclude_user_id: int | None = None,
) -> list[WorkflowCandidate]:
    if contract.workflow_route_version < 1:
        raise WorkflowValidationError(
            "contract_workflow_mismatch",
            "历史合同草稿只能使用原供应链合同审批流程。",
            {
                "workflow_code": workflow_code,
                "expected_workflow_code": "supply.contract.v2",
            },
        )
    expected_workflow_code = contract_workflow_code(contract)
    if workflow_code != expected_workflow_code:
        raise WorkflowValidationError(
            "contract_workflow_mismatch",
            "合同归属与所选审批流程不一致。",
            {
                "workflow_code": workflow_code,
                "expected_workflow_code": expected_workflow_code,
            },
        )
    _initiator_assignment(db, contract, submitter, on_date)
    _, workflow_node = _workflow_node(db, workflow_code, node_code)
    if workflow_node.auto_complete_on_submit:
        raise WorkflowValidationError(
            "workflow_node_hidden",
            "The initiator node is not selectable.",
            {"node_code": node_code},
        )
    if workflow_node.assignee_mode != WorkflowAssigneeMode.DESIGNATED_USER:
        raise WorkflowValidationError(
            "workflow_node_not_designated",
            "Candidates can only be requested for designated-user nodes.",
            {"workflow_code": workflow_code, "node_code": node_code},
        )

    position_codes = set(
        workflow_node.candidate_position_codes or [workflow_node.position_code]
    )
    permission_code = _candidate_permission_code(workflow_node.code)
    candidates: list[WorkflowCandidate] = []
    seen_users: set[int] = set()
    for assignment in _active_assignments(db, position_codes, on_date):
        if (
            assignment.user_id == submitter.id
            or assignment.user_id == exclude_user_id
            or assignment.user_id in seen_users
            or not _assignment_has_required_scope(assignment)
            or not _matches_candidate_rule(
                assignment, contract, workflow_node.candidate_rule
            )
            or (
                permission_code is not None
                and not has_permission(
                    db,
                    assignment.user,
                    permission_code,
                    PermissionContext(
                        company_code="investment",
                        assigned_user_id=assignment.user_id,
                    ),
                )
            )
        ):
            continue
        seen_users.add(assignment.user_id)
        candidates.append(WorkflowCandidate(
            user_id=assignment.user_id,
            full_name=assignment.user.full_name,
            assignment_id=assignment.id,
            organization_code=assignment.organization.code,
            organization_name=assignment.organization.name,
            position_code=assignment.position.code,
            position_name=assignment.position.name,
            valid_from=assignment.valid_from,
            valid_until=assignment.valid_until,
        ))
    return candidates


def submission_plan(
    db: Session,
    contract: Contract,
    submitter: User,
) -> WorkflowSubmissionPlan:
    if contract.workflow_route_version < 1:
        workflow_code = "supply.contract.v2"
    else:
        workflow_code = contract_workflow_code(contract)
        _initiator_assignment(db, contract, submitter, date.today())
    definition, version = _published_workflow(db, workflow_code)
    organization_name = db.scalar(
        select(Organization.name).where(
            Organization.code == contract.organization_code
        )
    )
    if organization_name is None:
        raise WorkflowValidationError(
            "contract_organization_not_found",
            "合同发起组织不存在。",
            {"organization_code": contract.organization_code},
        )
    visible_nodes = [
        node
        for node in sorted(version.nodes, key=lambda item: item.sequence)
        if not node.auto_complete_on_submit
        and (
            contract.workflow_route_version >= 1
            or node.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER
        )
    ]
    position_codes = {
        node.position_code for node in visible_nodes if node.position_code
    }
    position_names = dict(db.execute(
        select(Position.code, Position.name).where(Position.code.in_(position_codes))
    ).all())
    return WorkflowSubmissionPlan(
        workflow_code=workflow_code,
        workflow_name=definition.name,
        organization_code=contract.organization_code,
        organization_name=organization_name,
        nodes=[
            WorkflowSubmissionPlanNode(
                code=node.code,
                name=node.name,
                position_code=node.position_code,
                position_name=position_names.get(node.position_code, node.name),
                candidate_rule=node.candidate_rule,
            )
            for node in visible_nodes
        ],
    )


def validate_submission_assignments(
    db: Session,
    contract: Contract,
    submitter: User,
    version: WorkflowVersion,
    designated_users: dict[str, int],
    submitted_on: date,
) -> tuple[UserAssignment | None, dict[str, UserAssignment]]:
    if contract.workflow_route_version < 1:
        raise WorkflowValidationError(
            "contract_workflow_mismatch",
            "历史合同草稿只能使用原供应链合同审批流程。",
            {"expected_workflow_code": "supply.contract.v2"},
        )
    workflow_code = contract_workflow_code(contract)
    if version.definition.code != workflow_code:
        raise WorkflowValidationError(
            "contract_workflow_mismatch",
            "合同归属与所选审批流程不一致。",
            {
                "workflow_code": version.definition.code,
                "expected_workflow_code": workflow_code,
            },
        )
    initiator_assignment = _initiator_assignment(
        db, contract, submitter, submitted_on
    )
    visible_nodes = {
        node.code: node
        for node in version.nodes
        if not node.auto_complete_on_submit
        and node.assignee_mode == WorkflowAssigneeMode.DESIGNATED_USER
    }
    missing_codes = sorted(set(visible_nodes) - set(designated_users))
    if missing_codes:
        raise WorkflowValidationError(
            "missing_designated_user",
            "Every designated workflow node requires one selected user.",
            {"node_codes": missing_codes},
        )
    unknown_codes = sorted(set(designated_users) - set(visible_nodes))
    if unknown_codes:
        raise WorkflowValidationError(
            "unknown_designated_node",
            "Selected users include nodes that are not designated in this workflow.",
            {"node_codes": unknown_codes},
        )
    selected_user_ids = list(designated_users.values())
    if (
        len(set(selected_user_ids)) != len(selected_user_ids)
        or submitter.id in selected_user_ids
    ):
        raise WorkflowValidationError(
            "duplicate_workflow_actor",
            "One person cannot occupy two nodes in the same workflow.",
        )

    selected_assignments: dict[str, UserAssignment] = {}
    if initiator_assignment is not None:
        selected_assignments["initiator"] = initiator_assignment
    for node_code, user_id in designated_users.items():
        candidates = contract_node_candidates(
            db,
            contract,
            submitter,
            workflow_code,
            node_code,
            submitted_on,
        )
        candidate = next(
            (item for item in candidates if item.user_id == user_id), None
        )
        if candidate is None:
            raise WorkflowValidationError(
                "ineligible_designated_user",
                "The selected user is no longer eligible for the designated node.",
                {"node_code": node_code, "user_id": user_id},
            )
        assignment = db.get(UserAssignment, candidate.assignment_id)
        if assignment is None:
            raise WorkflowValidationError(
                "ineligible_designated_user",
                "The selected user is no longer eligible for the designated node.",
                {"node_code": node_code, "user_id": user_id},
            )
        selected_assignments[node_code] = assignment
    return initiator_assignment, selected_assignments
