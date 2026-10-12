import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.operation import router
from app.db.session import get_db


class OperationFinancialApiTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/operation")
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1, is_superuser=True, is_active=True
        )
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_financial_endpoint_serializes_null_zero_denominator(self):
        dashboard = {
            "existing_scale": Decimal("100.00"),
            "total_realized_scale": Decimal("80.00"),
            "total_gross_income": Decimal("5.00"),
            "capital_occupation_days": 10.0,
            "ledger_profit": [],
            "available_years": [2026],
            "scenic_ids": ["empty"],
            "scenic_completion": [{
                "scenic_id": "empty",
                "business_type": "ticket",
                "cumulative_writeoff": Decimal("0.00"),
                "pending_writeoff": Decimal("0.00"),
                "completion_rate": None,
            }],
        }
        with patch("app.api.deps.has_permission", return_value=True), patch(
            "app.api.v1.endpoints.operation.financial_svc.build_dashboard",
            return_value=dashboard,
        ) as build_dashboard:
            response = self.client.get("/api/v1/operation/financial")

        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()["data"]["scenic_completion"][0]
        self.assertIn("cumulative_writeoff", detail)
        self.assertIn("pending_writeoff", detail)
        self.assertIsNone(detail["completion_rate"])
        self.assertEqual(response.json()["data"]["total_gross_income"], "5.00")
        build_dashboard.assert_called_once()

    def test_financial_endpoint_keeps_dashboard_permission(self):
        with patch("app.api.deps.has_permission", return_value=False):
            response = self.client.get("/api/v1/operation/financial")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
