import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app


class FakeSession:
    def __init__(self):
        self.row = None

    def add(self, row):
        row.id = 1
        self.row = row

    def get(self, _model, fund_id):
        return self.row if self.row and self.row.id == fund_id else None

    def commit(self):
        return None

    def refresh(self, _row):
        return None

    def delete(self, _row):
        self.row = None


class FundApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = Mock()
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7, is_superuser=True, is_active=True
        )
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_routes_are_registered(self):
        paths = {route.path for route in self.app.routes}
        self.assertIn("/api/v1/funds", paths)
        self.assertIn("/api/v1/funds/summary", paths)
        self.assertIn("/api/v1/funds/{fund_id}/settle", paths)

    def test_view_permission_is_required(self):
        from app.api.v1.endpoints.fund import _view_guard

        def deny_view():
            raise HTTPException(status_code=403, detail="权限不足")

        self.app.dependency_overrides[_view_guard] = deny_view
        response = self.client.get("/api/v1/funds")

        self.assertEqual(response.status_code, 403)

    def test_create_and_update_cannot_set_settlement_state(self):
        payload = {
            "direction": "increase",
            "category": "company_loan",
            "amount": "100000",
            "occurred_on": "2026-08-28",
            "maturity_date": "2026-09-27",
        }
        for method, path, field, value in (
            ("post", "/api/v1/funds", "settlement_status", "settled"),
            ("post", "/api/v1/funds", "settled_on", "2026-08-29"),
            ("put", "/api/v1/funds/1", "settlement_status", "settled"),
            ("put", "/api/v1/funds/1", "settled_on", "2026-08-29"),
        ):
            with self.subTest(method=method, field=field):
                response = getattr(self.client, method)(path, json={**payload, field: value})
                self.assertEqual(response.status_code, 422)

    def test_create_settle_delete_and_missing(self):
        from app.api.v1.endpoints.fund import (
            create_fund,
            delete_fund,
            settle_fund,
        )
        from app.schemas.fund import FundSettleIn, FundTransactionCreate

        db = FakeSession()
        user = SimpleNamespace(id=9)
        created = create_fund(
            FundTransactionCreate(
                direction="increase",
                category="company_loan",
                amount=Decimal("100000"),
                occurred_on=date(2026, 8, 28),
                maturity_date=date(2026, 9, 27),
                counterparty="股东公司",
                summary="流动资金借款",
            ),
            db,
            user,
        )
        self.assertEqual(db.row.created_by, 9)
        self.assertEqual(created.data.amount, Decimal("100000"))

        settled = settle_fund(
            1, FundSettleIn(settled_on=date(2026, 8, 29)), db, user
        )
        self.assertEqual(settled.data.settlement_status, "settled")

        delete_fund(1, db)
        self.assertIsNone(db.row)
        with self.assertRaises(HTTPException) as raised:
            delete_fund(404, db)
        self.assertEqual(raised.exception.status_code, 404)

        created = create_fund(
            FundTransactionCreate(
                direction="increase",
                category="customer_payment",
                amount=Decimal("1000"),
                occurred_on=date(2026, 8, 28),
            ),
            db,
            user,
        )
        with self.assertRaises(HTTPException) as raised:
            settle_fund(created.data.id, FundSettleIn(), db, user)
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
