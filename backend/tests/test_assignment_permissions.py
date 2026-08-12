import unittest
from datetime import date

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.core.enums import AssignmentStatus, DataScope, Role
from app.db.base import Base
from app.models.organization import (
    ExternalAssignment,
    GovernanceScope,
    Organization,
    Permission,
    Position,
    PositionPermission,
    UserAssignment,
)
from app.models.portal import UserCompanyRole
from app.models.user import User
from app.services.legacy_assignment_migration import legacy_target, migrate_legacy_assignments
from app.services.organization_catalog import (
    ORGANIZATION_CATALOG,
    PERMISSION_CATALOG,
    POSITION_CATALOG,
    POSITION_GRANTS,
    seed_authorization_catalog,
)
from app.services.assignment_permissions import (
    PermissionContext,
    active_assignments,
    has_permission,
    has_position,
    permission_grants,
)


class AuthorizationCatalogTest(unittest.TestCase):
    def test_required_organizations_exist(self):
        codes = {item["code"] for item in ORGANIZATION_CATALOG}
        self.assertTrue({
            "investment",
            "investment.general",
            "investment.investment_management",
            "investment.legal_risk",
            "investment.asset_finance",
            "supplymanagement",
            "fundmanagement",
            "external.legal",
        }.issubset(codes))

    def test_required_positions_exist(self):
        codes = {item["code"] for item in POSITION_CATALOG}
        self.assertTrue({
            "investment.executive.chairman",
            "investment.executive.general_manager",
            "investment.executive.deputy_general_manager",
            "investment.department.director",
            "investment.department.deputy_director",
            "investment.department.senior_manager",
            "investment.department.middle_manager",
            "investment.department.junior_manager",
            "supply.business_handler",
            "supply.business_reviewer",
            "supply.company_leader",
            "supply.finance_handler",
            "governance.supply_leader",
            "fund.chairman",
            "fund.general_manager",
            "governance.fund_leader",
            "investment.duty.supply_risk_review",
            "investment.duty.supply_finance_review",
            "external.legal_counsel",
        }.issubset(codes))

    def test_permission_codes_cover_current_supply_modules(self):
        codes = {item["code"] for item in PERMISSION_CATALOG}
        self.assertTrue({
            "supply.portal.enter",
            "supply.dashboard.view",
            "supply.operation.view",
            "supply.scenic.update",
            "supply.scenic.review",
            "supply.finance.update",
            "supply.contract.submit",
            "supply.contract.approve",
            "supply.approval.submit",
            "supply.approval.approve",
            "supply.customer.update",
            "supply.channel.configure",
            "organization.directory.view",
        }.issubset(codes))

    def test_business_handler_has_the_independent_scenic_delete_grant(self):
        self.assertIn(
            "supply.scenic.delete",
            {item["code"] for item in PERMISSION_CATALOG},
        )
        delete_grantees = {
            item["position_code"]
            for item in POSITION_GRANTS
            if item["permission_code"] == "supply.scenic.delete"
        }
        self.assertEqual(delete_grantees, {"supply.business_handler"})

    def test_legacy_roles_map_to_confirmed_positions(self):
        self.assertEqual(
            legacy_target(Role.INVEST_DIRECTOR).position_code,
            "governance.supply_leader",
        )
        self.assertEqual(
            legacy_target(Role.RISK_AUDITOR).position_code,
            "investment.duty.supply_risk_review",
        )
        self.assertEqual(
            legacy_target(Role.FINANCE_REVIEWER).position_code,
            "investment.duty.supply_finance_review",
        )
        self.assertEqual(
            legacy_target(Role.LEGAL_COUNSEL).position_code,
            "external.legal_counsel",
        )
        self.assertIsNone(legacy_target(Role.INFO_MAINTAINER))


class AssignmentPermissionServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.multi_role_user = self.add_user("multi-role", Role.UNASSIGNED)
        self.expired_user = self.add_user("expired", Role.UNASSIGNED)
        self.legal_user = self.add_user("legal", Role.UNASSIGNED)
        self.admin = self.add_user("admin", Role.INFO_MAINTAINER, is_superuser=True)
        self.add_assignment(self.multi_role_user, "supplymanagement", "supply.business_handler")
        self.add_assignment(self.multi_role_user, "fundmanagement", "fund.chairman")
        self.add_assignment(
            self.expired_user,
            "supplymanagement",
            "supply.business_handler",
            valid_until=date(2026, 8, 11),
        )
        self.add_assignment(self.legal_user, "external.legal", "external.legal_counsel")

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

    def add_assignment(
        self,
        user: User,
        organization_code: str,
        position_code: str,
        valid_from: date = date(2026, 1, 1),
        valid_until: date | None = None,
    ) -> UserAssignment:
        assignment = UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == position_code)
            ),
            valid_from=valid_from,
            valid_until=valid_until,
            status=AssignmentStatus.ACTIVE,
        )
        self.db.add(assignment)
        self.db.commit()
        return assignment

    def test_multiple_assignments_union_permissions(self):
        grants = permission_grants(self.db, self.multi_role_user.id, on_date=date(2026, 8, 12))
        codes = {grant.code for grant in grants}
        self.assertIn("supply.contract.submit", codes)
        self.assertIn("fund.portal.enter", codes)

    def test_expired_assignment_does_not_grant_access(self):
        self.assertFalse(
            has_position(
                self.db,
                self.expired_user.id,
                "supply.business_handler",
                on_date=date(2026, 8, 12),
            )
        )

    def test_assignment_end_date_is_inclusive(self):
        self.assertTrue(
            has_position(
                self.db,
                self.expired_user.id,
                "supply.business_handler",
                on_date=date(2026, 8, 11),
            )
        )

    def test_assigned_scope_requires_matching_user(self):
        permission = "supply.contract.review"
        self.assertTrue(has_permission(
            self.db,
            self.legal_user,
            permission,
            PermissionContext(assigned_user_id=self.legal_user.id),
        ))
        self.assertFalse(has_permission(
            self.db,
            self.legal_user,
            permission,
            PermissionContext(assigned_user_id=999),
        ))
        self.assertFalse(has_permission(self.db, self.legal_user, permission))

    def test_inactive_grant_members_do_not_authorize(self):
        assignment = self.add_assignment(
            self.expired_user,
            "supplymanagement",
            "supply.business_handler",
            valid_from=date(2026, 8, 12),
        )
        organization = assignment.organization
        position = assignment.position
        permission = self.db.scalar(
            select(Permission).where(Permission.code == "supply.contract.submit")
        )

        for subject in (organization, position, permission):
            subject.is_active = False
            self.db.commit()
            self.assertFalse(has_permission(
                self.db,
                self.expired_user,
                "supply.contract.submit",
                PermissionContext(company_code="supplymanagement"),
            ))
            subject.is_active = True
            self.db.commit()

        assignment.status = AssignmentStatus.INACTIVE
        self.db.commit()
        self.assertEqual(active_assignments(self.db, self.expired_user.id, date(2026, 8, 12)), [])

    def test_scoped_permissions_fail_closed_without_required_context(self):
        grant = self.db.scalar(
            select(PositionPermission).join(Permission).where(
                PositionPermission.position_id == self.db.scalar(
                    select(Position.id).where(Position.code == "supply.business_handler")
                ),
                Permission.code == "supply.contract.submit",
            )
        )
        grant.data_scope = DataScope.OWN
        self.db.commit()

        self.assertFalse(has_permission(
            self.db,
            self.multi_role_user,
            "supply.contract.submit",
        ))
        self.assertTrue(has_permission(
            self.db,
            self.multi_role_user,
            "supply.contract.submit",
            PermissionContext(owner_id=self.multi_role_user.id),
        ))

    def test_superuser_has_no_implicit_business_permission(self):
        self.assertFalse(
            has_permission(
                self.db,
                self.admin,
                "supply.contract.approve",
                PermissionContext(company_code="supplymanagement"),
            )
        )


