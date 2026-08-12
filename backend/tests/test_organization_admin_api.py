import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.enums import DataScope, PositionCategory, Role
from app.db.base import Base
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.schemas.organization_admin import (
    AssignmentWrite,
    ExternalAssignmentWrite,
    GovernanceScopeWrite,
    PositionPermissionWrite,
    UserAssignmentsReplace,
)
from app.services.organization_admin import (
    AuthorizationConflictError,
    replace_position_permissions,
    replace_user_assignments,
)
from app.services.organization_catalog import seed_authorization_catalog


class AssignmentValidationTest(unittest.TestCase):
    def test_allows_multiple_positions_in_same_company(self):
        payload = UserAssignmentsReplace(
            assignments=[
                AssignmentWrite(
                    organization_code="investment",
                    position_code="investment.executive.general_manager",
                    valid_from=date(2026, 1, 1),
                ),
                AssignmentWrite(
                    organization_code="supplymanagement",
                    position_code="governance.supply_leader",
                    valid_from=date(2026, 1, 1),
                    governance_scopes=[
                        GovernanceScopeWrite(scope_type="company", scope_ref="supplymanagement")
                    ],
                ),
            ]
        )
        self.assertEqual(len(payload.assignments), 2)

    def test_external_legal_requires_end_date_and_provider(self):
        with self.assertRaises(ValueError):
            AssignmentWrite(
                organization_code="external.legal",
                position_code="external.legal_counsel",
                valid_from=date(2026, 1, 1),
                external=ExternalAssignmentWrite(
                    provider_name="",
                    service_scopes=[],
                ),
            )

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            AssignmentWrite(
                organization_code="supplymanagement",
                position_code="supply.business_handler",
                valid_from=date(2026, 2, 1),
                valid_until=date(2026, 1, 31),
            )

    def test_governance_assignment_requires_target_company_scope(self):
        with self.assertRaises(ValueError):
            AssignmentWrite(
                organization_code="supplymanagement",
                position_code="governance.supply_leader",
                valid_from=date(2026, 1, 1),
            )

        with self.assertRaises(ValueError):
            AssignmentWrite(
                organization_code="supplymanagement",
                position_code="governance.supply_leader",
                valid_from=date(2026, 1, 1),
                governance_scopes=[
                    GovernanceScopeWrite(scope_type="company", scope_ref="fundmanagement")
                ],
            )

    def test_external_legal_rejects_blank_provider_and_scopes(self):
        for provider_name, service_scopes in (("   ", ["review"]), ("firm", [" "])):
            with self.subTest(provider_name=provider_name, service_scopes=service_scopes):
                with self.assertRaises(ValueError):
                    AssignmentWrite(
                        organization_code="external.legal",
                        position_code="external.legal_counsel",
                        valid_from=date(2026, 1, 1),
                        valid_until=date(2026, 12, 31),
                        external=ExternalAssignmentWrite(
                            provider_name=provider_name,
                            service_scopes=service_scopes,
                        ),
                    )


class OrganizationAdminServiceValidationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.user = User(
            username="worker",
            full_name="Worker",
            hashed_password="test",
            role=Role.UNASSIGNED,
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_governance_assignment_must_use_its_target_organization(self):
        payload = UserAssignmentsReplace(assignments=[
            AssignmentWrite(
                organization_code="fundmanagement",
                position_code="governance.supply_leader",
                valid_from=date(2026, 1, 1),
                governance_scopes=[
                    GovernanceScopeWrite(scope_type="company", scope_ref="supplymanagement")
                ],
            )
        ])

        with self.assertRaisesRegex(AuthorizationConflictError, "target subsidiary"):
            replace_user_assignments(self.db, self.user.id, payload)

    def test_permission_scope_refs_resolve_active_catalog_targets(self):
        position = self.db.scalar(select(Position).where(Position.code == "supply.business_handler"))
        company_scope = PositionPermissionWrite(
            permission_code="supply.contract.view",
            data_scope=DataScope.COMPANY,
            scope_ref="supplymanagement",
        )
        links = replace_position_permissions(self.db, position.id, [company_scope])
        self.assertEqual(links[0].scope_ref, "supplymanagement")

        invalid_scope = PositionPermissionWrite(
            permission_code="supply.contract.view",
            data_scope=DataScope.BUSINESS_DOMAIN,
            scope_ref="unknown",
        )
        with self.assertRaisesRegex(AuthorizationConflictError, "scope"):
            replace_position_permissions(self.db, position.id, [invalid_scope])

    def test_assignment_replacement_returns_committed_reloaded_rows(self):
        payload = UserAssignmentsReplace(assignments=[
            AssignmentWrite(
                organization_code="supplymanagement",
                position_code="supply.business_handler",
                valid_from=date(2026, 1, 1),
            )
        ])

        assignments = replace_user_assignments(self.db, self.user.id, payload)

        self.assertEqual(len(assignments), 1)
        self.assertIsNotNone(assignments[0].id)
        self.assertEqual(assignments[0].organization.code, "supplymanagement")
        self.assertEqual(assignments[0].position.code, "supply.business_handler")
        self.assertEqual(
            self.db.scalar(select(UserAssignment).where(UserAssignment.id == assignments[0].id)).user_id,
            self.user.id,
        )

    def test_assignment_replacement_persists_external_detail(self):
        payload = UserAssignmentsReplace(assignments=[
            AssignmentWrite(
                organization_code="external.legal",
                position_code="external.legal_counsel",
                valid_from=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
                external=ExternalAssignmentWrite(
                    provider_name=" Counsel Firm ",
                    service_scopes=[" contract_review "],
                ),
            )
        ])

        assignments = replace_user_assignments(self.db, self.user.id, payload)

        self.assertEqual(assignments[0].external_detail.provider_name, "Counsel Firm")
        self.assertEqual(assignments[0].external_detail.service_scopes, ["contract_review"])
