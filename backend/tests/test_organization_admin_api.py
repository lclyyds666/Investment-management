import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.core.enums import DataScope, OrganizationType, PermissionAction, PositionCategory, Role
from app.db.base import Base
from app.models.organization import ExternalAssignment, GovernanceScope, Organization, Permission, Position, PositionPermission, UserAssignment
from app.models.audit import AuditLog
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

    def test_catalog_seed_is_idempotent_and_refreshes_managed_labels(self):
        supply_organization = self.db.scalar(
            select(Organization).where(Organization.code == "supplymanagement")
        )
        supply = self.db.scalar(select(Position).where(Position.code == "supply.business_handler"))
        legal_alert = self.db.scalar(select(Permission).where(Permission.code == "investment.legal.alerts.view"))
        supply_organization.organization_type = OrganizationType.DEPARTMENT
        supply_organization.company_code = "custom-company"
        supply_organization.sort_order = 999
        supply.name = "旧名称"
        supply.category = PositionCategory.DUTY
        legal_alert.name = "old name"
        legal_alert.resource = "old.resource"
        legal_alert.action = PermissionAction.CREATE
        self.db.commit()
        before = {
            "organizations": self.db.scalar(select(func.count()).select_from(Organization)),
            "positions": self.db.scalar(select(func.count()).select_from(Position)),
            "permissions": self.db.scalar(select(func.count()).select_from(Permission)),
            "grants": self.db.scalar(select(func.count()).select_from(PositionPermission)),
        }

        seed_authorization_catalog(self.db)
        after_first = {
            "organizations": self.db.scalar(select(func.count()).select_from(Organization)),
            "positions": self.db.scalar(select(func.count()).select_from(Position)),
            "permissions": self.db.scalar(select(func.count()).select_from(Permission)),
            "grants": self.db.scalar(select(func.count()).select_from(PositionPermission)),
        }
        seed_authorization_catalog(self.db)
        after_second = {
            "organizations": self.db.scalar(select(func.count()).select_from(Organization)),
            "positions": self.db.scalar(select(func.count()).select_from(Position)),
            "permissions": self.db.scalar(select(func.count()).select_from(Permission)),
            "grants": self.db.scalar(select(func.count()).select_from(PositionPermission)),
        }

        self.assertEqual(supply.name, "供管公司初级经理")
        self.assertEqual(supply.category, PositionCategory.DUTY)
        self.assertEqual(supply_organization.organization_type, OrganizationType.DEPARTMENT)
        self.assertEqual(supply_organization.company_code, "custom-company")
        self.assertEqual(supply_organization.sort_order, 999)
        self.assertEqual(legal_alert.name, "法务预警查看")
        self.assertEqual(legal_alert.resource, "investment.legal.alerts")
        self.assertEqual(legal_alert.action, PermissionAction.CREATE)
        self.assertEqual(before, after_first)
        self.assertEqual(after_first, after_second)

    def test_catalog_seed_preserves_existing_permission_grant_changes(self):
        position = self.db.scalar(select(Position).where(Position.code == "supply.business_handler"))
        permission = self.db.scalar(select(Permission).where(Permission.code == "supply.contract.view"))
        grant = self.db.scalar(select(PositionPermission).where(
            PositionPermission.position_id == position.id,
            PositionPermission.permission_id == permission.id,
            PositionPermission.data_scope == DataScope.COMPANY,
            PositionPermission.scope_ref == "supplymanagement",
        ))
        self.assertIsNotNone(grant)
        self.db.delete(grant)
        self.db.commit()

        seed_authorization_catalog(self.db)

        self.assertIsNone(self.db.scalar(select(PositionPermission).where(
            PositionPermission.position_id == position.id,
            PositionPermission.permission_id == permission.id,
            PositionPermission.data_scope == DataScope.COMPANY,
            PositionPermission.scope_ref == "supplymanagement",
        )))

    def test_catalog_seed_adds_new_permission_once_without_restoring_removed_grant(self):
        position = self.db.scalar(select(Position).where(Position.code == "supply.business_handler"))
        permission = self.db.scalar(select(Permission).where(Permission.code == "organization.directory.view"))
        self.db.query(PositionPermission).filter(
            PositionPermission.permission_id == permission.id
        ).delete()
        self.db.delete(permission)
        self.db.commit()

        seed_authorization_catalog(self.db)

        recreated_permission = self.db.scalar(select(Permission).where(
            Permission.code == "organization.directory.view"
        ))
        grant = self.db.scalar(select(PositionPermission).where(
            PositionPermission.position_id == position.id,
            PositionPermission.permission_id == recreated_permission.id,
            PositionPermission.data_scope == DataScope.COMPANY,
            PositionPermission.scope_ref == "supplymanagement",
        ))
        self.assertIsNotNone(grant)
        self.db.delete(grant)
        self.db.commit()

        seed_authorization_catalog(self.db)

        self.assertIsNone(self.db.scalar(select(PositionPermission).where(
            PositionPermission.position_id == position.id,
            PositionPermission.permission_id == recreated_permission.id,
            PositionPermission.data_scope == DataScope.COMPANY,
            PositionPermission.scope_ref == "supplymanagement",
        )))

    def test_catalog_seed_grants_defaults_to_new_catalog_position(self):
        position = self.db.scalar(select(Position).where(Position.code == "zhanwei.general_manager"))
        self.db.delete(position)
        self.db.commit()

        seed_authorization_catalog(self.db)

        recreated = self.db.scalar(select(Position).where(Position.code == "zhanwei.general_manager"))
        directory_permission = self.db.scalar(select(Permission).where(Permission.code == "organization.directory.view"))
        self.assertIsNotNone(self.db.scalar(select(PositionPermission).where(
            PositionPermission.position_id == recreated.id,
            PositionPermission.permission_id == directory_permission.id,
            PositionPermission.data_scope == DataScope.COMPANY,
            PositionPermission.scope_ref == "supplymanagement",
        )))

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

    def test_assignment_replace_records_structured_before_after(self):
        admin = User(
            username="audit-admin",
            full_name="Audit Admin",
            hashed_password="test",
            role=Role.INFO_MAINTAINER,
            is_superuser=True,
        )
        self.db.add(admin)
        self.db.commit()
        self.db.add(UserAssignment(
            user_id=self.user.id,
            organization_id=self.db.scalar(
                select(Organization.id).where(Organization.code == "supplymanagement")
            ),
            position_id=self.db.scalar(
                select(Position.id).where(Position.code == "supply.business_handler")
            ),
            valid_from=date(2026, 1, 1),
        ))
        self.db.commit()
        payload = UserAssignmentsReplace(assignments=[
            AssignmentWrite(
                organization_code="supplymanagement",
                position_code="supply.business_reviewer",
                valid_from=date(2026, 1, 1),
            )
        ])

        replace_user_assignments(
            self.db,
            actor=admin,
            target_user=self.user,
            payload=payload,
            reason="岗位调整",
        )

        row = self.db.scalar(select(AuditLog).where(AuditLog.action == "assignment_replace"))
        self.assertEqual(
            self.db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == "assignment_replace"
                )
            ),
            1,
        )
        self.assertEqual(row.reason, "岗位调整")
        self.assertIn(
            "supply.business_handler",
            {item["position_code"] for item in row.before_json},
        )
        self.assertIn(
            "supply.business_reviewer",
            {item["position_code"] for item in row.after_json},
        )
        self.assertEqual(row.position_code, "system.information_maintainer")

    def test_assignment_audit_snapshot_preserves_sorted_scopes_and_terms(self):
        admin = User(
            username="snapshot-admin", full_name="Snapshot Admin", hashed_password="test",
            role=Role.INFO_MAINTAINER, is_superuser=True,
        )
        external_organization = self.db.scalar(
            select(Organization).where(Organization.code == "external.legal")
        )
        external_position = self.db.scalar(
            select(Position).where(Position.code == "external.legal_counsel")
        )
        old_assignment = UserAssignment(
            user_id=self.user.id, organization_id=external_organization.id,
            position_id=external_position.id, valid_from=date(2026, 1, 1),
            valid_until=date(2026, 6, 30),
        )
        self.db.add_all([admin, old_assignment])
        self.db.flush()
        self.db.add_all([
            GovernanceScope(assignment_id=old_assignment.id, scope_type="department", scope_ref="legal"),
            GovernanceScope(assignment_id=old_assignment.id, scope_type="company", scope_ref="supplymanagement"),
            ExternalAssignment(
                assignment_id=old_assignment.id, provider_name="Old Counsel",
                service_scopes=["litigation", "contract_review"],
            ),
        ])
        self.db.commit()
        payload = UserAssignmentsReplace(assignments=[
            AssignmentWrite(
                organization_code="external.legal", position_code="external.legal_counsel",
                valid_from=date(2026, 7, 1), valid_until=date(2026, 12, 31),
                external=ExternalAssignmentWrite(
                    provider_name="New Counsel", service_scopes=["due_diligence", "contract_review"],
                ),
            )
        ])

        replace_user_assignments(
            self.db, actor=admin, target_user=self.user, payload=payload, reason="外聘续约",
        )

        row = self.db.scalar(select(AuditLog).where(AuditLog.action == "assignment_replace"))
        self.assertEqual(row.before_json[0]["valid_until"], "2026-06-30")
        self.assertEqual(row.before_json[0]["governance_scopes"], [
            {"scope_type": "company", "scope_ref": "supplymanagement"},
            {"scope_type": "department", "scope_ref": "legal"},
        ])
        self.assertEqual(row.before_json[0]["external"], {
            "provider_name": "Old Counsel",
            "service_scopes": ["contract_review", "litigation"],
        })
        self.assertEqual(row.after_json[0]["valid_from"], "2026-07-01")
        self.assertEqual(row.after_json[0]["external"]["service_scopes"], [
            "contract_review", "due_diligence",
        ])


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

    def test_permission_catalog_exposes_chinese_names(self):
        self.current_user = self.admin

        response = self.client.get("/api/v1/organizations/permissions")

        self.assertEqual(response.status_code, 200)
        permissions = {item["code"]: item for item in response.json()}
        self.assertEqual(permissions["investment.legal.alerts.view"]["name"], "法务预警查看")
        self.assertEqual(permissions["investment.legal.contracts.submit"]["name"], "法务合同提交")
        self.assertEqual(permissions["investment.legal.contracts.submit"]["resource_name"], "法务合同")

    def test_business_user_cannot_read_system_audit_apis(self):
        for method, path in (
            ("get", "/api/v1/audit/meta"),
            ("get", "/api/v1/audit/logs"),
            ("get", "/api/v1/ai-assistant/admin/conversations"),
            ("get", "/api/v1/ai-assistant/admin/conversations/999999"),
            ("delete", "/api/v1/ai-assistant/admin/conversations/999999?reason=unauthorized"),
            ("get", "/api/v1/ai-assistant/admin/deletion-audits"),
        ):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path).status_code, 403)

    def test_business_user_cannot_read_position_templates(self):
        response = self.client.get("/api/v1/organizations/positions")
        self.assertEqual(response.status_code, 403)

    def test_superuser_positions_include_deterministic_permission_templates_only(self):
        self.current_user = self.admin

        response = self.client.get("/api/v1/organizations/positions")

        self.assertEqual(response.status_code, 200)
        position = next(item for item in response.json() if item["code"] == "external.legal_counsel")
        self.assertTrue(position["is_active"])
        self.assertEqual(position["permissions"], [
            {
                "permission_code": "investment.legal.alerts.view",
                "data_scope": "company",
                "scope_ref": "investment",
            },
            {
                "permission_code": "investment.legal.cases.view",
                "data_scope": "company",
                "scope_ref": "investment",
            },
            {
                "permission_code": "investment.portal.enter",
                "data_scope": "platform",
                "scope_ref": "investment",
            },
            {
                "permission_code": "supply.contract.review",
                "data_scope": "assigned",
                "scope_ref": "",
            },
            {
                "permission_code": "supply.contract.view",
                "data_scope": "assigned",
                "scope_ref": "",
            },
            {
                "permission_code": "supply.portal.enter",
                "data_scope": "platform",
                "scope_ref": "supplymanagement",
            },
        ])
        self.assertNotIn("assignments", position)
        self.assertNotIn("users", position)

    def test_business_user_cannot_replace_assignments(self):
        response = self.client.put(
            f"/api/v1/organizations/users/{self.worker.id}/assignments?reason=无权限操作",
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
            f"/api/v1/organizations/users/{self.worker.id}/assignments?reason=岗位调整",
            json={
                "assignments": [
                    {
                        "organization_code": "supplymanagement",
                        "position_code": "supply.business_handler",
                        "valid_from": "2026-01-01",
                        "client_ref": "row-handler",
                    },
                    {
                        "organization_code": "supplymanagement",
                        "position_code": "supply.company_leader",
                        "valid_from": "2026-01-01",
                        "client_ref": "row-leader",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "assignment_workflow_conflict")
        self.assertEqual(response.json()["detail"]["assignment_ids"], [])
        self.assertEqual(response.json()["detail"]["conflicting_client_refs"], ["row-handler", "row-leader"])

    def test_duplicate_organization_code_update_returns_409_without_mutation(self):
        self.current_user = self.admin
        organization = self.db.scalar(
            select(Organization).where(Organization.code == "supplymanagement")
        )

        response = self.client.put(
            f"/api/v1/organizations/{organization.id}?reason=组织调整",
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

    def test_successful_organization_write_uses_only_explicit_audit(self):
        self.current_user = self.admin

        with patch("app.core.audit.write_log") as write_log:
            response = self.client.post(
                "/api/v1/organizations?reason=%20新增组织%20",
                json={
                    "code": "audit-test", "name": "Audit Test", "organization_type": "department",
                    "parent_code": "supplymanagement", "company_code": "supplymanagement",
                    "sort_order": 99, "is_active": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(write_log.call_count, 0)
        rows = self.db.scalars(select(AuditLog).where(AuditLog.action == "organization_create")).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reason, "新增组织")

    def test_rejected_organization_write_keeps_failed_generic_audit(self):
        self.current_user = self.admin

        with patch("app.core.audit.write_log") as write_log:
            response = self.client.put(
                "/api/v1/organizations/999999?reason=组织调整",
                json={
                    "code": "audit-missing", "name": "Missing", "organization_type": "department",
                    "parent_code": "supplymanagement", "company_code": "supplymanagement",
                    "sort_order": 99, "is_active": True,
                },
            )

        self.assertEqual(response.status_code, 409)
        write_log.assert_called_once()
        self.assertEqual(write_log.call_args.kwargs["status"], "fail")
        self.assertEqual(write_log.call_args.kwargs["http_status"], 409)
        self.assertIsNone(self.db.scalar(select(AuditLog).where(AuditLog.action == "organization_update")))

    def test_authorization_writes_require_nonblank_reason(self):
        self.current_user = self.admin

        response = self.client.post(
            "/api/v1/organizations?reason=%20%20%20",
            json={
                "code": "blank-reason", "name": "Blank Reason", "organization_type": "department",
                "parent_code": "supplymanagement", "company_code": "supplymanagement",
                "sort_order": 99, "is_active": True,
            },
        )

        self.assertEqual(response.status_code, 422)

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
