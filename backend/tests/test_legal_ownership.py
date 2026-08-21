from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.enums import AssignmentStatus, OrganizationType, PositionCategory, Role
from app.db.base import Base
from app.main import create_app
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.services.legal_ownership import (
    LegalOwnershipError,
    legal_initiator_options,
    resolve_legal_ownership,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def assigned_users(db):
    organizations = {}
    for code, name, company_code, organization_type in (
        ("supplymanagement", "山东出版供应链管理有限公司", "supplymanagement", OrganizationType.COMPANY),
        ("zhanwei", "山东展威科技有限公司", "zhanwei", OrganizationType.COMPANY),
        ("xinhuaproperty", "山东新华置业有限公司", "xinhuaproperty", OrganizationType.COMPANY),
        ("investment.legal_risk", "法务风控部", "investment", OrganizationType.DEPARTMENT),
    ):
        organization = Organization(
            code=code,
            name=name,
            company_code=company_code,
            organization_type=organization_type,
            is_active=True,
        )
        organizations[code] = organization
        db.add(organization)

    positions = {}
    for code, name in (
        ("supply.manager", "高级经理"),
        ("zhanwei.manager", "高级经理"),
        ("xinhuaproperty.department.employee", "部门员工"),
    ):
        position = Position(
            code=code,
            name=name,
            category=PositionCategory.BUSINESS,
            is_active=True,
        )
        positions[code] = position
        db.add(position)

    users = {}
    for key in ("supply_manager", "zhanwei_manager", "xinhua_employee"):
        user = User(
            username=key,
            full_name=key,
            hashed_password="hashed",
            role=Role.BUSINESS_HANDLER,
            is_active=True,
        )
        users[key] = user
        db.add(user)
    db.flush()

    assignments = {}
    for key, user_key, organization_code, position_code in (
        ("supply_manager_assignment", "supply_manager", "supplymanagement", "supply.manager"),
        ("zhanwei_manager_assignment", "zhanwei_manager", "zhanwei", "zhanwei.manager"),
        ("xinhua_employee_assignment", "xinhua_employee", "xinhuaproperty", "xinhuaproperty.department.employee"),
    ):
        assignment = UserAssignment(
            user_id=users[user_key].id,
            organization_id=organizations[organization_code].id,
            position_id=positions[position_code].id,
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        )
        assignments[key] = assignment
        db.add(assignment)
    db.commit()
    return {**users, **assignments, **organizations}


def test_subsidiary_contract_and_case_options_follow_company_policy(db, assigned_users):
    supply_user = assigned_users["supply_manager"]
    xinhua_user = assigned_users["xinhua_employee"]

    supply_contracts = legal_initiator_options(db, supply_user, "contract")
    supply_cases = legal_initiator_options(db, supply_user, "case")
    xinhua_contracts = legal_initiator_options(db, xinhua_user, "contract")
    xinhua_cases = legal_initiator_options(db, xinhua_user, "case")

    assert [item.company_code for item in supply_contracts] == ["supplymanagement"]
    assert [item.company_code for item in supply_cases] == ["supplymanagement"]
    assert xinhua_contracts == []
    assert [item.company_code for item in xinhua_cases] == ["xinhuaproperty"]


def test_normal_user_cannot_forge_initiator_assignment(db, assigned_users):
    with pytest.raises(LegalOwnershipError) as error:
        resolve_legal_ownership(
            db,
            assigned_users["supply_manager"],
            "contract",
            assigned_users["zhanwei_manager_assignment"].id,
            None,
        )
    assert error.value.code == "invalid_initiator_assignment"


def test_normal_user_resolves_selected_effective_assignment(db, assigned_users):
    assignment = assigned_users["supply_manager_assignment"]

    ownership = resolve_legal_ownership(
        db, assigned_users["supply_manager"], "contract", assignment.id, None
    )

    assert ownership.company_code == "supplymanagement"
    assert ownership.organization_code == "supplymanagement"
    assert ownership.initiator_assignment_id == assignment.id


def test_superuser_selects_active_business_organization_without_assignment(db, assigned_users):
    admin = User(
        username="admin",
        full_name="管理员",
        hashed_password="hashed",
        role=Role.INFO_MAINTAINER,
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()

    ownership = resolve_legal_ownership(
        db, admin, "case", None, "investment.legal_risk"
    )

    assert ownership.company_code == "investment"
    assert ownership.organization_code == "investment.legal_risk"
    assert ownership.initiator_assignment_id is None


def test_superuser_cannot_select_company_disallowed_for_resource(db, assigned_users):
    admin = User(
        username="admin-denied",
        full_name="管理员",
        hashed_password="hashed",
        role=Role.INFO_MAINTAINER,
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()

    with pytest.raises(LegalOwnershipError) as error:
        resolve_legal_ownership(db, admin, "contract", None, "xinhuaproperty")

    assert error.value.code == "invalid_organization"


def test_legal_risk_router_exposes_initiator_options_endpoint():
    route = next(
        route
        for route in create_app().routes
        if route.path == "/api/v1/legal-risk/initiator-options"
    )

    assert "GET" in route.methods
