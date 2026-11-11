import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.api.deps import get_current_user
from app.core.enums import InvoiceDirection
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.fund import FundTransaction
from app.models.invoice import Invoice
from app.services.invoice_reconciliation import (
    ReconciliationError,
    allocate,
    delete_allocation,
    invoice_reconciliation_state,
    list_allocations,
)


class InvoiceFundReconciliationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.db = Session(self.engine)
        self.db.query(FundTransaction).delete()
        self.db.query(Invoice).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def invoice(self, direction=InvoiceDirection.INPUT, amount="100.00", contract_id=1):
        row = Invoice(
            invoice_title="invoice",
            direction=direction,
            amount=Decimal(amount),
            contract_id=contract_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def fund(self, direction="usage", amount="100.00", contract_id=1):
        row = FundTransaction(
            direction=direction,
            category="business_payment" if direction == "usage" else "customer_payment",
            amount=Decimal(amount),
            occurred_on=date(2026, 10, 11),
            contract_id=contract_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def test_input_invoice_only_accepts_usage_funds(self):
        invoice = self.invoice()
        fund = self.fund(direction="increase")
        with self.assertRaises(ReconciliationError) as caught:
            allocate(self.db, invoice.id, fund.id, Decimal("10"), actor_id=1)
        self.assertEqual(caught.exception.code, "direction_mismatch")

    def test_output_invoice_only_accepts_increase_funds(self):
        invoice = self.invoice(direction=InvoiceDirection.OUTPUT)
        fund = self.fund(direction="usage")
        with self.assertRaises(ReconciliationError) as caught:
            allocate(self.db, invoice.id, fund.id, Decimal("10"), actor_id=1)
        self.assertEqual(caught.exception.code, "direction_mismatch")

    def test_allocation_cannot_exceed_invoice_or_fund_remaining(self):
        invoice = self.invoice()
        fund = self.fund()
        allocate(self.db, invoice.id, fund.id, Decimal("60"), actor_id=1)
        other_invoice = self.invoice(amount="50.00")
        with self.assertRaises(ReconciliationError) as caught:
            allocate(self.db, other_invoice.id, fund.id, Decimal("40.01"), actor_id=1)
        self.assertEqual(caught.exception.code, "allocation_exceeds_remaining")
        with self.assertRaises(ReconciliationError):
            allocate(self.db, invoice.id, self.fund().id, Decimal("40.01"), actor_id=1)

    def test_contracts_must_match_when_both_sources_have_one(self):
        with self.assertRaises(ReconciliationError) as caught:
            allocate(self.db, self.invoice(contract_id=1).id, self.fund(contract_id=2).id, Decimal("10"), actor_id=1)
        self.assertEqual(caught.exception.code, "contract_mismatch")

    def test_state_and_list_follow_multiple_allocations_and_delete(self):
        invoice = self.invoice()
        first = allocate(self.db, invoice.id, self.fund(amount="30").id, Decimal("30"), actor_id=1)
        self.assertEqual(invoice_reconciliation_state(self.db, invoice), "partial")
        second = allocate(self.db, invoice.id, self.fund(amount="70").id, Decimal("70"), actor_id=1)
        self.assertEqual(invoice_reconciliation_state(self.db, invoice), "allocated")
        self.assertEqual([row.id for row in list_allocations(self.db, invoice.id)], [first.id, second.id])
        delete_allocation(self.db, invoice.id, second.id)
        self.assertEqual(invoice_reconciliation_state(self.db, invoice), "partial")

    def test_rejects_missing_sources_and_nonpositive_amount(self):
        invoice = self.invoice()
        fund = self.fund()
        with self.assertRaises(ReconciliationError) as caught:
            allocate(self.db, 999, fund.id, Decimal("10"), actor_id=1)
        self.assertEqual(caught.exception.code, "source_not_found")
        with self.assertRaises(ReconciliationError) as caught:
            allocate(self.db, invoice.id, fund.id, Decimal("0"), actor_id=1)
        self.assertEqual(caught.exception.code, "allocation_exceeds_remaining")


class InvoiceFundReconciliationApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.invoice = Invoice(
            invoice_title="invoice",
            direction=InvoiceDirection.INPUT,
            amount=Decimal("100.00"),
            contract_id=1,
        )
        self.fund = FundTransaction(
            direction="usage",
            category="business_payment",
            amount=Decimal("100.00"),
            occurred_on=date(2026, 10, 11),
            contract_id=1,
        )
        self.db.add_all([self.invoice, self.fund])
        self.db.commit()
        app = create_app()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7, is_superuser=True, is_active=True
        )
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_create_list_delete_allocation_and_invoice_summary(self):
        created = self.client.post(
            f"/api/v1/invoices/{self.invoice.id}/allocations",
            json={"fund_transaction_id": self.fund.id, "amount": "40.00"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        allocation = created.json()["data"]
        self.assertEqual(allocation["fund_direction"], "usage")
        listed = self.client.get(
            f"/api/v1/invoices/{self.invoice.id}/allocations"
        )
        self.assertEqual(len(listed.json()["data"]), 1)
        invoices = self.client.get("/api/v1/invoices", params={"include_legacy": True})
        summary = next(row for row in invoices.json()["data"] if row["id"] == self.invoice.id)
        self.assertEqual(summary["reconciliation_state"], "partial")
        self.assertEqual(Decimal(summary["unallocated_amount"]), Decimal("60.00"))
        deleted = self.client.delete(
            f"/api/v1/invoices/{self.invoice.id}/allocations/{allocation['id']}"
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)

    def test_direction_error_is_structured_conflict(self):
        self.fund.direction = "increase"
        self.db.commit()
        response = self.client.post(
            f"/api/v1/invoices/{self.invoice.id}/allocations",
            json={"fund_transaction_id": self.fund.id, "amount": "10.00"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "direction_mismatch")

    def test_fund_balances_refresh_after_allocation_and_removal(self):
        def balance():
            response = self.client.get("/api/v1/funds", params={"fund_id": self.fund.id})
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["data"]["items"][0]

        initial = balance()
        self.assertEqual(Decimal(initial["allocated_amount"]), Decimal("0"))
        self.assertEqual(Decimal(initial["unallocated_amount"]), Decimal("100"))
        created = self.client.post(f"/api/v1/invoices/{self.invoice.id}/allocations",
                                   json={"fund_transaction_id": self.fund.id, "amount": "40"})
        self.assertEqual(created.status_code, 200, created.text)
        partial = balance()
        self.assertEqual(Decimal(partial["amount"]), Decimal("100"))
        self.assertEqual(Decimal(partial["allocated_amount"]), Decimal("40"))
        self.assertEqual(Decimal(partial["unallocated_amount"]), Decimal("60"))
        self.client.delete(f"/api/v1/invoices/{self.invoice.id}/allocations/{created.json()['data']['id']}")
        self.assertEqual(Decimal(balance()["unallocated_amount"]), Decimal("100"))

    def test_fund_candidates_filter_contract_direction_and_remaining(self):
        allocate(self.db, self.invoice.id, self.fund.id, Decimal("100.00"), actor_id=7)
        available = FundTransaction(
            direction="usage",
            category="business_payment",
            amount=Decimal("20.00"),
            occurred_on=date(2026, 10, 12),
            contract_id=1,
        )
        wrong_contract = FundTransaction(
            direction="usage",
            category="business_payment",
            amount=Decimal("20.00"),
            occurred_on=date(2026, 10, 12),
            contract_id=2,
        )
        self.db.add_all([available, wrong_contract])
        self.db.commit()
        response = self.client.get("/api/v1/funds", params={
            "direction": "usage",
            "contract_id": 1,
            "unallocated_only": True,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [row["id"] for row in response.json()["data"]["items"]],
            [available.id],
        )


if __name__ == "__main__":
    unittest.main()
