import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import require_company_resource, require_roles
from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.api.v1.endpoints.approval import list_todo as list_approval_todo
from app.api.v1.endpoints.approval_stats import pending_count
from app.api.v1.endpoints.contract import list_todo as list_contract_todo
from app.api.v1.endpoints.user import create_user, update_user
from app.core.enums import (
    AssignmentStatus, CompanyCode, ContractStatus, DataScope, PermissionAction,
    PositionCategory, ResourceCode, Role,
)
from app.db.base import Base
from app.models.organization import (
    Organization, Permission, Position, PositionPermission, UserAssignment,
)
from app.models.portal import UserCompanyRole
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.operation import OperationData
from app.models.ticket_ledger import TicketLedger
from app.models.user import User
from app.schemas.user import CompanyRoleAssignment, UserCreate, UserOut, UserUpdate
from app.services.organization_catalog import seed_authorization_catalog
from app.services.permissions import allowed_resources, get_company_role, has_resource


class CompanyRoleModelTest(unittest.TestCase):
    def test_company_and_resource_codes_are_stable(self):
        self.assertEqual(CompanyCode.INVESTMENT.value, "investment")
        self.assertEqual(CompanyCode.SUPPLY_MANAGEMENT.value, "supplymanagement")
        self.assertEqual(CompanyCode.FUND_MANAGEMENT.value, "fundmanagement")
        self.assertEqual(ResourceCode.SCENIC_ANALYTICS.value, "supply.scenic.analytics")

    def test_user_company_role_has_one_membership_per_company(self):
        unique_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in UserCompanyRole.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("user_id", "company_code"), unique_sets)


class CompanyPermissionServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, username: str, role: Role, is_superuser: bool = False) -> User:
        user = User(
            username=username,
            full_name=username,
            hashed_password="test",
            role=role,
            is_superuser=is_superuser,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def add_assignment(self, user: User, organization_code: str, position_code: str) -> None:
        self.db.add(UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        self.db.commit()

    def test_assignment_position_overrides_stale_legacy_role(self):
        user = self.add_user("handler", Role.LEGAL_COUNSEL)
        self.add_assignment(user, "supplymanagement", "supply.business_handler")
        self.assertEqual(
            get_company_role(self.db, user, CompanyCode.SUPPLY_MANAGEMENT),
            Role.BUSINESS_HANDLER,
        )

    def test_user_without_assignment_has_no_supply_resource(self):
        user = self.add_user("unassigned", Role.BUSINESS_HANDLER)
        self.assertFalse(
            has_resource(
                self.db,
                user,
                CompanyCode.SUPPLY_MANAGEMENT,
                ResourceCode.SCENIC_ANALYTICS,
            )
        )

    def test_superuser_has_no_implicit_registered_resources(self):
        user = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)
        self.assertEqual(
            allowed_resources(self.db, user, CompanyCode.SUPPLY_MANAGEMENT),
            frozenset(),
        )

    def test_superuser_cannot_access_supply_resource_under_another_company(self):
        user = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)
        self.assertFalse(
            has_resource(
                self.db,
                user,
                CompanyCode.INVESTMENT,
                ResourceCode.SCENIC_ANALYTICS,
            )
        )


class CompanyPermissionDependencyTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, username: str, role: Role, is_superuser: bool = False) -> User:
        user = User(
            username=username,
            full_name=username,
            hashed_password="test",
            role=role,
            is_superuser=is_superuser,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def add_assignment(self, user: User, position_code: str) -> None:
        self.db.add(UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == "supplymanagement")
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        self.db.commit()

    def test_require_roles_denies_missing_assignment(self):
        user = self.add_user("unassigned", Role.BUSINESS_HANDLER)

        with self.assertRaises(HTTPException) as raised:
            require_roles(Role.BUSINESS_HANDLER)(current_user=user, db=self.db)

        self.assertEqual(raised.exception.status_code, 403)

    def test_require_roles_denies_superuser_with_business_assignment(self):
        user = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)
        self.add_assignment(user, "supply.business_handler")

        with self.assertRaises(HTTPException) as raised:
            require_roles(Role.BUSINESS_HANDLER)(current_user=user, db=self.db)

        self.assertEqual(raised.exception.status_code, 403)

    def test_require_company_resource_denies_missing_assignment(self):
        user = self.add_user("unassigned", Role.BUSINESS_HANDLER)

        with self.assertRaises(HTTPException) as raised:
            require_company_resource(
                CompanyCode.SUPPLY_MANAGEMENT,
                ResourceCode.SCENIC_ANALYTICS,
            )(current_user=user, db=self.db)

        self.assertEqual(raised.exception.status_code, 403)

    def test_require_company_resource_denies_superuser_without_assignment(self):
        user = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)

        with self.assertRaises(HTTPException) as raised:
            require_company_resource(
                CompanyCode.SUPPLY_MANAGEMENT,
                ResourceCode.SCENIC_ANALYTICS,
            )(current_user=user, db=self.db)

        self.assertEqual(raised.exception.status_code, 403)


class SupplyApiAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.app = create_app()
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7, role=Role.BUSINESS_HANDLER, is_superuser=False, is_active=True
        )
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_supply_resource_endpoints_deny_stale_legacy_role_without_membership(self):
        for path in (
            "/api/v1/channels",
            "/api/v1/contracts",
            "/api/v1/approval-forms",
            "/api/v1/users",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)


class ResourceSpecificEndpointTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.current_user = SimpleNamespace(id=7, is_superuser=False)
        self.app = create_app()
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _assign_supply_role(self, user_id: int, role: Role):
        targets = {
            Role.RISK_AUDITOR: ("investment.legal_risk", "investment.duty.supply_risk_review"),
            Role.BUSINESS_HANDLER: ("supplymanagement", "supply.business_handler"),
            Role.LEGAL_COUNSEL: ("external.legal", "external.legal_counsel"),
        }
        organization_code, position_code = targets[role]
        self.db.add(UserAssignment(
            user_id=user_id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        self.db.commit()

    def test_dashboard_only_role_can_load_operation_dashboard(self):
        self._assign_supply_role(7, Role.RISK_AUDITOR)

        response = self.client.get("/api/v1/operation/dashboard")

        self.assertEqual(response.status_code, 200)

    def test_assigned_only_legal_position_fails_closed_for_resource_guard(self):
        self.current_user = SimpleNamespace(id=8, is_superuser=False)
        self._assign_supply_role(8, Role.LEGAL_COUNSEL)

        response = self.client.get("/api/v1/approval/pending-count")

        self.assertEqual(response.status_code, 403)

    def _set_permission(self, permission_code: str):
        self.db.query(UserAssignment).filter(UserAssignment.user_id == self.current_user.id).delete()
        position = self.db.scalar(
            select(Position).where(Position.code == f"test.{permission_code}")
        )
        if position is None:
            position = Position(
                code=f"test.{permission_code}",
                name=permission_code,
                category=PositionCategory.BUSINESS,
            )
            self.db.add(position)
            self.db.flush()
            self.db.add(PositionPermission(
                position_id=position.id,
                permission_id=self.db.scalar(
                    select(Permission.id).where(Permission.code == permission_code)
                ),
                data_scope=DataScope.COMPANY,
                scope_ref=CompanyCode.SUPPLY_MANAGEMENT.value,
            ))
        self.db.add(UserAssignment(
            user_id=self.current_user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == "supplymanagement")
            ),
            position_id=position.id,
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        self.db.commit()

    def _add_current_user(self):
        user = User(
            id=7,
            username="endpoint-user",
            full_name="Endpoint User",
            hashed_password="test",
            role=Role.UNASSIGNED,
            is_superuser=False,
        )
        self.db.add(user)
        self.db.commit()
        self.current_user = user

    def test_mutation_endpoints_require_the_exact_permission_code(self):
        self._add_current_user()
        self.db.add_all([
            Contract(id=1, contract_no="C-1", title="Contract", created_by=7, status=ContractStatus.DRAFT),
            Customer(id=1, customer_code="CUS-1", name="Customer"),
            Invoice(id=1, invoice_title="Invoice"),
            TicketLedger(id=1, scenic_id="demo", row_no=1, confirm_stored="confirm.pdf"),
        ])
        self.db.commit()
        cases = (
            ("POST", "/api/v1/contracts", "supply.contract.create", {"contract_no": "C-2", "title": "New"}),
            ("POST", "/api/v1/contracts/1/submit", "supply.contract.submit", None),
            ("PUT", "/api/v1/customers/1", "supply.customer.update", {"name": "Updated"}),
            ("POST", "/api/v1/scenic-spots/demo/ticket-ledger", "supply.scenic.create", {"rows": []}),
            ("POST", "/api/v1/scenic-spots/demo/ticket-ledger/1/confirm/approve", "supply.scenic.review", None),
            ("PUT", "/api/v1/invoices/1", "supply.finance.update", {"invoice_title": "Updated"}),
            ("POST", "/api/v1/channels", "supply.channel.configure", {"name": "Channel"}),
        )

        for method, path, permission_code, payload in cases:
            with self.subTest(path=path, permission=permission_code):
                self._set_permission(permission_code)
                response = self.client.request(method, path, json=payload)
                self.assertNotEqual(response.status_code, 403, response.text)

                view_code = permission_code.rsplit(".", 1)[0] + ".view"
                self._set_permission(view_code)
                denied = self.client.request(method, path, json=payload)
                self.assertEqual(denied.status_code, 403, denied.text)

    def test_scenic_delete_is_independent_from_scenic_update(self):
        self._add_current_user()
        self._set_permission("supply.scenic.update")
        denied = self.client.delete("/api/v1/scenic-spots/demo/ledger")
        self.assertEqual(denied.status_code, 403)

        self._set_permission("supply.scenic.delete")
        allowed = self.client.delete("/api/v1/scenic-spots/demo/ledger")
        self.assertEqual(allowed.status_code, 200)

    def test_approved_business_records_are_immutable_for_delete(self):
        self._add_current_user()
        contract = Contract(
            id=1, contract_no="APPROVED", title="Approved", created_by=7,
            status=ContractStatus.APPROVED,
        )
        form = ApprovalForm(id=1, form_type="business", created_by=7, status=ContractStatus.APPROVED)
        self.db.add_all([contract, form])
        self.db.commit()

        for path, permission_code in (
            ("/api/v1/contracts/1", "supply.contract.delete"),
            ("/api/v1/approval-forms/1", "supply.approval.delete"),
        ):
            with self.subTest(path=path):
                self._set_permission(permission_code)
                response = self.client.delete(path)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"], "已审批业务记录不可删除")

    def test_superuser_without_business_assignment_has_zero_pending_tasks(self):
        user = User(
            id=7,
            username="admin-no-business-role",
            full_name="Admin",
            hashed_password="test",
            role=Role.INFO_MAINTAINER,
            is_superuser=True,
        )
        self.db.add_all([
            user,
            Contract(
                id=1, contract_no="PENDING", title="Pending", created_by=7,
                status=ContractStatus.PENDING, current_step=1,
            ),
            ApprovalForm(
                id=1, form_type="business", created_by=7,
                status=ContractStatus.PENDING, current_step=1,
            ),
        ])
        self.db.commit()

        self.assertEqual(list_contract_todo(self.db, user).data, [])
        self.assertEqual(list_approval_todo(self.db, user).data, [])
        self.assertEqual(pending_count(self.db, user).data["total"], 0)

    def test_remaining_read_endpoints_require_module_view_permission(self):
        self._add_current_user()
        cases = (
            ("POST", "/api/v1/contracts/999/ai-review", "supply.contract.view"),
            ("POST", "/api/v1/approval-forms/999/proofread", "supply.approval.view"),
            ("GET", "/api/v1/approval/pending-count", "supply.approval.view"),
        )

        for method, path, permission_code in cases:
            with self.subTest(path=path, permission=permission_code):
                self._set_permission("supply.dashboard.view")
                denied = self.client.request(method, path)
                self.assertEqual(denied.status_code, 403, denied.text)

                self._set_permission(permission_code)
                allowed = self.client.request(method, path)
                self.assertNotEqual(allowed.status_code, 403, allowed.text)


class UserCompanyRoleSchemaTest(unittest.TestCase):
    def test_duplicate_company_assignments_are_rejected(self):
        with self.assertRaises(ValueError):
            UserCreate(
                username="worker", full_name="测试", password="123456",
                company_roles=[
                    CompanyRoleAssignment(company_code="supplymanagement", role="business_handler"),
                    CompanyRoleAssignment(company_code="supplymanagement", role="finance_handler"),
                ],
            )

    def test_info_maintainer_cannot_be_created_as_a_normal_user(self):
        with self.assertRaises(ValueError):
            UserCreate(
                username="admin2", full_name="第二管理员", password="123456",
                role="info_maintainer", is_superuser=False,
                company_roles=[],
            )

    def test_existing_admin_supply_membership_remains_serializable(self):
        output = UserOut.model_validate(
            SimpleNamespace(
                id=1,
                username="admin",
                full_name="信息维护",
                role=Role.INFO_MAINTAINER,
                department="信息中心",
                is_active=True,
                is_superuser=True,
                signature=None,
                company_roles=[
                    SimpleNamespace(
                        company_code=CompanyCode.SUPPLY_MANAGEMENT.value,
                        role=Role.INFO_MAINTAINER,
                    )
                ],
            )
        )

        self.assertEqual(output.company_roles[0].role, Role.INFO_MAINTAINER)


class UserCompanyRoleEndpointTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        User.__table__.create(self.engine)
        UserCompanyRole.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.admin = User(
            username="admin",
            full_name="信息维护",
            hashed_password="hashed",
            role=Role.INFO_MAINTAINER,
            is_superuser=True,
            is_active=True,
        )
        self.worker = User(
            username="worker",
            full_name="测试用户",
            hashed_password="hashed",
            role=Role.BUSINESS_HANDLER,
            is_superuser=False,
            is_active=True,
            company_roles=[
                UserCompanyRole(
                    company_code=CompanyCode.SUPPLY_MANAGEMENT.value,
                    role=Role.BUSINESS_HANDLER,
                ),
                UserCompanyRole(
                    company_code=CompanyCode.INVESTMENT.value,
                    role=Role.RISK_AUDITOR,
                ),
            ],
        )
        self.db.add_all([self.admin, self.worker])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_update_replaces_assignments_and_synchronizes_legacy_supply_role(self):
        response = update_user(
            self.worker.id,
            UserUpdate(
                company_roles=[
                    CompanyRoleAssignment(
                        company_code=CompanyCode.SUPPLY_MANAGEMENT,
                        role=Role.FINANCE_HANDLER,
                    ),
                    CompanyRoleAssignment(
                        company_code=CompanyCode.FUND_MANAGEMENT,
                        role=Role.INVEST_DIRECTOR,
                    ),
                ]
            ),
            self.db,
            self.admin,
        )

        self.assertEqual(response.data.role, Role.FINANCE_HANDLER)
        self.assertEqual(
            {(item.company_code, item.role) for item in response.data.company_roles},
            {
                (CompanyCode.SUPPLY_MANAGEMENT, Role.FINANCE_HANDLER),
                (CompanyCode.FUND_MANAGEMENT, Role.INVEST_DIRECTOR),
            },
        )
        persisted = self.db.get(User, self.worker.id)
        self.assertEqual(persisted.role, Role.FINANCE_HANDLER)
        self.assertEqual(
            {(item.company_code, item.role) for item in persisted.company_roles},
            {
                (CompanyCode.SUPPLY_MANAGEMENT.value, Role.FINANCE_HANDLER),
                (CompanyCode.FUND_MANAGEMENT.value, Role.INVEST_DIRECTOR),
            },
        )

    def test_non_superuser_update_requires_supply_assignment(self):
        with self.assertRaises(HTTPException) as raised:
            update_user(
                self.worker.id,
                UserUpdate(
                    company_roles=[
                        CompanyRoleAssignment(
                            company_code=CompanyCode.INVESTMENT,
                            role=Role.RISK_AUDITOR,
                        )
                    ]
                ),
                self.db,
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_non_superuser_cannot_receive_info_maintainer_company_role(self):
        payload = UserCreate(
            username="worker2",
            full_name="第二用户",
            password="123456",
            company_roles=[
                CompanyRoleAssignment(
                    company_code=CompanyCode.SUPPLY_MANAGEMENT,
                    role=Role.BUSINESS_HANDLER,
                ),
                CompanyRoleAssignment(
                    company_code=CompanyCode.INVESTMENT,
                    role=Role.INFO_MAINTAINER,
                ),
            ],
        )

        with self.assertRaises(HTTPException) as raised:
            create_user(payload, self.db, self.admin)

        self.assertEqual(raised.exception.status_code, 400)

    def test_failed_commit_rolls_back_assignments_and_legacy_role_together(self):
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                update_user(
                    self.worker.id,
                    UserUpdate(
                        company_roles=[
                            CompanyRoleAssignment(
                                company_code=CompanyCode.SUPPLY_MANAGEMENT,
                                role=Role.FINANCE_REVIEWER,
                            )
                        ]
                    ),
                    self.db,
                    self.admin,
                )

        self.db.expire_all()
        persisted = self.db.get(User, self.worker.id)
        self.assertEqual(persisted.role, Role.BUSINESS_HANDLER)
        self.assertEqual(
            {(item.company_code, item.role) for item in persisted.company_roles},
            {
                (CompanyCode.SUPPLY_MANAGEMENT.value, Role.BUSINESS_HANDLER),
                (CompanyCode.INVESTMENT.value, Role.RISK_AUDITOR),
            },
        )

    def test_existing_information_maintainer_identity_cannot_change(self):
        with self.assertRaises(HTTPException) as raised:
            update_user(
                self.admin.id,
                UserUpdate(role=Role.BUSINESS_HANDLER),
                self.db,
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_second_information_maintainer_is_rejected(self):
        payload = UserCreate(
            username="admin2",
            full_name="第二管理员",
            password="123456",
            role=Role.INFO_MAINTAINER,
            is_superuser=True,
            company_roles=[],
        )

        with self.assertRaises(HTTPException) as raised:
            create_user(payload, self.db, self.admin)

        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
