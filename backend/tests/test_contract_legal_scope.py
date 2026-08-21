from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.enums import ApprovalAction, AssignmentStatus, OrganizationType, PositionCategory, Role
from app.db.base import Base
from app.models.contract import Contract
from app.models.customer import Customer  # noqa: F401
from app.models.approval import Approval
from app.models.legal_risk import LegalCase, LegalCaseCollaborator, LegalCollaboratorType
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.services.legal_record_scope import (
    can_access_case,
    can_access_contract,
    case_access_predicate,
    contract_access_predicate,
    legal_record_scope,
)
from app.api.v1.endpoints.contract import list_contracts


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _user(db: Session, username: str, organization: Organization, position: Position) -> User:
    user = User(
        username=username,
        full_name=username,
        hashed_password="hashed",
        role=Role.BUSINESS_HANDLER,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserAssignment(
        user_id=user.id,
        organization_id=organization.id,
        position_id=position.id,
        valid_from=date(2026, 1, 1),
        status=AssignmentStatus.ACTIVE,
    ))
    return user


def test_contract_and_case_scope_union_company_department_and_legal_global(db):
    organizations = {}
    for code, company_code, organization_type in (
        ("investment.general", "investment", OrganizationType.DEPARTMENT),
        ("investment.asset_finance", "investment", OrganizationType.DEPARTMENT),
        ("investment.legal_risk", "investment", OrganizationType.DEPARTMENT),
        ("supplymanagement", "supplymanagement", OrganizationType.COMPANY),
        ("fundmanagement", "fundmanagement", OrganizationType.COMPANY),
    ):
        organization = Organization(
            code=code,
            name=code,
            company_code=company_code,
            organization_type=organization_type,
            is_active=True,
        )
        organizations[code] = organization
        db.add(organization)
    position = Position(
        code="test.manager", name="经理", category=PositionCategory.BUSINESS, is_active=True
    )
    db.add(position)
    db.flush()
    users = {
        key: _user(db, key, organizations[organization_code], position)
        for key, organization_code in (
            ("general", "investment.general"),
            ("finance", "investment.asset_finance"),
            ("legal", "investment.legal_risk"),
            ("supply", "supplymanagement"),
            ("fund", "fundmanagement"),
        )
    }
    db.flush()
    contracts = [
        Contract(contract_no=number, title=number, created_by=users[owner].id,
                 company_code=company, organization_code=organization)
        for number, owner, company, organization in (
            ("INV-G", "general", "investment", "investment.general"),
            ("INV-F", "finance", "investment", "investment.asset_finance"),
            ("SUP", "supply", "supplymanagement", "supplymanagement"),
            ("FUND", "fund", "fundmanagement", "fundmanagement"),
        )
    ]
    cases = [
        LegalCase(case_name=contract.contract_no, created_by=contract.created_by,
                  company_code=contract.company_code, organization_code=contract.organization_code)
        for contract in contracts
    ]
    db.add_all([*contracts, *cases])
    db.commit()

    expected = {
        "general": {"INV-G"},
        "finance": {"INV-F"},
        "supply": {"SUP"},
        "fund": {"FUND"},
        "legal": {"INV-G", "INV-F", "SUP", "FUND"},
    }
    for key, user in users.items():
        scope = legal_record_scope(db, user)
        visible_contracts = set(db.scalars(
            select(Contract.contract_no).where(contract_access_predicate(scope))
        ))
        visible_cases = set(db.scalars(
            select(LegalCase.case_name).where(case_access_predicate(scope))
        ))
        assert visible_contracts == expected[key]
        assert visible_cases == expected[key]


def test_contract_scope_includes_records_created_by_the_user(db):
    organization = Organization(
        code="scope-owner", name="scope-owner", company_code="scope-owner",
        organization_type=OrganizationType.COMPANY, is_active=True,
    )
    position = Position(
        code="scope-owner-position", name="scope-owner-position",
        category=PositionCategory.BUSINESS, is_active=True,
    )
    db.add_all([organization, position])
    db.flush()
    owner = _user(db, "scope-owner", organization, position)
    contract = Contract(
        contract_no="OWNER-ONLY", title="OWNER-ONLY", created_by=owner.id,
        company_code="other-company", organization_code="other-company",
    )
    db.add(contract)
    db.commit()

    assert can_access_contract(db, contract, legal_record_scope(db, owner))


