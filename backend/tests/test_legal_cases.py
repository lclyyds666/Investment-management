import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.enums import AssignmentStatus, CompanyCode, OrganizationType, PositionCategory, Role
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
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from fastapi import HTTPException

from app.api.v1.endpoints.contract import create_contract
from app.api.v1.endpoints.legal_risk import create_case, list_cases, update_case, update_progress
from app.schemas.contract import ContractCreate
from app.schemas.legal_risk import LegalCaseCreate, LegalCaseUpdate, LegalProgressIn
from app.services.legal_cases import (
    activate_case,
    calculate_case_money,
    change_case_status,
    ensure_formal_case_fields,
    reserve_case_version,
    resolve_investment_user_name,
    get_case_or_403,
)
from app.services.legal_permissions import LegalAccessContext
from app.services.legal_record_scope import LegalRecordScope


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

    def test_money_without_current_basis_does_not_fall_back_to_subject_amount(self):
        case = self._complete_draft()
        activate_case(self.db, case, self.actor)
        self.db.commit()

        summary = calculate_case_money(self.db, case.id)

        self.assertIsNone(summary.executable_amount)
        self.assertEqual(summary.outstanding_amount, Decimal("0"))

    def test_resolve_investment_user_name_requires_active_exact_match(self):
        target = User(
            username="owner", full_name="案件负责人", hashed_password="x",
            role=Role.BUSINESS_HANDLER, is_active=True,
        )
        self.db.add(target)
        self.db.flush()
        self.db.add(UserCompanyRole(
            user_id=target.id,
            company_code=CompanyCode.INVESTMENT.value,
            role=Role.BUSINESS_HANDLER,
        ))
        self.db.commit()

        self.assertEqual(resolve_investment_user_name(self.db, "案件负责人").id, target.id)
        with self.assertRaises(HTTPException) as raised:
            resolve_investment_user_name(self.db, "不存在")
        self.assertEqual(raised.exception.status_code, 422)

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

    def test_xinhua_property_can_create_case_but_not_contract_and_cannot_view_other_company_case(self):
        company = Organization(
            code="xinhuaproperty", name="山东新华置业有限公司",
            organization_type=OrganizationType.COMPANY, company_code="xinhuaproperty",
        )
        position = Position(
            code="xinhuaproperty.business_handler", name="置业经办人",
            category=PositionCategory.BUSINESS,
        )
        user = User(username="property-user", full_name="置业经办人", hashed_password="x", role=Role.BUSINESS_HANDLER)
        self.db.add_all([company, position, user]); self.db.flush()
        assignment = UserAssignment(
            user_id=user.id, organization_id=company.id, position_id=position.id,
            valid_from=date(2026, 1, 1), status=AssignmentStatus.ACTIVE,
        )
        self.db.add(assignment); self.db.flush()

        created = create_case(
            LegalCaseCreate(case_name="置业案件", initiator_assignment_id=assignment.id), self.db, user
        ).data
        self.assertEqual(created.company_code, "xinhuaproperty")
        self.assertEqual(created.organization_code, "xinhuaproperty")
        self.assertEqual(created.initiator_assignment_id, assignment.id)

        updated = update_case(
            created.id,
            LegalCaseUpdate(version=created.version, case_name="置业案件更新"),
            self.db,
            self.actor,
        ).data
        self.assertEqual(updated.company_code, "xinhuaproperty")
        self.assertEqual(updated.organization_code, "xinhuaproperty")
        self.assertEqual(updated.initiator_assignment_id, assignment.id)

        with self.assertRaises(HTTPException) as contract_error:
            create_contract(
                ContractCreate(
                    contract_no="XH-2026-001",
                    title="置业合同",
                    initiator_assignment_id=assignment.id,
                ),
                self.db,
                user,
            )
        self.assertEqual(contract_error.exception.status_code, 422)
        self.assertEqual(
            contract_error.exception.detail["code"],
            "invalid_initiator_assignment",
        )

        other_company_case = LegalCase(
            case_name="供管案件", created_by=self.actor.id,
            company_code="supplymanagement", organization_code="supplymanagement",
        )
        self.db.add(other_company_case); self.db.commit()
        property_context = LegalAccessContext(
            user_id=user.id, role=None, is_superuser=False, capabilities=frozenset(),
            record_scope=LegalRecordScope(
                user_id=user.id, global_access=False,
                company_codes=frozenset({"xinhuaproperty"}), organization_codes=frozenset(),
            ),
        )
        with self.assertRaises(HTTPException) as raised:
            get_case_or_403(self.db, other_company_case.id, property_context)
        self.assertEqual(raised.exception.status_code, 404)

    def test_case_list_returns_and_filters_ownership_names(self):
        self.db.add_all([
            Organization(
                code="xinhuaproperty", name="山东新华置业有限公司",
                organization_type=OrganizationType.COMPANY, company_code="xinhuaproperty",
            ),
            Organization(
                code="supplymanagement", name="山东供销供应链管理集团有限公司",
                organization_type=OrganizationType.COMPANY, company_code="supplymanagement",
            ),
            LegalCase(
                case_name="置业案件", created_by=self.actor.id,
                company_code="xinhuaproperty", organization_code="xinhuaproperty",
            ),
            LegalCase(
                case_name="供管案件", created_by=self.actor.id,
                company_code="supplymanagement", organization_code="supplymanagement",
            ),
        ])
        self.db.commit()

        page = list_cases(
            company_name="新华", page=1, page_size=20,
            db=self.db, current_user=self.actor,
        ).data

        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].case_name, "置业案件")
        self.assertEqual(page.items[0].company_name, "山东新华置业有限公司")
        self.assertEqual(page.items[0].organization_name, "山东新华置业有限公司")


if __name__ == "__main__":
    unittest.main()
