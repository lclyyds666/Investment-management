import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.core.enums import ContractStatus, ContractType, InvoiceApprovalStatus, InvoiceDirection
from app.db.base import Base
from app.models.approval_form import ApprovalForm
from app.models.cash_execution import CashExecutionTask
from app.models.invoice import Invoice, InvoiceAttachment
from app.services.cash_execution import ensure_payment_task, ensure_receipt_task


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


if __name__ == "__main__":
    unittest.main()
