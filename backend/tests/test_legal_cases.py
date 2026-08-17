import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.db.base import Base
from app.models.legal_risk import (
    LegalCase,
    LegalCaseJudgment,
    LegalCaseParty,
    LegalCaseProgress,
    LegalCaseRecovery,
    LegalCaseStage,
    LegalCaseStatus,
    LegalJudgmentType,
    LegalPartyType,
    LegalProgressType,
    LegalRecoveryType,
)
from app.models.portal import UserCompanyRole
from app.models.user import User
from fastapi import HTTPException

from app.api.v1.endpoints.legal_risk import update_progress
from app.schemas.legal_risk import LegalCaseUpdate, LegalProgressIn
from app.services.legal_cases import (
    activate_case,
    calculate_case_money,
    change_case_status,
    ensure_formal_case_fields,
    reserve_case_version,
)


class LegalCaseServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.actor = User(
            username="admin", full_name="测试管理员", hashed_password="hashed",
            role=Role.INFO_MAINTAINER, is_superuser=True, is_active=True,
        )
        self.db.add(self.actor)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _complete_draft(self):
        case = LegalCase(
            stage=LegalCaseStage.DRAFT,
            case_name="测试案件",
            cause_of_action="合同纠纷",
            court="济南市中级人民法院",
            court_case_no="(2026)鲁01民初1号",
            subject_amount=Decimal("1000.00"),
            responsible_user_id=self.actor.id,
            created_by=self.actor.id,
        )
        case.parties.extend([
            LegalCaseParty(party_type=LegalPartyType.PLAINTIFF, name="原告公司"),
            LegalCaseParty(party_type=LegalPartyType.DEFENDANT, name="被告公司"),
        ])
        self.db.add(case)
        self.db.flush()
        return case

    def test_activate_generates_number_and_fixed_initial_status(self):
        case = self._complete_draft()
        activate_case(self.db, case, self.actor)
        self.db.commit()
        self.assertRegex(case.case_no, r"^AJ-\d{4}-0001$")
        self.assertEqual(case.stage, LegalCaseStage.FORMAL)
        self.assertEqual(case.status, LegalCaseStatus.REVIEW_FILING)

    def test_money_uses_current_basis_and_separates_avoided_loss(self):
        case = self._complete_draft()
        activate_case(self.db, case, self.actor)
        case.judgments.append(LegalCaseJudgment(
            judgment_type=LegalJudgmentType.SETTLEMENT,
            executable_amount=Decimal("800.00"),
            is_current_enforcement_basis=True,
        ))
        case.recoveries.extend([
            LegalCaseRecovery(
                recovery_type=LegalRecoveryType.RECOVERY,
                recovery_date=case.activated_at.date(), amount=Decimal("300.00"),
                registered_by=self.actor.id,
            ),
            LegalCaseRecovery(
                recovery_type=LegalRecoveryType.AVOIDED_LOSS,
                recovery_date=case.activated_at.date(), amount=Decimal("200.00"),
                registered_by=self.actor.id,
            ),
        ])
        self.db.commit()
        summary = calculate_case_money(self.db, case.id)
        self.assertEqual(summary.recovered_amount, Decimal("300.00"))
        self.assertEqual(summary.avoided_loss_amount, Decimal("200.00"))
        self.assertEqual(summary.outstanding_amount, Decimal("500.00"))

    def test_stale_case_version_is_rejected_by_database_update(self):
        case = self._complete_draft()
        self.db.commit()
        case_id = case.id

        first = Session(self.engine)
        second = Session(self.engine)
        try:
            first_case = first.get(LegalCase, case_id)
            second_case = second.get(LegalCase, case_id)
            reserve_case_version(first, first_case, 1)
            first.commit()

            with self.assertRaises(HTTPException) as raised:
                reserve_case_version(second, second_case, 1)
            self.assertEqual(raised.exception.status_code, 409)
        finally:
            first.close()
            second.close()

    def test_formal_case_required_fields_cannot_be_cleared(self):
        case = self._complete_draft()
        activate_case(self.db, case, self.actor)

        with self.assertRaises(HTTPException) as raised:
            ensure_formal_case_fields(case, {"court": ""})

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("受理法院", raised.exception.detail)

    def test_case_update_rejects_explicit_null_for_non_nullable_field(self):
        with self.assertRaises(ValueError):
            LegalCaseUpdate(version=1, court=None)

    def test_progress_record_can_be_updated(self):
        case = self._complete_draft()
        activate_case(self.db, case, self.actor)
        progress = LegalCaseProgress(
            case_id=case.id,
            progress_type=LegalProgressType.PROGRESS,
            content="原进展",
            registered_by=self.actor.id,
        )
        self.db.add(progress)
        self.db.commit()

        response = update_progress(
            case.id,
            progress.id,
            LegalProgressIn(
                progress_type=LegalProgressType.PROGRESS,
                content="更新后的进展",
                risk_points="新风险",
            ),
            self.db,
            self.actor,
        )

        self.assertEqual(response.data.content, "更新后的进展")
        self.assertEqual(response.data.risk_points, "新风险")


    def test_status_rollback_clears_closed_fields(self):
        case = self._complete_draft()
        activate_case(self.db, case, self.actor)
        case.status = LegalCaseStatus.CLOSED
        case.closed_date = date(2026, 8, 15)
        case.closure_summary = "已完成结案"
        self.db.commit()

        change_case_status(
            self.db,
            case,
            LegalCaseStatus.IN_TRIAL,
            case.version,
            self.actor,
        )

        self.assertIsNone(case.closed_date)
        self.assertEqual(case.closure_summary, "")


if __name__ == "__main__":
    unittest.main()
