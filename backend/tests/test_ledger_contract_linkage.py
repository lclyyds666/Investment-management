import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.enums import ContractStatus, InvoiceSourceKind
from app.db.base import Base
from app.models.contract import Contract
from app.models.ledger_contract import LedgerContractLink, ScenicContractPreference
from app.models.organization import UserAssignment  # noqa: F401
from app.models.user import User  # noqa: F401
from app.services.contract_linkage import ContractLinkError, link_period_contract


class LedgerContractLinkageTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.ticket_contract = self._contract(
            "TICKET-001", "scenic-a", [InvoiceSourceKind.TICKET.value]
        )
        self.other_ticket_contract = self._contract(
            "TICKET-002", "scenic-a", [InvoiceSourceKind.TICKET.value]
        )
        self.hotel_contract = self._contract(
            "HOTEL-001", "scenic-a", [InvoiceSourceKind.HOTEL.value]
        )
        self.other_scenic_contract = self._contract(
            "TICKET-OTHER", "scenic-b", [InvoiceSourceKind.TICKET.value]
        )
        self.draft_contract = self._contract(
            "TICKET-DRAFT",
            "scenic-a",
            [InvoiceSourceKind.TICKET.value],
            status=ContractStatus.DRAFT,
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _contract(self, contract_no, scenic_id, business_scopes, *, status=ContractStatus.APPROVED):
        contract = Contract(
            contract_no=contract_no,
            title=contract_no,
            scenic_id=scenic_id,
            business_scopes=business_scopes,
            status=status,
            created_by=1,
        )
        self.db.add(contract)
        self.db.flush()
        return contract

    def test_confirm_rejects_contract_from_another_scenic(self):
        with self.assertRaises(ContractLinkError) as caught:
            link_period_contract(
                self.db,
                "scenic-a",
                InvoiceSourceKind.TICKET,
                "P1",
                self.other_scenic_contract.id,
                1,
            )

        self.assertEqual(caught.exception.code, "contract_scenic_mismatch")

    def test_confirm_rejects_unapproved_contract(self):
        with self.assertRaises(ContractLinkError) as caught:
            link_period_contract(
                self.db,
                "scenic-a",
                InvoiceSourceKind.TICKET,
                "P1",
                self.draft_contract.id,
                1,
            )

        self.assertEqual(caught.exception.code, "contract_not_approved")

    def test_confirm_rejects_contract_outside_business_scope(self):
        with self.assertRaises(ContractLinkError) as caught:
            link_period_contract(
                self.db,
                "scenic-a",
                InvoiceSourceKind.TICKET,
                "P1",
                self.hotel_contract.id,
                1,
            )

        self.assertEqual(caught.exception.code, "contract_scope_mismatch")

    def test_confirm_rejects_approved_contract_outside_current_user_scope(self):
        user = User(
            id=99,
            username="ledger-scope-user",
            full_name="台账用户",
            hashed_password="test",
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()

        with self.assertRaises(ContractLinkError) as caught:
            link_period_contract(
                self.db,
                "scenic-a",
                InvoiceSourceKind.TICKET,
                "P-hidden",
                self.ticket_contract.id,
                user,
            )

        self.assertEqual(caught.exception.code, "contract_not_approved")

    def test_confirmed_period_keeps_original_contract(self):
        link = link_period_contract(
            self.db,
            "scenic-a",
            InvoiceSourceKind.TICKET,
            "P1",
            self.ticket_contract.id,
            1,
        )

        with self.assertRaises(ContractLinkError) as caught:
            link_period_contract(
                self.db,
                "scenic-a",
                InvoiceSourceKind.TICKET,
                "P1",
                self.other_ticket_contract.id,
                1,
            )

        self.assertEqual(caught.exception.code, "confirmed_period_contract_locked")
        self.assertEqual(link.contract_id, self.ticket_contract.id)

    def test_link_snapshots_contract_and_remembers_source_specific_preference(self):
        ticket_link = link_period_contract(
            self.db,
            "scenic-a",
            InvoiceSourceKind.TICKET,
            "P1",
            self.ticket_contract.id,
            7,
        )
        hotel_link = link_period_contract(
            self.db,
            "scenic-a",
            InvoiceSourceKind.HOTEL,
            "P1",
            self.hotel_contract.id,
            7,
        )
        self.db.flush()

        self.assertEqual(ticket_link.contract_no_snapshot, "TICKET-001")
        self.assertEqual(ticket_link.selected_by, 7)
        self.assertEqual(hotel_link.contract_no_snapshot, "HOTEL-001")
        preferences = self.db.scalars(
            select(ScenicContractPreference).order_by(ScenicContractPreference.source_kind)
        ).all()
        self.assertEqual(len(preferences), 2)
        self.assertEqual(
            {
                preference.source_kind: preference.last_contract_id
                for preference in preferences
            },
            {
                InvoiceSourceKind.TICKET: self.ticket_contract.id,
                InvoiceSourceKind.HOTEL: self.hotel_contract.id,
            },
        )


if __name__ == "__main__":
    unittest.main()
