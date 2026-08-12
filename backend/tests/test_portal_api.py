import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.enums import AssignmentStatus, Role
from app.db.base import Base
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.services.organization_catalog import seed_authorization_catalog
from app.services.portal import applications_for_user, permission_snapshot_for_user


class PortalRegistryTest(unittest.TestCase):
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
        self.add_assignment(
            self.admin, "investment", "investment.executive.general_manager"
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
            ["construction", "online", "construction"],
        )
        self.assertEqual([item.accessible for item in apps], [True, False, False])

    def test_superuser_with_platform_assignment_has_no_business_applications(self):
        apps = applications_for_user(self.db, self.admin)

        self.assertEqual([item.accessible for item in apps], [False, False, False])

    def test_product_name_is_unified(self):
        from app.core.config import Settings

        self.assertEqual(Settings().PROJECT_NAME, "山东出版投资有限公司工作平台")

    def test_denied_applications_include_the_required_reason(self):
        apps = applications_for_user(self.db, self.admin)

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

        self.assertEqual(snapshot.company_roles, {"supplymanagement": "invest_director"})

    def test_superuser_snapshot_has_system_identity_without_business_resources(self):
        snapshot = permission_snapshot_for_user(self.db, self.admin)

        self.assertTrue(snapshot.is_superuser)
        self.assertEqual(snapshot.assignments, [])
        self.assertNotIn("supply.contract.view", {item.code for item in snapshot.permissions})
        self.assertEqual(snapshot.resources, [])


if __name__ == "__main__":
    unittest.main()
