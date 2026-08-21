from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.enums import (
    AssignmentStatus,
    DataScope,
    OrganizationType,
    PositionCategory,
    Role,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.organization import (
    Organization,
    Permission,
    Position,
    PositionPermission,
    UserAssignment,
)
from app.models.contract import Contract
from app.models.legal_risk import LegalCase
from app.models.user import User
from app.services.legal_ownership import (
    LegalOwnershipError,
    legal_initiator_options,
    resolve_legal_ownership,
)
from app.services.organization_catalog import seed_authorization_catalog


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def test_normal_user_with_single_assignment_can_omit_assignment_id(db, assigned_users):
    assignment = assigned_users["supply_manager_assignment"]

    ownership = resolve_legal_ownership(
        db, assigned_users["supply_manager"], "contract", None, None
    )

    assert ownership.initiator_assignment_id == assignment.id


def test_normal_user_with_multiple_assignments_must_select_assignment(db, assigned_users):
    user = assigned_users["supply_manager"]
    second_assignment = UserAssignment(
        user_id=user.id,
        organization_id=assigned_users["zhanwei"].id,
        position_id=assigned_users["zhanwei_manager_assignment"].position_id,
        valid_from=date(2026, 1, 1),
        status=AssignmentStatus.ACTIVE,
    )
    db.add(second_assignment)
    db.commit()

    with pytest.raises(LegalOwnershipError) as error:
        resolve_legal_ownership(db, user, "contract", None, None)

    assert error.value.code == "invalid_initiator_assignment"


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


def test_superuser_contract_options_are_real_business_organizations_without_xinhua(
    db, assigned_users
):
    admin = User(
        username="admin-contract-options",
        full_name="管理员",
        hashed_password="hashed",
        role=Role.INFO_MAINTAINER,
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()

    options = legal_initiator_options(db, admin, "contract")

    assert {item.organization_code for item in options} == {
        "investment.legal_risk",
        "supplymanagement",
        "zhanwei",
    }
    assert all(item.assignment_id is None for item in options)
    assert "xinhuaproperty" not in {item.organization_code for item in options}


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


@pytest.mark.parametrize("resource", ("contract", "case"))
def test_superuser_cannot_select_investment_company_root(db, assigned_users, resource):
    admin = User(
        username=f"admin-investment-root-{resource}",
        full_name="管理员",
        hashed_password="hashed",
        role=Role.INFO_MAINTAINER,
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()

    with pytest.raises(LegalOwnershipError) as error:
        resolve_legal_ownership(db, admin, resource, None, "investment")

    assert error.value.code == "invalid_organization"


def test_legal_risk_router_exposes_initiator_options_endpoint():
    route = next(
        route
        for route in create_app().routes
        if route.path == "/api/v1/legal-risk/initiator-options"
    )

    assert "GET" in route.methods


@pytest.mark.parametrize(
    ("path", "payload"),
    (
        ("/api/v1/contracts", {"contract_no": "ADMIN-NO-ORG", "title": "无归属合同"}),
        ("/api/v1/legal-risk/cases", {"case_name": "无归属案件"}),
    ),
)
def test_superuser_create_endpoint_requires_organization_code(
    db, assigned_users, path, payload
):
    admin = User(
        username=f"admin-{len(path)}",
        full_name="管理员",
        hashed_password="hashed",
        role=Role.INFO_MAINTAINER,
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin
    with TestClient(app) as client:
        response = client.post(path, json=payload)
    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_organization"


def test_superuser_contract_create_marks_new_route_without_assignment(
    db, assigned_users
):
    admin = User(
        username="admin-proxy-contract",
        full_name="管理员",
        hashed_password="hashed",
        role=Role.INFO_MAINTAINER,
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/contracts",
            json={
                "contract_no": "ADMIN-PROXY-ROUTE",
                "title": "管理员代建合同",
                "organization_code": "supplymanagement",
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["data"]["workflow_route_version"] == 1
    contract = db.scalar(
        select(Contract).where(Contract.contract_no == "ADMIN-PROXY-ROUTE")
    )
    assert contract.initiator_assignment_id is None
    assert contract.workflow_route_version == 1


def _catalog_user(
    db: Session,
    username: str,
    organization_code: str,
    position_code: str,
) -> tuple[User, UserAssignment]:
    user = User(
        username=username,
        full_name=username,
        hashed_password="hashed",
        role=Role.UNASSIGNED,
        is_active=True,
    )
    db.add(user)
    db.flush()
    assignment = UserAssignment(
        user_id=user.id,
        organization_id=db.scalar(
            select(Organization.id).where(Organization.code == organization_code)
        ),
        position_id=db.scalar(
            select(Position.id).where(Position.code == position_code)
        ),
        valid_from=date(2026, 1, 1),
        status=AssignmentStatus.ACTIVE,
    )
    db.add(assignment)
    db.commit()
    return user, assignment


def _permission_position(
    db: Session,
    position_code: str,
    permission_codes: tuple[str, ...],
) -> Position:
    position = Position(
        code=position_code,
        name=position_code,
        category=PositionCategory.BUSINESS,
        is_active=True,
    )
    db.add(position)
    db.flush()
    for permission_code in permission_codes:
        db.add(PositionPermission(
            position_id=position.id,
            permission_id=db.scalar(
                select(Permission.id).where(Permission.code == permission_code)
            ),
            data_scope=DataScope.COMPANY,
            scope_ref="investment",
        ))
    db.commit()
    return position


def test_xinhua_case_http_chain_uses_catalog_permissions_and_company_scope(db):
    seed_authorization_catalog(db)
    xinhua_user, assignment = _catalog_user(
        db,
        "xinhua-http-user",
        "xinhuaproperty",
        "xinhuaproperty.department.employee",
    )
    other_case = LegalCase(
        case_name="供管案件",
        created_by=xinhua_user.id,
        company_code="supplymanagement",
        organization_code="supplymanagement",
    )
    db.add(other_case)
    db.commit()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: xinhua_user
    with TestClient(app) as client:
        case_options = client.get(
            "/api/v1/legal-risk/initiator-options", params={"resource": "case"}
        )
        contract_options = client.get(
            "/api/v1/legal-risk/initiator-options", params={"resource": "contract"}
        )
        created = client.post(
            "/api/v1/legal-risk/cases",
            json={
                "case_name": "新华案件",
                "initiator_assignment_id": assignment.id,
            },
        )
        hidden = client.get(f"/api/v1/legal-risk/cases/{other_case.id}")
        denied_contract = client.post(
            "/api/v1/contracts",
            json={
                "contract_no": "XH-HTTP-DENIED",
                "title": "新华合同",
                "initiator_assignment_id": assignment.id,
            },
        )
    app.dependency_overrides.clear()

    assert case_options.status_code == 200, case_options.text
    assert [item["organization_code"] for item in case_options.json()["data"]] == [
        "xinhuaproperty"
    ]
    assert contract_options.status_code == 200, contract_options.text
    assert contract_options.json()["data"] == []
    assert created.status_code == 200, created.text
    assert created.json()["data"]["company_code"] == "xinhuaproperty"
    assert hidden.status_code == 404, hidden.text
    assert denied_contract.status_code == 403, denied_contract.text


def test_case_create_and_update_permissions_are_independent_over_http(db):
    seed_authorization_catalog(db)
    _permission_position(
        db,
        "test.case.create-only",
        ("investment.legal.cases.view", "investment.legal.cases.create"),
    )
    _permission_position(
        db,
        "test.case.update-only",
        ("investment.legal.cases.view", "investment.legal.cases.update"),
    )
    create_user, create_assignment = _catalog_user(
        db, "case-create-only", "xinhuaproperty", "test.case.create-only"
    )
    update_user, update_assignment = _catalog_user(
        db, "case-update-only", "xinhuaproperty", "test.case.update-only"
    )
    existing = LegalCase(
        case_name="待更新案件",
        created_by=update_user.id,
        company_code="xinhuaproperty",
        organization_code="xinhuaproperty",
        initiator_assignment_id=update_assignment.id,
    )
    db.add(existing)
    db.commit()
    current = {"user": create_user}
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/legal-risk/cases",
            json={
                "case_name": "仅创建案件",
                "initiator_assignment_id": create_assignment.id,
            },
        )
        assert created.status_code == 200, created.text
        create_update = client.put(
            f"/api/v1/legal-risk/cases/{created.json()['data']['id']}",
            json={"version": created.json()["data"]["version"], "case_name": "越权更新"},
        )

        current["user"] = update_user
        update_create = client.post(
            "/api/v1/legal-risk/cases",
            json={
                "case_name": "越权创建",
                "initiator_assignment_id": update_assignment.id,
            },
        )
        allowed_update = client.put(
            f"/api/v1/legal-risk/cases/{existing.id}",
            json={"version": existing.version, "case_name": "已更新案件"},
        )
    app.dependency_overrides.clear()

    assert create_update.status_code == 403, create_update.text
    assert update_create.status_code == 403, update_create.text
    assert allowed_update.status_code == 200, allowed_update.text
