from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.core.enums import AssignmentStatus, ContractStatus
from app.db.base import Base
from app.models.contract import Contract
from app.models.organization import (
    ExternalAssignment,
    GovernanceScope,
    Organization,
    Position,
    UserAssignment,
)
from app.models.user import User
from app.models.workflow import WorkflowTask, WorkflowTaskAction
from app.services.contract_workflow import (
    DEPARTMENT_WORKFLOW,
    LEGAL_RISK_WORKFLOW,
    SUBSIDIARY_WORKFLOW,
    contract_node_candidates,
    contract_workflow_code,
    submission_plan,
)
from app.services.organization_catalog import seed_authorization_catalog
from app.services.workflow_engine import (
    WorkflowValidationError,
    seed_workflow_definitions,
    start_workflow,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_authorization_catalog(session)
    publisher = User(
        username="publisher",
        full_name="流程发布人",
        hashed_password="test",
        is_active=True,
        is_superuser=True,
    )
    session.add(publisher)
    session.flush()
    seed_workflow_definitions(session, publisher.id)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def add_user(db: Session, username: str) -> User:
    user = User(
        username=username,
        full_name=username,
        hashed_password="test",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def assign(
    db: Session,
    user: User,
    organization_code: str,
    position_code: str,
) -> UserAssignment:
    assignment = UserAssignment(
        user_id=user.id,
        organization_id=db.scalar(
            select(Organization.id).where(Organization.code == organization_code)
        ),
        position_id=db.scalar(select(Position.id).where(Position.code == position_code)),
        valid_from=date(2026, 1, 1),
        status=AssignmentStatus.ACTIVE,
    )
    db.add(assignment)
    db.flush()
    return assignment


def make_contract(
    db: Session,
    organization_code: str,
    company_code: str,
    position_code: str,
) -> tuple[Contract, User]:
    submitter = add_user(db, f"submitter-{organization_code}")
    initiator_assignment = assign(db, submitter, organization_code, position_code)
    contract = Contract(
        contract_no=f"WF-{organization_code}",
        title=f"{organization_code} contract",
        status=ContractStatus.DRAFT,
        created_by=submitter.id,
        company_code=company_code,
        organization_code=organization_code,
        initiator_assignment_id=initiator_assignment.id,
    )
    db.add(contract)
    db.commit()
    return contract, submitter


@pytest.mark.parametrize(
    ("organization_code", "company_code", "position_code", "workflow_code", "node_names"),
    [
        (
            "investment.general",
            "investment",
            "investment.department.junior_manager",
            DEPARTMENT_WORKFLOW,
            ["经办部门负责人", "外聘法律顾问", "法务风控部", "分管领导", "总经理", "单位主要负责人"],
        ),
        (
            "investment.legal_risk",
            "investment",
            "investment.department.junior_manager",
            LEGAL_RISK_WORKFLOW,
            ["经办部门负责人", "外聘法律顾问", "分管领导", "总经理", "单位主要负责人"],
        ),
        (
            "supplymanagement",
            "supplymanagement",
            "supply.business_handler",
            SUBSIDIARY_WORKFLOW,
            ["公司负责人", "外聘法律顾问", "法务风控部", "分管领导"],
        ),
    ],
)
def test_contract_submission_plan_matches_owner(
    db,
    organization_code,
    company_code,
    position_code,
    workflow_code,
    node_names,
):
    contract, submitter = make_contract(
        db, organization_code, company_code, position_code
    )

    plan = submission_plan(db, contract, submitter)

    assert plan.workflow_code == workflow_code
    assert plan.organization_code == organization_code
    assert [node.name for node in plan.nodes] == node_names
    assert all(node.code != "initiator" for node in plan.nodes)


def test_department_candidates_are_scoped_to_owner_and_governance_scope(db):
    contract, submitter = make_contract(
        db,
        "investment.general",
        "investment",
        "investment.department.junior_manager",
    )
    same_head = add_user(db, "same-head")
    assign(db, same_head, "investment.general", "investment.department.director")
    other_head = add_user(db, "other-head")
    assign(
        db,
        other_head,
        "investment.investment_management",
        "investment.department.director",
    )
    matching_leader = add_user(db, "matching-leader")
    matching_assignment = assign(
        db,
        matching_leader,
        "investment",
        "investment.executive.deputy_general_manager",
    )
    db.add(GovernanceScope(
        assignment_id=matching_assignment.id,
        scope_type="department",
        scope_ref="investment.general",
    ))
    other_leader = add_user(db, "other-leader")
    other_assignment = assign(
        db,
        other_leader,
        "investment",
        "investment.executive.deputy_general_manager",
    )
    db.add(GovernanceScope(
        assignment_id=other_assignment.id,
        scope_type="department",
        scope_ref="investment.asset_finance",
    ))
    db.commit()

    heads = contract_node_candidates(
        db, contract, submitter, DEPARTMENT_WORKFLOW, "department_head", date.today()
    )
    leaders = contract_node_candidates(
        db, contract, submitter, DEPARTMENT_WORKFLOW, "governance_leader", date.today()
    )

    assert {item.user_id for item in heads} == {same_head.id}
    assert {item.user_id for item in leaders} == {matching_leader.id}


def test_legal_executive_and_subsidiary_candidates_are_not_cross_scoped(db):
    contract, submitter = make_contract(
        db,
        "supplymanagement",
        "supplymanagement",
        "supply.business_handler",
    )
    supply_head = add_user(db, "supply-head")
    assign(db, supply_head, "supplymanagement", "supply.company_leader")
    fund_head = add_user(db, "fund-head")
    assign(db, fund_head, "fundmanagement", "fund.general_manager")
    legal_reviewer = add_user(db, "legal-reviewer")
    assign(
        db,
        legal_reviewer,
        "investment.legal_risk",
        "investment.duty.supply_risk_review",
    )
    legal_outsider = add_user(db, "legal-outsider")
    assign(
        db,
        legal_outsider,
        "investment.general",
        "investment.duty.supply_risk_review",
    )
    counsel = add_user(db, "counsel")
    counsel_assignment = assign(db, counsel, "external.legal", "external.legal_counsel")
    db.add(ExternalAssignment(
        assignment_id=counsel_assignment.id,
        provider_name="律所",
        service_scopes=["contract_legal_review"],
    ))
    wrong_counsel = add_user(db, "wrong-counsel")
    wrong_counsel_assignment = assign(
        db, wrong_counsel, "external.legal", "external.legal_counsel"
    )
    db.add(ExternalAssignment(
        assignment_id=wrong_counsel_assignment.id,
        provider_name="其他律所",
        service_scopes=["case_review"],
    ))
    governance = add_user(db, "supply-governance")
    governance_assignment = assign(
        db, governance, "supplymanagement", "governance.supply_leader"
    )
    db.add(GovernanceScope(
        assignment_id=governance_assignment.id,
        scope_type="company",
        scope_ref="supplymanagement",
    ))
    db.commit()

    assert {
        item.user_id
        for item in contract_node_candidates(
            db, contract, submitter, SUBSIDIARY_WORKFLOW, "company_head", date.today()
        )
    } == {supply_head.id}
    assert {
        item.user_id
        for item in contract_node_candidates(
            db, contract, submitter, SUBSIDIARY_WORKFLOW, "legal_risk", date.today()
        )
    } == {legal_reviewer.id}
    assert {
        item.user_id
        for item in contract_node_candidates(
            db, contract, submitter, SUBSIDIARY_WORKFLOW, "legal_counsel", date.today()
        )
    } == {counsel.id}
    assert {
        item.user_id
        for item in contract_node_candidates(
            db, contract, submitter, SUBSIDIARY_WORKFLOW, "governance_leader", date.today()
        )
    } == {governance.id}


def test_xinhua_contract_workflow_is_not_available(db):
    contract, _ = make_contract(
        db,
        "xinhuaproperty",
        "xinhuaproperty",
        "xinhuaproperty.department.employee",
    )

    with pytest.raises(WorkflowValidationError) as raised:
        contract_workflow_code(contract)

    assert raised.value.code == "contract_workflow_not_available"


def test_start_workflow_snapshots_initiator_assignment_and_scoped_approvers(db):
    contract, submitter = make_contract(
        db,
        "supplymanagement",
        "supplymanagement",
        "supply.business_handler",
    )
    head = add_user(db, "start-head")
    assign(db, head, "supplymanagement", "supply.company_leader")
    counsel = add_user(db, "start-counsel")
    counsel_assignment = assign(
        db, counsel, "external.legal", "external.legal_counsel"
    )
    db.add(ExternalAssignment(
        assignment_id=counsel_assignment.id,
        provider_name="律所",
        service_scopes=["contract_legal_review"],
    ))
    legal_reviewer = add_user(db, "start-legal")
    assign(
        db,
        legal_reviewer,
        "investment.legal_risk",
        "investment.duty.supply_risk_review",
    )
    governance = add_user(db, "start-governance")
    governance_assignment = assign(
        db, governance, "supplymanagement", "governance.supply_leader"
    )
    db.add(GovernanceScope(
        assignment_id=governance_assignment.id,
        scope_type="company",
        scope_ref="supplymanagement",
    ))
    db.commit()

    instance = start_workflow(
        db,
        "contract",
        contract.id,
        submitter,
        {
            "company_head": head.id,
            "legal_counsel": counsel.id,
            "legal_risk": legal_reviewer.id,
            "governance_leader": governance.id,
        },
        workflow_code=SUBSIDIARY_WORKFLOW,
    )

    tasks = list(db.scalars(
        select(WorkflowTask)
        .where(WorkflowTask.instance_id == instance.id)
        .order_by(WorkflowTask.sequence)
    ))
    initiator = tasks[0]
    action = db.scalar(
        select(WorkflowTaskAction).where(WorkflowTaskAction.task_id == initiator.id)
    )
    assert initiator.node.code == "initiator"
    assert initiator.designated_user_id == submitter.id
    assert initiator.designated_assignment_id == contract.initiator_assignment_id
    assert initiator.required_position_code == "supply.business_handler"
    assert action.organization_code == "supplymanagement"
    assert action.position_code == "supply.business_handler"
