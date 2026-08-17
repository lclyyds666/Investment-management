import unittest
from datetime import date, timedelta

from app.models.legal_risk import (
    LegalAlertStatus,
    LegalAlertType,
    LegalCaseAlert,
)
from app.services.legal_alerts import delivery_stages


class LegalAlertStageTest(unittest.TestCase):
    def _alert(self, due: date, alert_type=LegalAlertType.HEARING):
        return LegalCaseAlert(
            case_id=1, source_type="deadline", source_id=1,
            alert_type=alert_type, cycle_key=due.isoformat(),
            trigger_date=due - timedelta(days=45), due_date=due,
            status=LegalAlertStatus.PENDING,
        )

    def test_window_due_and_overdue_seven_day_stages(self):
        due = date(2026, 8, 14)
        alert = self._alert(due)
        self.assertEqual(delivery_stages(alert, due - timedelta(days=10)), ["window-entry"])
        self.assertEqual(delivery_stages(alert, due), ["due-date"])
        self.assertEqual(delivery_stages(alert, due + timedelta(days=1)), ["overdue-1"])
        self.assertEqual(delivery_stages(alert, due + timedelta(days=8)), ["overdue-2"])
        self.assertEqual(delivery_stages(alert, due + timedelta(days=7)), ["overdue-1"])

    def test_terminal_alert_has_monthly_stage(self):
        current = date(2026, 8, 14)
        alert = self._alert(current, LegalAlertType.TERMINAL_MONITORING)
        alert.cycle_key = "2026-08"
        self.assertEqual(delivery_stages(alert, current), ["terminal-2026-08"])

    def test_completed_alert_stops_delivery(self):
        due = date(2026, 8, 14)
        alert = self._alert(due)
        alert.status = LegalAlertStatus.COMPLETED
        self.assertEqual(delivery_stages(alert, due), [])


if __name__ == "__main__":
    unittest.main()
