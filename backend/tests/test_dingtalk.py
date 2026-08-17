import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.models.legal_risk import LegalAlertType
from app.services.dingtalk import DingTalkClient, build_alert_message, sign_webhook


class DingTalkAdapterTest(unittest.TestCase):
    def test_signature_is_stable(self):
        self.assertEqual(
            sign_webhook("SEC-test", 1700000000000),
            sign_webhook("SEC-test", 1700000000000),
        )

    def test_message_uses_minimum_disclosure(self):
        case = SimpleNamespace(
            case_no="AJ-2026-0001", case_name="高度敏感案件",
            subject_amount=Decimal("999999.00"),
        )
        alert = SimpleNamespace(
            alert_type=LegalAlertType.HEARING,
            due_date=date(2026, 8, 20),
        )
        message = build_alert_message(alert, case, today=date(2026, 8, 14))
        self.assertIn("AJ-2026-0001", message)
        self.assertNotIn("高度敏感案件", message)
        self.assertNotIn("999999", message)

    def test_unconfigured_channel_degrades_without_network(self):
        result = DingTalkClient(enabled=False, webhook="", secret="").send_test("测试员")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "channel_unconfigured")


if __name__ == "__main__":
    unittest.main()
