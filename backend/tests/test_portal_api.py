import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.core.enums import AssignmentStatus, Role
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.services.organization_catalog import (
    INVESTMENT_EXECUTIVE_POSITION_CODES,
    INVESTMENT_EXECUTIVE_READ_PERMISSIONS,
    PERMISSION_CATALOG,
    seed_authorization_catalog,
)
from app.services.portal import applications_for_user, permission_snapshot_for_user
from app.services.permissions import RESOURCE_VIEW_PERMISSIONS


class PortalRegistryTest(unittest.TestCase):
    SUPPLY_PORTAL_ASSIGNMENTS = (
        ("supplymanagement", "supply.business_handler"),
        ("supplymanagement", "supply.business_reviewer"),
        ("supplymanagement", "supply.finance_handler"),
        ("supplymanagement", "supply.company_leader"),
        ("supplymanagement", "governance.supply_leader"),
        ("investment.legal_risk", "investment.duty.supply_risk_review"),
        ("investment.asset_finance", "investment.duty.supply_finance_review"),
        ("external.legal", "external.legal_counsel"),
    )

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.user = self.add_user("portal-user")
        self.admin = self.add_user("admin", is_superuser=True)
        self.add_assignment(
            self.user, "investment", "investment.executive.general_manager"
        )
        self.add_assignment(
            self.user, "supplymanagement", "governance.supply_leader"
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, username: str, is_superuser: bool = False) -> User:
        user = User(
            username=username,
            full_name=username,
            hashed_password="test",
            role=Role.UNASSIGNED,
            is_superuser=is_superuser,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def add_assignment(
        self, user: User, organization_code: str, position_code: str
    ) -> UserAssignment:
        assignment = UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        )
        self.db.add(assignment)
        self.db.commit()
        return assignment

    def test_registry_always_returns_three_apps_in_fixed_order(self):
        apps = applications_for_user(self.db, self.user)

        self.assertEqual(
            [item.code for item in apps],
            ["investment", "supplymanagement", "fundmanagement"],
        )
        self.assertEqual(
            [item.status for item in apps],
            ["online", "online", "construction"],
        )
        self.assertEqual([item.accessible for item in apps], [True, True, True])

    def test_every_intended_position_can_enter_the_supply_application(self):
        for index, (organization_code, position_code) in enumerate(
            self.SUPPLY_PORTAL_ASSIGNMENTS
        ):
            with self.subTest(position_code=position_code):
                user = self.add_user(f"supply-portal-{index}")
                self.add_assignment(user, organization_code, position_code)

                supply_app = applications_for_user(self.db, user)[1]

                self.assertTrue(supply_app.accessible)
                self.assertIsNone(supply_app.denial_reason)

    def test_each_investment_executive_can_enter_all_three_applications(self):
        for index, position_code in enumerate((
            "investment.executive.chairman",
            "investment.executive.general_manager",
            "investment.executive.deputy_general_manager",
        )):
            with self.subTest(position_code=position_code):
                user = self.add_user(f"investment-executive-{index}")
                self.add_assignment(user, "investment", position_code)
                apps = applications_for_user(self.db, user)
                self.assertEqual([item.accessible for item in apps], [True, True, True])
                self.assertEqual([item.denial_reason for item in apps], [None, None, None])

    def test_enabled_superuser_can_enter_every_application_without_assignments(self):
        apps = applications_for_user(self.db, self.admin)

        self.assertEqual([item.accessible for item in apps], [True, True, True])
        self.assertEqual([item.denial_reason for item in apps], [None, None, None])

    def test_disabled_superuser_cannot_enter_applications_with_assignment(self):
        self.add_assignment(self.admin, "supplymanagement", "supply.business_handler")
        self.admin.is_active = False
        self.db.commit()

        apps = applications_for_user(self.db, self.admin)

        self.assertEqual([item.accessible for item in apps], [False, False, False])
        self.assertEqual(
            [item.denial_reason for item in apps],
            ["暂时无访问权限", "暂时无访问权限", "暂时无访问权限"],
        )

    def test_product_name_is_unified(self):
        from app.core.config import Settings

        self.assertEqual(Settings().PROJECT_NAME, "山东出版投资有限公司工作平台")

    def test_denied_applications_include_the_required_reason(self):
        apps = applications_for_user(self.db, self.add_user("denied-user"))

        self.assertEqual(
            [item.denial_reason for item in apps],
            ["暂时无访问权限", "暂时无访问权限", "暂时无访问权限"],
        )


class PortalPermissionSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.multi_role_user = self.add_user("multi-role")
        self.legacy_user = self.add_user("legacy-user")
        self.admin = self.add_user("admin", is_superuser=True)
        self.add_assignment(
            self.multi_role_user, "investment", "investment.executive.general_manager"
        )
        self.add_assignment(
            self.multi_role_user, "supplymanagement", "governance.supply_leader"
        )
        self.add_assignment(
            self.multi_role_user, "supplymanagement", "supply.business_handler"
        )
        self.add_assignment(
            self.legacy_user, "supplymanagement", "governance.supply_leader"
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, username: str, is_superuser: bool = False) -> User:
        user = User(
            username=username,
            full_name=username,
            hashed_password="test",
            role=Role.UNASSIGNED,
            is_superuser=is_superuser,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def add_assignment(
        self, user: User, organization_code: str, position_code: str
    ) -> UserAssignment:
        assignment = UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        )
        self.db.add(assignment)
        self.db.commit()
        return assignment

    def test_snapshot_returns_multiple_assignments_and_scoped_permissions(self):
        snapshot = permission_snapshot_for_user(self.db, self.multi_role_user)

        self.assertEqual(
            {item.position_code for item in snapshot.assignments},
            {
                "investment.executive.general_manager",
                "governance.supply_leader",
                "supply.business_handler",
            },
        )
        self.assertIn(
            ("supply.contract.view", "company", "supplymanagement"),
            {(item.code, item.data_scope, item.scope_ref) for item in snapshot.permissions},
        )
        self.assertIn("supply.scenic.delete", {item.code for item in snapshot.permissions})

    def test_snapshot_orders_and_deduplicates_projections(self):
        snapshot = permission_snapshot_for_user(self.db, self.multi_role_user)

        self.assertEqual(
            [item.position_code for item in snapshot.assignments],
            [
                "investment.executive.general_manager",
                "governance.supply_leader",
                "supply.business_handler",
            ],
        )
        grants = [(item.code, item.data_scope, item.scope_ref) for item in snapshot.permissions]
        self.assertEqual(grants, sorted(set(grants)))
        self.assertEqual(snapshot.resources, sorted(set(snapshot.resources)))

    def test_snapshot_projects_an_unambiguous_migrated_legacy_role(self):
        snapshot = permission_snapshot_for_user(self.db, self.legacy_user)

        self.assertEqual(snapshot.company_roles, {
            "investment": "invest_director",
            "supplymanagement": "invest_director",
        })

    def test_each_investment_executive_snapshot_has_exact_authorization_boundary(self):
        for index, position_code in enumerate(INVESTMENT_EXECUTIVE_POSITION_CODES):
            with self.subTest(position_code=position_code):
                user = self.add_user(f"snapshot-executive-{index}")
                self.add_assignment(user, "investment", position_code)

                snapshot = permission_snapshot_for_user(self.db, user)
                expected_permissions = INVESTMENT_EXECUTIVE_READ_PERMISSIONS | {
                    "investment.legal.cases.export",
                    "investment.legal.contracts.view",
                    "investment.legal.contracts.export",
                    "investment.legal.contracts.review",
                    "investment.legal.contracts.approve",
                    "investment.legal.contracts.return",
                }

                self.assertEqual(
                    {item.code for item in snapshot.permissions},
                    expected_permissions,
                )
                self.assertEqual(
                    set(snapshot.resources),
                    {
                        resource.value
                        for resource, permission_code in RESOURCE_VIEW_PERMISSIONS.items()
                        if permission_code in expected_permissions
                    },
                )

    def test_superuser_snapshot_projects_all_registered_permissions_and_resources(self):
        self.add_assignment(
            self.admin, "supplymanagement", "supply.business_handler"
        )
        snapshot = permission_snapshot_for_user(self.db, self.admin)

        self.assertTrue(snapshot.is_superuser)
        self.assertEqual(snapshot.assignments, [])
        self.assertEqual(
            {item.code for item in snapshot.permissions},
            {item["code"] for item in PERMISSION_CATALOG},
        )
        self.assertEqual(
            set(snapshot.resources),
            {resource.value for resource in RESOURCE_VIEW_PERMISSIONS},
        )

    def test_disabled_superuser_snapshot_is_empty_with_assignment(self):
        self.add_assignment(
            self.admin, "supplymanagement", "supply.business_handler"
        )
        self.admin.is_active = False
        self.db.commit()

        snapshot = permission_snapshot_for_user(self.db, self.admin)

        self.assertTrue(snapshot.is_superuser)
        self.assertEqual(snapshot.assignments, [])
        self.assertEqual(snapshot.permissions, [])
        self.assertEqual(snapshot.resources, [])
        self.assertEqual(snapshot.company_roles, {})


class PortalPermissionSnapshotHttpIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.contract_user = self._add_user(
            "contract-user", "supplymanagement", "supply.business_handler"
        )
        self.case_only_user = self._add_user(
            "case-only-user",
            "xinhuaproperty",
            "xinhuaproperty.department.employee",
        )
        self.current_user = self.contract_user
        self.app = create_app()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _add_user(
        self, username: str, organization_code: str, position_code: str
    ) -> User:
        user = User(
            username=username,
            full_name=username,
            hashed_password="test",
            role=Role.UNASSIGNED,
        )
        self.db.add(user)
        self.db.flush()
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
        return user

    def test_http_snapshot_exposes_contract_resource_only_with_view_grant(self):
        allowed = self.client.get("/api/v1/portal/me/permissions")
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertIn("invest.legal.contracts", allowed.json()["data"]["resources"])

        self.current_user = self.case_only_user
        denied = self.client.get("/api/v1/portal/me/permissions")
        self.assertEqual(denied.status_code, 200, denied.text)
        self.assertNotIn("invest.legal.contracts", denied.json()["data"]["resources"])


if __name__ == "__main__":
    unittest.main()
