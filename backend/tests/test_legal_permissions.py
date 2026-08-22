import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.enums import AssignmentStatus, DataScope, OrganizationType, PermissionAction, PositionCategory, Role
from app.db.base import Base
from app.models.organization import Organization, Permission, Position, PositionPermission, UserAssignment
from app.models.user import User
from app.services.legal_permissions import (
    LegalCapability,
    access_context,
    capabilities_for,
    capabilities_for_positions,
)


class LegalPermissionMatrixTest(unittest.TestCase):
    def test_business_and_risk_have_identical_permissions(self):
        self.assertEqual(
            capabilities_for(Role.BUSINESS_HANDLER),
            capabilities_for(Role.RISK_AUDITOR),
        )
        self.assertIn(LegalCapability.EDIT_CASE, capabilities_for(Role.BUSINESS_HANDLER))

    def test_management_role_is_read_only(self):
        capabilities = capabilities_for(Role.INVEST_DIRECTOR)
        self.assertIn(LegalCapability.VIEW_CASE, capabilities)
        self.assertIn(LegalCapability.VIEW_STATISTICS, capabilities)
        self.assertNotIn(LegalCapability.EDIT_CASE, capabilities)

    def test_superuser_has_maximum_permissions(self):
        capabilities = capabilities_for(None, is_superuser=True)
        self.assertEqual(capabilities, frozenset(LegalCapability))

    def test_counsel_cannot_manage_case_master_data(self):
        capabilities = capabilities_for(Role.LEGAL_COUNSEL)
        self.assertIn(LegalCapability.ADD_COUNSEL_CONTENT, capabilities)
        self.assertNotIn(LegalCapability.EDIT_CASE, capabilities)
        self.assertNotIn(LegalCapability.VIEW_STATISTICS, capabilities)

    def test_management_and_business_assignments_union_capabilities(self):
        capabilities = capabilities_for_positions({
            "investment.executive.general_manager",
            "investment.department.junior_manager",
        })

        self.assertIn(LegalCapability.EDIT_CASE, capabilities)
        self.assertIn(LegalCapability.EXPORT_MANAGEMENT, capabilities)

    def test_access_context_uses_effective_position_permissions_not_legacy_role(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            organization = Organization(
                code="supplymanagement", name="供管", company_code="supplymanagement",
                organization_type=OrganizationType.COMPANY, is_active=True,
            )
            position = Position(
                code="custom.legal.viewer", name="查看人",
                category=PositionCategory.BUSINESS, is_active=True,
            )
            permission = Permission(
                code="investment.legal.cases.view", name="法务案件查看",
                resource="investment.legal.cases", action=PermissionAction.VIEW,
                is_active=True,
            )
            user = User(
                username="legacy-risk", full_name="旧法务角色", hashed_password="hashed",
                role=Role.RISK_AUDITOR, is_active=True,
            )
            db.add_all([organization, position, permission, user])
            db.flush()
            db.add_all([
                PositionPermission(
                    position_id=position.id, permission_id=permission.id,
                    data_scope=DataScope.PLATFORM, scope_ref="",
                ),
                UserAssignment(
                    user_id=user.id, organization_id=organization.id, position_id=position.id,
                    valid_from=date(2026, 1, 1), status=AssignmentStatus.ACTIVE,
                ),
            ])
            db.commit()

            context = access_context(db, user)

            self.assertEqual(context.capabilities, frozenset({LegalCapability.VIEW_CASE}))

            permission.is_active = False
            db.commit()
            with self.assertRaises(HTTPException):
                access_context(db, user)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