class LegacyAssignmentMigrationTest(unittest.TestCase):
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

    def authorization_state(self) -> dict[str, tuple[tuple[object, ...], ...]]:
        models = (
            Organization,
            Position,
            Permission,
            PositionPermission,
            UserAssignment,
            GovernanceScope,
            ExternalAssignment,
        )
        return {
            model.__tablename__: tuple(
                tuple(row)
                for row in self.db.execute(
                    select(*model.__table__.columns).order_by(model.id)
                )
            )
            for model in models
        }

    def test_repeat_migration_creates_no_duplicate_assignments(self):
        user = self.add_user("handler", Role.BUSINESS_HANDLER)

        first = migrate_legacy_assignments(self.db, dry_run=False)
        second = migrate_legacy_assignments(self.db, dry_run=False)

        assignments = self.db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        self.assertEqual(first.created, 1)
        self.assertEqual(second.created, 0)
        self.assertEqual(second.existing, 1)
        self.assertEqual(second.existing_rows[0].username, "handler")
        self.assertEqual(len(assignments), 1)

    def test_dry_run_does_not_persist_assignments(self):
        user = self.add_user("preview", Role.BUSINESS_HANDLER)
        before = self.authorization_state()

        report = migrate_legacy_assignments(self.db, dry_run=True)

        after = self.authorization_state()
        assignments = self.db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        self.assertEqual(report.created, 1)
        self.assertEqual(after, before)
        self.assertEqual(assignments, [])

    def test_dry_run_preserves_caller_pending_changes(self):
        self.add_user("preview", Role.BUSINESS_HANDLER)
        pending_user = User(
            username="pending",
            full_name="pending",
            hashed_password="test",
            role=Role.UNASSIGNED,
        )
        self.db.add(pending_user)

        migrate_legacy_assignments(self.db, dry_run=True)

        self.assertIn(pending_user, self.db.new)
        self.db.commit()
        self.assertIsNotNone(
            self.db.scalar(select(User).where(User.username == "pending"))
        )

    def test_supply_company_role_takes_precedence_over_legacy_user_role(self):
        user = self.add_user("company-role", Role.FINANCE_HANDLER)
        self.db.add(UserCompanyRole(
            user_id=user.id,
            company_code="supplymanagement",
            role=Role.BUSINESS_REVIEWER,
        ))
        self.db.commit()

        migrate_legacy_assignments(self.db, dry_run=False)

        assignment = self.db.scalar(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        )
        self.assertEqual(assignment.position.code, "supply.business_reviewer")

    def test_user_role_is_used_when_no_supply_company_role_exists(self):
        user = self.add_user("user-role", Role.FINANCE_HANDLER)

        migrate_legacy_assignments(self.db, dry_run=False)

        assignment = self.db.scalar(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        )
        self.assertEqual(assignment.position.code, "supply.finance_handler")

    def test_manual_assignment_is_preserved_as_existing(self):
        user = self.add_user("manual", Role.BUSINESS_HANDLER)
        organization = self.db.scalar(
            select(Organization).where(Organization.code == "supplymanagement")
        )
        position = self.db.scalar(
            select(Position).where(Position.code == "supply.business_handler")
        )
        manual_assignment = UserAssignment(
            user_id=user.id,
            organization_id=organization.id,
            position_id=position.id,
            valid_from=date.today(),
            status=AssignmentStatus.ACTIVE,
            source="manual",
        )
        self.db.add(manual_assignment)
        self.db.commit()

        report = migrate_legacy_assignments(self.db, dry_run=False)

        assignments = self.db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        self.assertEqual(report.existing, 1)
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].source, "manual")

    def test_missing_catalog_code_rolls_back_migration(self):
        handler = self.add_user("handler", Role.BUSINESS_HANDLER)
        self.add_user("reviewer", Role.BUSINESS_REVIEWER)
        self.db.execute(
            delete(Position).where(Position.code == "supply.business_reviewer")
        )
        self.db.commit()

        report = migrate_legacy_assignments(self.db, dry_run=False)

        assignments = self.db.scalars(select(UserAssignment)).all()
        self.assertEqual(assignments, [])
        self.assertEqual(len(report.unresolved), 1)
        self.assertIn("position", report.unresolved[0].reason)

    def test_unassigned_role_is_skipped_without_an_error(self):
        user = self.add_user("unassigned", Role.UNASSIGNED)

        report = migrate_legacy_assignments(self.db, dry_run=False)

        assignments = self.db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        self.assertEqual(report.skipped_unassigned, 1)
        self.assertEqual(report.unresolved, [])
        self.assertEqual(assignments, [])
        self.assertEqual(report.skipped_unassigned_rows[0].username, "unassigned")

    def test_information_maintainer_creates_no_business_assignment(self):
        user = self.add_user("maintainer", Role.INFO_MAINTAINER)

        report = migrate_legacy_assignments(self.db, dry_run=False)

        assignments = self.db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        self.assertEqual(report.created, 0)
        self.assertEqual(assignments, [])
        self.assertEqual(len(report.unresolved), 1)
        self.assertIn("No normalized position mapping", report.unresolved[0].reason)

    def test_superuser_receives_no_business_assignment(self):
        user = self.add_user("admin", Role.BUSINESS_HANDLER, is_superuser=True)

        report = migrate_legacy_assignments(self.db, dry_run=False)

        assignments = self.db.scalars(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        ).all()
        self.assertEqual(report.skipped_admin, 1)
        self.assertEqual(assignments, [])
        self.assertEqual(report.skipped_admin_rows[0].username, "admin")

    def test_legal_counsel_requires_end_date_confirmation(self):
        user = self.add_user("legal", Role.LEGAL_COUNSEL)

        report = migrate_legacy_assignments(self.db, dry_run=False)

        assignment = self.db.scalar(
            select(UserAssignment).where(UserAssignment.user_id == user.id)
        )
        external = self.db.scalar(
            select(ExternalAssignment).where(ExternalAssignment.assignment_id == assignment.id)
        )
        self.assertEqual(report.created, 1)
        self.assertTrue(report.unresolved)
        self.assertIn("effective end date", report.unresolved[0].reason)
        self.assertEqual(external.service_scopes, ["contract_legal_review"])
        self.assertEqual(report.created_rows[0].username, "legal")
