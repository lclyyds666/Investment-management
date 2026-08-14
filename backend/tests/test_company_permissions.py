import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

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
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.organization_catalog import seed_authorization_catalog
from app.services.permissions import (
    RESOURCE_VIEW_PERMISSIONS,
    allowed_resources,
    get_company_role,
    has_resource,
)


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

    def test_enabled_superuser_has_all_registered_resources(self):
        user = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)
        self.assertEqual(
            allowed_resources(self.db, user, CompanyCode.SUPPLY_MANAGEMENT),
            frozenset(RESOURCE_VIEW_PERMISSIONS),
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

    def test_require_company_resource_allows_enabled_superuser_without_assignment(self):
        user = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)

        self.assertIs(
            require_company_resource(
                CompanyCode.SUPPLY_MANAGEMENT,
                ResourceCode.SCENIC_ANALYTICS,
            )(current_user=user, db=self.db),
            user,
        )


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

    def test_operation_post_requires_independent_create_permission(self):
        self._add_current_user()
        payload = {
            "year": 2099,
            "month": 1,
            "business_line": "permission-boundary",
            "revenue": "100",
            "cost": "40",
            "profit": "60",
            "order_count": 1,
        }

        for permission_code in (
            "supply.operation.export",
            "supply.operation.view",
        ):
            with self.subTest(permission_code=permission_code):
                self._set_permission(permission_code)
                response = self.client.post("/api/v1/operation", json=payload)
                self.assertEqual(response.status_code, 403, response.text)

        self._assign_supply_role(self.current_user.id, Role.BUSINESS_HANDLER)
        payload["business_line"] = "handler-create"

        allowed = self.client.post("/api/v1/operation", json=payload)

        self.assertNotEqual(allowed.status_code, 403, allowed.text)

    def test_assigned_only_legal_position_can_read_zero_pending_count(self):
        self._add_current_user()
        self._assign_supply_role(self.current_user.id, Role.LEGAL_COUNSEL)

        response = self.client.get("/api/v1/approval/pending-count")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 0)

    def test_investment_executive_can_read_and_download_but_cannot_mutate(self):
        self._add_current_user()
        organization_id = self.db.scalar(
            select(Organization.id).where(Organization.code == "investment")
        )
        position_id = self.db.scalar(
            select(Position.id).where(
                Position.code == "investment.executive.general_manager"
            )
        )
        self.db.add(UserAssignment(
            user_id=self.current_user.id,
            organization_id=organization_id,
            position_id=position_id,
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        self.db.commit()

        self.assertEqual(self.client.get("/api/v1/contracts").status_code, 200)
        self.assertNotEqual(
            self.client.get("/api/v1/contracts/999/attachment").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/contracts",
                json={"contract_no": "EXEC-WRITE", "title": "Denied"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/channels",
                json={"name": "Denied"},
            ).status_code,
            403,
        )

    def _set_permission(
        self,
        permission_code: str,
        data_scope: DataScope = DataScope.COMPANY,
        scope_ref: str = CompanyCode.SUPPLY_MANAGEMENT.value,
    ):
        self.db.query(UserAssignment).filter(UserAssignment.user_id == self.current_user.id).delete()
        position_code = f"test.{permission_code}.{data_scope.value}.{scope_ref or 'blank'}"
        position = self.db.scalar(
            select(Position).where(Position.code == position_code)
        )
        if position is None:
            position = Position(
                code=position_code,
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
                data_scope=data_scope,
                scope_ref=scope_ref,
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

    def test_supply_company_scope_handler_can_view_all_contracts(self):
        self._add_current_user()
        self._assign_supply_role(self.current_user.id, Role.BUSINESS_HANDLER)
        self.db.add_all([
            Contract(contract_no="OWN", title="Own", created_by=self.current_user.id),
            Contract(contract_no="OTHER", title="Other", created_by=999),
        ])
        self.db.commit()

        response = self.client.get("/api/v1/contracts")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            {item["contract_no"] for item in response.json()["data"]},
            {"OWN", "OTHER"},
        )

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

    def test_pending_count_enforces_view_permission_scopes(self):
        self._add_current_user()

        for permission_code in (
            "supply.contract.view",
            "supply.approval.view",
        ):
            with self.subTest(permission_code=permission_code, data_scope="supply_company"):
                self._set_permission(permission_code)

                response = self.client.get("/api/v1/approval/pending-count")

                self.assertEqual(response.status_code, 200, response.text)

            for data_scope, scope_ref in (
                (DataScope.COMPANY, CompanyCode.INVESTMENT.value),
                (DataScope.OWN, ""),
                (DataScope.PARTICIPATED, ""),
                (DataScope.DEPARTMENT, "supply.test.department"),
            ):
                with self.subTest(
                    permission_code=permission_code,
                    data_scope=data_scope,
                    scope_ref=scope_ref,
                ):
                    self._set_permission(permission_code, data_scope, scope_ref)

                    response = self.client.get("/api/v1/approval/pending-count")

                    self.assertEqual(response.status_code, 403, response.text)


class UserAccountSchemaTest(unittest.TestCase):
    def test_account_requests_reject_authorization_inputs(self):
        for payload in (
            {"username": "worker", "password": "123456", "company_roles": []},
            {"username": "worker", "password": "123456", "role": "business_handler"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    UserCreate(**payload)

        with self.assertRaises(ValueError):
            UserUpdate(company_roles=[])

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


class UserAccountEndpointTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
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
            role=Role.UNASSIGNED,
            is_superuser=False,
            is_active=True,
        )
        self.db.add_all([self.admin, self.worker])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_account_is_unassigned_without_company_roles(self):
        response = create_user(
            UserCreate(username="new-worker", full_name="New", password="123456"),
            self.db,
            self.admin,
        )

        self.assertEqual(response.data.role, Role.UNASSIGNED)
        self.assertEqual(response.data.company_roles, [])
        self.assertEqual(response.data.assignment_summaries, [])

    def test_update_changes_account_fields_without_authorization_mutation(self):
        response = update_user(
            self.worker.id,
            UserUpdate(full_name="Updated", department="Operations"),
            self.db,
            self.admin,
        )

        self.assertEqual(response.data.full_name, "Updated")
        persisted = self.db.get(User, self.worker.id)
        self.assertEqual(persisted.full_name, "Updated")
        self.assertEqual(persisted.department, "Operations")
        self.assertEqual(persisted.role, Role.UNASSIGNED)
        self.assertFalse(persisted.is_superuser)
        self.assertEqual(persisted.company_roles, [])


if __name__ == "__main__":
    unittest.main()
