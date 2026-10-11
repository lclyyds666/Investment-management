import unittest

from app.models.cash_execution import CashExecutionTask, InvoiceFundAllocation


class CashExecutionModelTest(unittest.TestCase):
    def test_payment_task_is_unique_per_approval(self):
        names = {constraint.name for constraint in CashExecutionTask.__table__.constraints}
        self.assertIn("uq_cash_task_approval", names)

    def test_invoice_allocation_is_audit_backed(self):
        self.assertTrue(
            {"fund_transaction_id", "invoice_id", "amount", "allocated_by"}.issubset(
                InvoiceFundAllocation.__table__.columns.keys()
            )
        )


if __name__ == "__main__":
    unittest.main()