def test_contract_list_endpoint_applies_shared_scope(db):
    from app.services.organization_catalog import seed_authorization_catalog

    seed_authorization_catalog(db)
    organizations = {
        code: db.scalar(select(Organization).where(Organization.code == code))
        for code in ("investment.legal_risk", "supplymanagement", "fundmanagement")
    }
    positions = {
        code: db.scalar(select(Position).where(Position.code == code))
        for code in (
            "investment.department.junior_manager",
            "supply.business_handler",
            "fund.general_manager",
        )
    }
    legal = _user(
        db, "endpoint-legal", organizations["investment.legal_risk"],
        positions["investment.department.junior_manager"],
    )
    supply = _user(
        db, "endpoint-supply", organizations["supplymanagement"],
        positions["supply.business_handler"],
    )
    fund = _user(
        db, "endpoint-fund", organizations["fundmanagement"],
        positions["fund.general_manager"],
    )
    db.flush()
    db.add_all([
        Contract(
            contract_no="END-SUP", title="供管", created_by=supply.id,
            company_code="supplymanagement", organization_code="supplymanagement",
        ),
        Contract(
            contract_no="END-FUND", title="基管", created_by=fund.id,
            company_code="fundmanagement", organization_code="fundmanagement",
        ),
    ])
    db.commit()

    supply_response = list_contracts(db=db, current_user=supply)
    legal_response = list_contracts(db=db, current_user=legal)

    assert {item.contract_no for item in supply_response.data} == {"END-SUP"}
    assert {item.contract_no for item in legal_response.data} == {"END-SUP", "END-FUND"}


def test_participation_extends_scope_without_granting_external_organization_access(db):
    external = Organization(
        code="external.legal", name="外聘法律顾问", organization_type=OrganizationType.EXTERNAL,
        is_active=True,
    )
    position = Position(
        code="external.legal_counsel", name="外聘法律顾问",
        category=PositionCategory.EXTERNAL, is_active=True,
    )
    db.add_all([external, position])
    db.flush()
    counsel = _user(db, "counsel", external, position)
    owner = User(
        username="owner", full_name="owner", hashed_password="hashed",
        role=Role.BUSINESS_HANDLER, is_active=True,
    )
    db.add(owner)
    db.flush()
    assigned_case = LegalCase(
        case_name="assigned", created_by=owner.id,
        company_code="supplymanagement", organization_code="supplymanagement",
    )
    hidden_case = LegalCase(
        case_name="hidden", created_by=owner.id,
        company_code="fundmanagement", organization_code="fundmanagement",
    )
    assigned_contract = Contract(
        contract_no="assigned-contract", title="assigned-contract", created_by=owner.id,
        company_code="supplymanagement", organization_code="supplymanagement",
    )
    hidden_contract = Contract(
        contract_no="hidden-contract", title="hidden-contract", created_by=owner.id,
        company_code="fundmanagement", organization_code="fundmanagement",
    )
    db.add_all([assigned_case, hidden_case, assigned_contract, hidden_contract])
    db.flush()
    db.add_all([
        LegalCaseCollaborator(
            case_id=assigned_case.id,
            user_id=counsel.id,
            collaborator_type=LegalCollaboratorType.LEGAL_COUNSEL,
            effective_at=datetime.now() - timedelta(days=1),
            expires_at=datetime.now() + timedelta(days=1),
            assigned_by=owner.id,
        ),
        Approval(
            contract_id=assigned_contract.id,
            approver_id=counsel.id,
            action=ApprovalAction.APPROVE,
        ),
    ])
    db.commit()

    scope = legal_record_scope(db, counsel)

    assert scope.company_codes == frozenset()
    assert can_access_case(db, assigned_case, scope)
    assert not can_access_case(db, hidden_case, scope)
    assert can_access_contract(db, assigned_contract, scope)
    assert not can_access_contract(db, hidden_contract, scope)
    assert set(db.scalars(
        select(LegalCase.case_name).where(case_access_predicate(scope))
    )) == {"assigned"}
