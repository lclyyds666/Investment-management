import unittest

import app.db.init_db  # noqa: F401
from app.core.enums import InvoiceApprovalStatus, InvoiceDirection, InvoiceSourceKind
from app.models.invoice import Invoice, InvoiceAttachment, InvoiceDetail
from app.models.invoice_preference import ScenicInvoicePreference


class InvoiceModelTest(unittest.TestCase):
    def test_source_fields_and_unique_key(self):
        invoice = Invoice(
            invoice_title="Example",
            direction=InvoiceDirection.OUTPUT,
            source_kind=InvoiceSourceKind.TICKET,
            scenic_id="demo",
            period_key="2026-09",
            source_fingerprint="abc",
        )
        self.assertEqual(invoice.direction, InvoiceDirection.OUTPUT)
        self.assertTrue({"direction", "source_kind", "scenic_id", "period_key"}.issubset(Invoice.__table__.columns.keys()))
        names = {constraint.name for constraint in Invoice.__table__.constraints}
        self.assertIn("uq_invoice_source", names)

    def test_invoice_cascades_attachments_and_details(self):
        invoice = Invoice(invoice_title="Example")
        invoice.attachments.extend([
            InvoiceAttachment(original_name="a.pdf", stored_name="a"),
            InvoiceAttachment(original_name="b.pdf", stored_name="b"),
        ])
        invoice.details.append(InvoiceDetail(line_no=1, platform="票付通", amount=1))
        self.assertEqual(len(invoice.attachments), 2)
        self.assertEqual(invoice.details[0].invoice, invoice)
        self.assertIn("delete-orphan", str(Invoice.attachments.property.cascade))

    def test_preference_is_unique_per_scenic_and_direction(self):
        preference = ScenicInvoicePreference(
            scenic_id="demo", direction=InvoiceDirection.INPUT, last_contract_no="HT-1"
        )
        self.assertEqual(preference.contract_no, "HT-1")
        self.assertTrue({"scenic_id", "direction"}.issubset(ScenicInvoicePreference.__table__.columns.keys()))
        names = {constraint.name for constraint in ScenicInvoicePreference.__table__.constraints}
        self.assertIn("uq_scenic_invoice_preference", names)

    def test_approval_status_is_available(self):
        self.assertEqual(InvoiceApprovalStatus.APPROVED.value, "approved")


if __name__ == "__main__":
    unittest.main()
