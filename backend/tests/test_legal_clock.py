import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.core.config import settings
from app.services.legal_clock import legal_now_aware


class LegalClockTest(unittest.TestCase):
    def test_configured_timezone_controls_legal_business_date(self):
        utc_time = datetime(2026, 8, 13, 16, 30, tzinfo=timezone.utc)

        with patch.object(settings, "LEGAL_ALERT_TIMEZONE", "Asia/Shanghai"):
            local_time = legal_now_aware(utc_time)

        self.assertEqual(local_time.isoformat(), "2026-08-14T00:30:00+08:00")


if __name__ == "__main__":
    unittest.main()
