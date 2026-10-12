import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.core.enums import ContractStatus, ContractType, InvoiceApprovalStatus, InvoiceDirection
from app.db.base import Base
from app.models.approval_form import ApprovalForm
from app.models.cash_execution import CashExecutionTask
from app.models.fund import FundTransaction
from app.models.invoice import Invoice, InvoiceAttachment
from app.services.cash_execution import (
    CashExecutionError,
    ensure_payment_task,
    ensure_receipt_task,
    execute_task,
)


class CashExecutionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_final_payment_approval_creates_task_not_fund_transaction(self):
        with Session(self.engine) as db:
            form = ApprovalForm(
                form_type=ContractType.PAYMENT,
                status=ContractStatus.APPROVED,
                amount=Decimal("125.50"),
                scenic_id="demo",
                created_by=1,
            )
            db.add(form)
            db.flush()
            task = ensure_payment_task(db, form)
            again = ensure_payment_task(db, form)
            self.assertEqual(task.id, again.id)
            self.assertEqual(db.query(CashExecutionTask).count(), 1)
            self.assertEqual(db.query(FundTransaction).count(), 0)

    def test_output_receipt_task_waits_for_approval_and_attachment(self):
        with Session(self.engine) as db:
            invoice = Invoice(
                invoice_title="demo",
                direction=InvoiceDirection.OUTPUT,
                approval_status=InvoiceApprovalStatus.DRAFT,
                amount=Decimal("10.00"),
            )
            db.add(invoice)
            db.flush()
            self.assertIsNone(ensure_receipt_task(db, invoice))
            invoice.approval_status = InvoiceApprovalStatus.APPROVED
            invoice.attachments.append(
                InvoiceAttachment(original_name="a.pdf", stored_name="a.pdf")
            )
            db.flush()
            self.assertIsNotNone(ensure_receipt_task(db, invoice))

    def test_execute_task_supports_partial_then_complete(self):
        with Session(self.engine) as db:
            form = ApprovalForm(
                form_type=ContractType.PAYMENT,
                status=ContractStatus.APPROVED,
                amount=Decimal("100.00"),
                scenic_id="demo",
                created_by=1,
            )
            db.add(form)
            db.flush()
            task = ensure_payment_task(db, form)
            payload = lambda amount: SimpleNamespace(
                amount=Decimal(amount),
                occurred_on=date(2026, 10, 11),
                counterparty="Supplier",
                bank_reference="BANK-1",
                summary="Payment",
                remark="",
            )
            first = execute_task(db, task.id, payload("40.00"), actor_id=1)
            self.assertEqual(task.status, "partial")
            second = execute_task(db, task.id, payload("60.00"), actor_id=1)
            self.assertEqual(task.status, "completed")
            self.assertEqual(first.direction, "usage")
            self.assertEqual(second.execution_task_id, task.id)

    def test_execute_task_rejects_amount_above_remaining(self):
        with Session(self.engine) as db:
            form = ApprovalForm(
                form_type=ContractType.PAYMENT,
                status=ContractStatus.APPROVED,
                amount=Decimal("100.00"),
                scenic_id="demo",
                created_by=1,
            )
            db.add(form)
            db.flush()
            task = ensure_payment_task(db, form)
            payload = SimpleNamespace(
                amount=Decimal("100.01"),
                occurred_on=date(2026, 10, 11),
                counterparty="Supplier",
                bank_reference="BANK-2",
                summary="Payment",
                remark="",
            )
            with self.assertRaises(CashExecutionError):
                execute_task(db, task.id, payload, actor_id=1)


if __name__ == "__main__":
    unittest.main()
