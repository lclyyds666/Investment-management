import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.api.v1.endpoints.contract import eligible_contracts
from app.core.enums import ContractStatus, InvoiceSourceKind
from app.db.base import Base
from app.models.contract import Contract
from app.models.user import User
from app.schemas.contract import ContractCreate, ContractUpdate


class ContractBusinessScopeTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        creator = User(
            username="contract-scope-creator",
            full_name="合同经办",
            hashed_password="test",
            is_active=True,
        )
        self.db.add(creator)
        self.db.flush()

        self.approved_ticket_contract = self._add_contract(
            creator.id,
            "HT-TICKET",
            ContractStatus.APPROVED,
            "changsha-dongqu",
            ["ticket"],
        )
        self._add_contract(
            creator.id,
            "HT-HOTEL",
            ContractStatus.APPROVED,
            "changsha-dongqu",
            ["hotel"],
        )
        self._add_contract(
            creator.id,
            "HT-OTHER-SCENIC",
            ContractStatus.APPROVED,
            "guanquelou",
            ["ticket", "hotel"],
        )
        self._add_contract(
            creator.id,
            "HT-PENDING",
            ContractStatus.PENDING,
            "changsha-dongqu",
            ["ticket"],
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _add_contract(
        self,
        creator_id: int,
        contract_no: str,
        status: ContractStatus,
        scenic_id: str,
        business_scopes: list[str],
    ) -> Contract:
        contract = Contract(
            contract_no=contract_no,
            title=contract_no,
            status=status,
            scenic_id=scenic_id,
            business_scopes=business_scopes,
            created_by=creator_id,
            company_code="investment",
            organization_code="investment.general",
        )
        self.db.add(contract)
        self.db.flush()
        return contract

    def test_new_contract_requires_one_scenic_and_business_scope(self):
        with self.assertRaises(ValidationError):
            ContractCreate(
                contract_no="HT-1",
                title="测试",
                scenic_id="",
                business_scopes=[],
            )

        with self.assertRaises(ValidationError):
            ContractCreate(
                contract_no="HT-2",
                title="测试",
                scenic_id="guanquelou",
                business_scopes=["retail"],
            )

    def test_business_scopes_are_deduplicated(self):
        contract = ContractCreate(
            contract_no="HT-3",
            title="测试",
            scenic_id="guanquelou",
            business_scopes=["ticket", "hotel", "ticket"],
        )

        self.assertEqual(contract.business_scopes, ["ticket", "hotel"])

    def test_update_cannot_clear_required_linkage_fields(self):
        with self.assertRaises(ValidationError):
            ContractUpdate(scenic_id=None)

        with self.assertRaises(ValidationError):
            ContractUpdate(business_scopes=None)

    def test_eligible_contract_requires_approved_matching_scope(self):
        result = eligible_contracts(
            self.db,
            "changsha-dongqu",
            InvoiceSourceKind.TICKET,
        )

        self.assertEqual(
            [row.id for row in result],
            [self.approved_ticket_contract.id],
        )

    def test_eligible_contract_applies_visibility_predicate(self):
        result = eligible_contracts(
            self.db,
            "changsha-dongqu",
            InvoiceSourceKind.TICKET,
            Contract.id != self.approved_ticket_contract.id,
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
