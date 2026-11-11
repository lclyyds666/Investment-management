import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook

from tests.test_operation_analysis_api import _client_with_database, _ledger
from app.models.ticket_ledger import TicketLedger


class OperationForecastApiTests(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.db, self.user = _client_with_database()
        self.db.rows[TicketLedger] = [
            _ledger(id=day, period_start=date(2026, 9, day), period_end=date(2026, 9, day))
            for day in (1, 2, 3)
        ] + [_ledger(id=99, confirmed=False, jinying_amount=999999)]
        self.payload = {"start_date": "2026-09-04", "end_date": "2026-09-04", "factors": []}

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_three_metrics_confirmed_only_and_no_writes(self):
        # This fake deliberately provides no mutation methods: any persistence fails.
        with patch("app.api.deps.has_permission", return_value=True) as permission, patch("app.services.operation_insights.settings.DEEPSEEK_API_KEY", ""):
            response = self.client.post("/api/v1/operation/forecast", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        lines = response.json()["data"]["lines"]
        self.assertEqual({line["metric"]: float(line["forecast"]) for line in lines}, {
            "settlement_amount": 120, "writeoff_amount": 90, "order_count": 12,
        })
        self.assertEqual(response.json()["data"]["insights"]["engine"], "rules")
        self.assertEqual(permission.call_args.args[2], "supply.operation.create")
        self.assertTrue(all("confirmed IS true" in str(statement) for statement in self.db.statements))

    def test_bounds_and_forbidden_before_database_access(self):
        with patch("app.api.deps.has_permission", return_value=True):
            for start, end in (("2026-11-01", "2027-02-01"), ("2026-11-02", "2026-11-01")):
                for suffix in ("forecast", "forecast/export"):
                    response = self.client.post("/api/v1/operation/" + suffix, json={"start_date": start, "end_date": end})
                    self.assertEqual(response.status_code, 422)
        self.assertEqual(self.db.entities, [])

    def test_factor_import_requires_create_permission(self):
        self.user.is_superuser = False
        with patch("app.api.deps.has_permission", side_effect=lambda db, user, permission, *args, **kwargs: permission == "supply.operation.view"):
            response = self.client.post("/api/v1/operation/forecast-factors/parse", files={"file": ("factors.xlsx", b"invalid")})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.client.get("/api/v1/operation/forecast-factors/template").status_code, 200)
        self.user.is_superuser = False
        with patch("app.api.deps.has_permission", return_value=False):
            for suffix in ("forecast", "forecast/export"):
                self.assertEqual(self.client.post("/api/v1/operation/" + suffix, json=self.payload).status_code, 403)
        self.assertEqual(self.db.entities, [])

    def test_export_sheets_permission_and_literal_factor_text(self):
        self.payload["factors"] = [{"start_date": "2026-09-04", "end_date": "2026-09-04", "factor_type": "活动", "name": "=1+1", "impact_rate": "0.1"}]
        with patch("app.api.deps.has_permission", return_value=True) as permission, patch("app.services.operation_insights.settings.DEEPSEEK_API_KEY", ""):
            response = self.client.post("/api/v1/operation/forecast/export", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(permission.call_args.args[2], "supply.operation.export")
        book = load_workbook(BytesIO(response.content))
        self.assertEqual(book.sheetnames, ["预测汇总", "分层明细", "影响因素", "数据质量"])
        self.assertEqual(book["分层明细"].max_row, 4)
        self.assertEqual(book["分层明细"].cell(2, 5).data_type, "n")
        self.assertEqual(book["分层明细"].cell(2, 7).data_type, "n")
        self.assertEqual(book["影响因素"].cell(2, 8).data_type, "n")
        name_cell = book["影响因素"].cell(2, 7)
        self.assertEqual(name_cell.value, "=1+1")
        self.assertEqual(name_cell.data_type, "s")
