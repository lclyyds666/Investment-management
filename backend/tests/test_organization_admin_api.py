import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app
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

    def test_portal_platform_scopes_preserve_only_catalog_targets(self):
        position = self.db.scalar(select(Position).where(Position.code == "supply.business_handler"))
        portal_refs = {
            "supply.portal.enter": "supplymanagement",
            "investment.portal.enter": "investment",
            "fund.portal.enter": "fundmanagement",
        }
        for permission_code, scope_ref in portal_refs.items():
            with self.subTest(permission_code=permission_code):
                links = replace_position_permissions(self.db, position.id, [
                    PositionPermissionWrite(
                        permission_code=permission_code,
                        data_scope=DataScope.PLATFORM,
                        scope_ref=scope_ref,
                    )
                ])
                self.assertEqual(links[0].scope_ref, scope_ref)

        for permission_code, scope_ref in (
            ("supply.portal.enter", "investment"),
            ("investment.portal.enter", "arbitrary"),
            ("supply.contract.view", "supplymanagement"),
        ):
            with self.subTest(permission_code=permission_code, scope_ref=scope_ref):
                with self.assertRaisesRegex(AuthorizationConflictError, "scope"):
                    replace_position_permissions(self.db, position.id, [
                        PositionPermissionWrite(
                            permission_code=permission_code,
                            data_scope=DataScope.PLATFORM,
                            scope_ref=scope_ref,
                        )
                    ])

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


class OrganizationAdminApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        seed_authorization_catalog(self.db)
        self.business_user = User(
            username="directory-user",
            full_name="Directory User",
            hashed_password="test",
            role=Role.UNASSIGNED,
        )
        self.admin = User(
            username="admin",
            full_name="Admin",
            hashed_password="test",
            role=Role.INFO_MAINTAINER,
            is_superuser=True,
        )
        self.worker = User(
            username="worker",
            full_name="Worker",
            hashed_password="test",
            role=Role.UNASSIGNED,
        )
        self.db.add_all([self.business_user, self.admin, self.worker])
        self.db.commit()
        self._assign(self.business_user, "supplymanagement", "supply.business_handler")
        self.app = create_app()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.current_user = self.business_user
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _assign(self, user: User, organization_code: str, position_code: str) -> None:
        self.db.add(UserAssignment(
            user_id=user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == organization_code)
            ),
            position_id=self.db.scalar(select(Position.id).where(Position.code == position_code)),
            valid_from=date(2026, 1, 1),
        ))
        self.db.commit()

    def test_business_user_can_read_directory(self):
        response = self.client.get("/api/v1/organizations/tree")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("username", response.text)
        self.assertNotIn("signature", response.text)

    def test_business_user_cannot_read_permission_templates(self):
        response = self.client.get("/api/v1/organizations/permissions")
        self.assertEqual(response.status_code, 403)

    def test_business_user_cannot_replace_assignments(self):
        response = self.client.put(
            f"/api/v1/organizations/users/{self.worker.id}/assignments",
            json={"assignments": []},
        )
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_read_assignment_history(self):
        self._assign(self.worker, "supplymanagement", "supply.business_handler")
        self.current_user = self.admin

        response = self.client.get(f"/api/v1/organizations/users/{self.worker.id}/assignments")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["organization"]["code"], "supplymanagement")
        self.assertIn("source", response.json()[0])

    def test_assignment_conflicts_return_safe_409_details(self):
        self.current_user = self.admin

        response = self.client.put(
            f"/api/v1/organizations/users/{self.worker.id}/assignments",
            json={
                "assignments": [
                    {
                        "organization_code": "supplymanagement",
                        "position_code": "supply.business_handler",
                        "valid_from": "2026-01-01",
                    },
                    {
                        "organization_code": "supplymanagement",
                        "position_code": "supply.company_leader",
                        "valid_from": "2026-01-01",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "assignment_workflow_conflict")

    def test_duplicate_organization_code_update_returns_409_without_mutation(self):
        self.current_user = self.admin
        organization = self.db.scalar(
            select(Organization).where(Organization.code == "supplymanagement")
        )

        response = self.client.put(
            f"/api/v1/organizations/{organization.id}",
            json={
                "code": "fundmanagement",
                "name": "Renamed Supply",
                "organization_type": "company",
                "company_code": "supplymanagement",
                "sort_order": 20,
                "is_active": True,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "organization_code_exists")
        self.db.expire_all()
        persisted = self.db.get(Organization, organization.id)
        self.assertEqual(persisted.code, "supplymanagement")
        self.assertNotEqual(persisted.name, "Renamed Supply")

    def test_user_update_rejects_company_roles_field(self):
        self.current_user = self.admin

        response = self.client.put(
            f"/api/v1/users/{self.worker.id}",
            json={
                "company_roles": [
                    {"company_code": "supplymanagement", "role": "business_handler"}
                ]
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_user_output_contains_multiple_assignment_summaries(self):
        self._assign(
            self.worker,
            "investment",
            "investment.executive.general_manager",
        )
        self._assign(
            self.worker,
            "supplymanagement",
            "governance.supply_leader",
        )
        self.current_user = self.admin

        response = self.client.get("/api/v1/users")

        self.assertEqual(response.status_code, 200)
        worker = next(item for item in response.json()["data"] if item["id"] == self.worker.id)
        self.assertEqual(
            {item["position_code"] for item in worker["assignment_summaries"]},
            {"investment.executive.general_manager", "governance.supply_leader"},
        )
