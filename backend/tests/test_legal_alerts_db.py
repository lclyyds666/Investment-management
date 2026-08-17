import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.db.base import Base
from app.models.legal_risk import (
    LegalAlertDelivery,
    LegalAlertStatus,
    LegalCase,
    LegalCaseAlert,
    LegalCaseAsset,
    LegalCaseStage,
    LegalCaseStatus,
    LegalDeliveryStatus,
)
from app.models.user import User
from app.services.dingtalk import DeliveryResult
from app.services.legal_alerts import dispatch_pending_deliveries, scan_alerts


class LegalAlertDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(
            username="legal", full_name="法务人员", hashed_password="x",
            role=Role.RISK_AUDITOR, is_active=True, mobile="13800138000",
            legal_alert_enabled=True,
        )
        self.db.add(self.user)
        self.db.flush()
        self.case = LegalCase(
            stage=LegalCaseStage.FORMAL, case_no="FL-2026-0001",
            case_name="预警数据库测试", cause_of_action="合同纠纷",
            court="测试法院", court_case_no="(2026)测1号",
            subject_amount=Decimal("1000"), status=LegalCaseStatus.IN_TRIAL,
            responsible_user_id=self.user.id, created_by=self.user.id,
            activated_by=self.user.id, activated_at=datetime.now(),
        )
        self.db.add(self.case)
        self.db.flush()
        self.asset = LegalCaseAsset(
            case_id=self.case.id, asset_type="房产", asset_name="测试资产",
            measure_type="查封", expiry_date=date(2026, 8, 20), reminder_days=30,
        )
        self.db.add(self.asset)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_scan_is_idempotent_and_date_change_closes_old_alert(self):
        first = scan_alerts(self.db, date(2026, 8, 14))
        self.db.commit()
        self.assertEqual(first.alerts_created, 1)
        self.assertEqual(first.deliveries_created, 2)

        second = scan_alerts(self.db, date(2026, 8, 14))
        self.db.commit()
        self.assertEqual(second.alerts_created, 0)
        self.assertEqual(second.deliveries_created, 0)
        self.assertEqual(self.db.query(LegalCaseAlert).count(), 1)
        self.assertEqual(self.db.query(LegalAlertDelivery).count(), 2)

        self.asset.expiry_date = date(2026, 8, 25)
        self.db.commit()
        changed = scan_alerts(self.db, date(2026, 8, 14))
        self.db.commit()
        self.assertEqual(changed.alerts_created, 1)
        alerts = self.db.query(LegalCaseAlert).order_by(LegalCaseAlert.id).all()
        self.assertEqual(alerts[0].status, LegalAlertStatus.CLOSED)
        self.assertEqual(alerts[1].status, LegalAlertStatus.PENDING)

    def test_failed_dingtalk_delivery_uses_bounded_retry_schedule(self):
        scan_alerts(self.db, date(2026, 8, 14))
        self.db.commit()
        delivery = self.db.query(LegalAlertDelivery).filter(
            LegalAlertDelivery.channel == "dingtalk"
        ).one()
        client = SimpleNamespace(send_alert=lambda *_: DeliveryResult(
            success=False, status="failed", failure_reason="temporary"
        ))
        now = datetime(2026, 8, 14, 9, 0, 0)

        self.assertEqual(dispatch_pending_deliveries(self.db, client, now), 1)
        self.assertEqual(delivery.status, LegalDeliveryStatus.FAILED)
        self.assertEqual(delivery.next_retry_at, now + timedelta(minutes=5))
        self.assertEqual(dispatch_pending_deliveries(self.db, client, now + timedelta(minutes=4)), 0)
        self.assertEqual(dispatch_pending_deliveries(self.db, client, now + timedelta(minutes=5)), 1)
        self.assertEqual(delivery.attempts, 2)
        self.assertEqual(delivery.next_retry_at, now + timedelta(minutes=35))

    def test_claimed_delivery_is_not_sent_by_a_concurrent_worker(self):
        scan_alerts(self.db, date(2026, 8, 14))
        self.db.commit()
        now = datetime(2026, 8, 14, 9, 0, 0)
        duplicate_calls = []
        concurrent_processed = []

        class DuplicateClient:
            configured = True

            def send_alert(self, *_):
                duplicate_calls.append(True)
                return DeliveryResult(success=True, status="sent")

        engine = self.engine

        class FirstClient:
            configured = True

            def send_alert(self, *_):
                with Session(engine) as concurrent_db:
                    processed = dispatch_pending_deliveries(
                        concurrent_db, DuplicateClient(), now
                    )
                concurrent_processed.append(processed)
                return DeliveryResult(success=True, status="sent")

        self.assertEqual(dispatch_pending_deliveries(self.db, FirstClient(), now), 1)
        self.assertEqual(concurrent_processed, [0])
        self.assertEqual(duplicate_calls, [])


if __name__ == "__main__":
    unittest.main()
