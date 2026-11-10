import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.fund import _view_guard
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.fund import FundTransaction
from app.models.fund_alert import FundAlertReceipt
from app.models.user import User
from app.schemas.fund import FundAlertReceiptItem
from app.services.fund import acknowledge_alert_receipts, build_fund_alert_item, list_today_alerts


class FundAlertServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(username="alert-user", full_name="Alert User", hashed_password="test", is_active=True)
        self.other_user = User(username="other-alert-user", full_name="Other Alert User", hashed_password="test", is_active=True)
        self.db.add_all([self.user, self.other_user])
        self.db.flush()
        self.today = date(2026, 10, 10)
        self.row = self._fund(self.today + timedelta(days=30))
        self.db.add(self.row)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _fund(self, maturity_date, **overrides):
        values = {"id": 100, "direction": "increase", "category": "bank_credit", "amount": Decimal("100000"), "occurred_on": date(2026, 1, 1), "counterparty": "Test Bank", "summary": "Working capital credit", "maturity_date": maturity_date, "settlement_status": "open", "remark": ""}
        values.update(overrides)
        return FundTransaction(**values)

    def test_alert_builder_includes_boundaries_and_excludes_irrelevant_rows(self):
        self.assertEqual(build_fund_alert_item(self._fund(self.today + timedelta(days=30)), self.today).stage, "due_soon")
        self.assertIsNone(build_fund_alert_item(self._fund(self.today + timedelta(days=31)), self.today))
        self.assertEqual(build_fund_alert_item(self._fund(self.today - timedelta(days=1)), self.today).stage, "overdue")
        self.assertIsNone(build_fund_alert_item(self._fund(self.today, settlement_status="settled"), self.today))
        self.assertIsNone(build_fund_alert_item(self._fund(self.today, category="customer_payment"), self.today))

    def test_receipt_is_daily_user_scoped_idempotent_and_stage_scoped(self):
        first = list_today_alerts(self.db, self.user.id, self.today)
        self.assertEqual([item.id for item in first.items], [self.row.id])
        items = [FundAlertReceiptItem(fund_id=self.row.id, stage="due_soon"), FundAlertReceiptItem(fund_id=self.row.id, stage="due_soon")]
        self.assertEqual(acknowledge_alert_receipts(self.db, self.user.id, items, self.today), 1)
        self.db.commit()
        self.assertEqual(list_today_alerts(self.db, self.user.id, self.today).items, [])
        self.assertEqual(len(list_today_alerts(self.db, self.other_user.id, self.today).items), 1)
        self.assertEqual(len(list_today_alerts(self.db, self.user.id, self.today + timedelta(days=1)).items), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FundAlertReceipt)), 1)
        self.row.maturity_date = self.today - timedelta(days=1)
        self.db.commit()
        self.assertEqual(list_today_alerts(self.db, self.user.id, self.today).items[0].stage, "overdue")

    def test_fixed_date_five_record_acceptance_dataset(self):
        self.db.add_all([
            self._fund(self.today + timedelta(days=31), id=101),
            self._fund(self.today, id=102),
            self._fund(self.today - timedelta(days=1), id=103),
            self._fund(self.today, id=104, settlement_status="settled"),
        ])
        self.db.commit()
        alerts = list_today_alerts(self.db, self.user.id, self.today)
        self.assertEqual({item.id: item.stage for item in alerts.items}, {
            100: "due_soon", 102: "due_soon", 103: "overdue",
        })

    def test_acknowledge_revalidates_missing_settled_and_mismatched_items(self):
        items = [FundAlertReceiptItem(fund_id=self.row.id, stage="overdue"), FundAlertReceiptItem(fund_id=999999, stage="due_soon")]
        self.assertEqual(acknowledge_alert_receipts(self.db, self.user.id, items, self.today), 0)
        self.row.settlement_status = "settled"
        self.db.commit()
        self.assertEqual(acknowledge_alert_receipts(self.db, self.user.id, [FundAlertReceiptItem(fund_id=self.row.id, stage="due_soon")], self.today), 0)
        self.assertEqual(list_today_alerts(self.db, self.user.id, self.today).items, [])

    def test_savepoint_unique_collision_is_treated_as_existing_receipt(self):
        user_id = self.user.id
        item = FundAlertReceiptItem(fund_id=self.row.id, stage="due_soon")
        collision = IntegrityError("insert", {}, Exception("unique collision"))
        with patch.object(self.db, "get", return_value=self.row), patch.object(
            self.db, "flush", side_effect=collision
        ), patch.object(
            self.db, "scalar", side_effect=[None, 77]
        ):
            self.assertEqual(
                acknowledge_alert_receipts(
                    self.db, user_id, [item], self.today
                ),
                0,
            )

    def test_non_duplicate_integrity_error_is_re_raised(self):
        user_id = self.user.id
        item = FundAlertReceiptItem(fund_id=self.row.id, stage="due_soon")
        failure = IntegrityError("insert", {}, Exception("foreign key failure"))
        with patch.object(self.db, "get", return_value=self.row), patch.object(
            self.db, "flush", side_effect=failure
        ), patch.object(
            self.db, "scalar", side_effect=[None, None]
        ):
            with self.assertRaises(IntegrityError):
                acknowledge_alert_receipts(
                    self.db, user_id, [item], self.today
                )


class FundAlertHttpTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = Mock()
        self.user = SimpleNamespace(id=7, is_superuser=True, is_active=True)
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_alert_routes_are_registered_and_require_view_permission(self):
        paths = {route.path for route in self.app.routes}
        self.assertIn("/api/v1/funds/alerts/today", paths)
        self.assertIn("/api/v1/funds/alerts/today/acknowledge", paths)
        def deny_view():
            raise HTTPException(status_code=403, detail="permission denied")
        self.app.dependency_overrides[_view_guard] = deny_view
        self.assertEqual(self.client.get("/api/v1/funds/alerts/today").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/funds/alerts/today/acknowledge", json={"items": []}).status_code, 403)

    def test_today_and_acknowledge_endpoints_use_current_user(self):
        with patch("app.api.v1.endpoints.fund.list_today_alerts") as list_alerts:
            list_alerts.return_value = {"alert_date": date.today(), "items": []}
            response = self.client.get("/api/v1/funds/alerts/today")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(list_alerts.call_args.args[1], self.user.id)
        with patch("app.api.v1.endpoints.fund.acknowledge_alert_receipts", return_value=1) as acknowledge:
            response = self.client.post("/api/v1/funds/alerts/today/acknowledge", json={"items": [{"fund_id": 1, "stage": "due_soon"}]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"], {"acknowledged": 1})
        self.assertEqual(acknowledge.call_args.kwargs["user_id"], self.user.id)
        self.db.commit.assert_called_once()

    def test_acknowledge_schema_rejects_invalid_stage_and_oversized_batches(self):
        invalid = self.client.post("/api/v1/funds/alerts/today/acknowledge", json={"items": [{"fund_id": 1, "stage": "normal"}]})
        oversized = self.client.post("/api/v1/funds/alerts/today/acknowledge", json={"items": [{"fund_id": index + 1, "stage": "due_soon"} for index in range(201)]})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(oversized.status_code, 422)


if __name__ == "__main__":
    unittest.main()
