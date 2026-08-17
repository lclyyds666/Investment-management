import unittest
from datetime import date, timedelta
from decimal import Decimal

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.db.base import Base
from app.models.legal_risk import LegalCase, LegalCaseAsset, LegalCaseStage, LegalCaseStatus
from app.models.portal import UserCompanyRole
from app.models.user import User
from app.services.legal_permissions import LegalAccessContext, LegalCapability
from app.services.legal_statistics import (
    LegalCaseFilters,
    dashboard_statistics,
    export_cases_workbook,
    status_statistics,
)


class LegalStatisticsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(username="admin", full_name="管理员", hashed_password="x",
                         role=Role.INFO_MAINTAINER, is_superuser=True, is_active=True)
        self.db.add(self.user); self.db.commit()
        self.access = LegalAccessContext(
            user_id=self.user.id, role=None, is_superuser=True,
            capabilities=frozenset(LegalCapability),
        )

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_six_statuses_and_total_are_always_returned(self):
        rows = status_statistics(self.db, LegalCaseFilters(), self.access)
        self.assertEqual([row["status"] for row in rows[:-1]], [item.value for item in LegalCaseStatus])
        self.assertEqual(rows[-1]["status"], "total")

    def test_draft_is_excluded_from_dashboard(self):
        self.db.add(LegalCase(stage=LegalCaseStage.DRAFT, case_name="草稿", subject_amount=Decimal("1"),
                              created_by=self.user.id))
        self.db.commit()
        self.assertEqual(dashboard_statistics(self.db, LegalCaseFilters(), self.access)["case_count"], 0)

    def test_dashboard_count_is_not_capped_by_preview_limit(self):
        case = LegalCase(
            stage=LegalCaseStage.FORMAL, status=LegalCaseStatus.IN_TRIAL,
            case_name="统计案件", subject_amount=Decimal("1"), created_by=self.user.id,
        )
        self.db.add(case); self.db.flush()
        due = date.today() + timedelta(days=10)
        self.db.add_all([
            LegalCaseAsset(
                case_id=case.id, asset_type="房产", asset_name=f"资产{i}",
                measure_type="查封", expiry_date=due,
            )
            for i in range(25)
        ])
        self.db.commit()

        result = dashboard_statistics(self.db, LegalCaseFilters(), self.access)

        self.assertEqual(result["upcoming_asset_count"], 25)
        self.assertEqual(len(result["upcoming_assets"]), 20)

    def test_export_escapes_formula_leading_case_text(self):
        self.db.add(LegalCase(
            stage=LegalCaseStage.FORMAL, status=LegalCaseStatus.IN_TRIAL,
            case_name="=HYPERLINK(\"https://example.invalid\")",
            subject_amount=Decimal("1"), created_by=self.user.id,
        ))
        self.db.commit()

        workbook = load_workbook(export_cases_workbook(
            self.db, LegalCaseFilters(), self.access, self.user
        ))

        self.assertTrue(workbook["案件明细"]["B2"].value.startswith("'="))


if __name__ == "__main__":
    unittest.main()
