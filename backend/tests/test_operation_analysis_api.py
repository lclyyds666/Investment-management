import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.operation import router
from app.db.session import get_db
from app.models.hotel_ledger import HotelLedger
from app.models.ticket_ledger import TicketLedger


class _ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeDatabase:
    def __init__(self, tickets, hotels):
        self.rows = {TicketLedger: tickets, HotelLedger: hotels}
        self.entities = []
        self.statements = []

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        self.entities.append(entity)
        self.statements.append(statement)
        return _ScalarResult(self.rows[entity])


def _ledger(**overrides):
    values = {
        "id": 1,
        "scenic_id": "scenic-a",
        "platform": "platform-a",
        "period_start": date(2026, 9, 1),
        "period_end": date(2026, 9, 1),
        "jinying_amount": Decimal("120"),
        "hexiao_amount": Decimal("90"),
        "order_count": 12,
        "confirmed": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _client_with_database():
    database = _FakeDatabase(
        [
            _ledger(),
            _ledger(id=2, period_start=date(2026, 8, 31), period_end=date(2026, 8, 31), jinying_amount=Decimal("100"), hexiao_amount=Decimal("75"), order_count=10),
        ],
        [],
    )
    user = SimpleNamespace(id=1, is_superuser=True, is_active=True)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/operation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: database
    return app, TestClient(app), database, user


class OperationAnalysisApiTests(unittest.TestCase):
    def test_uses_confirmed_ledgers_filters_and_view_permission(self):
        app, client, database, user = _client_with_database()
        with patch("app.api.deps.has_permission", return_value=True) as permission_check:
            response = client.get(
                "/api/v1/operation/analysis",
                params=[
                    ("start_date", "2026-09-01"), ("end_date", "2026-09-01"),
                    ("scenic_id", "scenic-a"), ("platform", "platform-a"),
                ],
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()["data"]
        self.assertEqual(body["summary"]["settlement_amount"], "120.00")
        self.assertEqual(body["comparisons"]["settlement"]["mom_rate"], "20.00")
        self.assertEqual(database.entities, [TicketLedger, HotelLedger])
        self.assertTrue(all("confirmed IS true" in str(statement) for statement in database.statements))
        self.assertEqual(permission_check.call_args.args[2], "supply.operation.view")

        user.is_superuser = False
        with patch("app.api.deps.has_permission", return_value=False):
            forbidden = client.get(
                "/api/v1/operation/analysis?start_date=2026-09-01&end_date=2026-09-01"
            )
        self.assertEqual(forbidden.status_code, 403)
        client.close()
        app.dependency_overrides.clear()

    def test_validates_date_order_and_maximum_span(self):
        app, client, _database, _user = _client_with_database()
        with patch("app.api.deps.has_permission", return_value=True):
            reversed_response = client.get(
                "/api/v1/operation/analysis?start_date=2026-09-02&end_date=2026-09-01"
            )
            oversized_response = client.get(
                "/api/v1/operation/analysis?start_date=2025-01-01&end_date=2026-01-02"
            )
        self.assertEqual(reversed_response.status_code, 422)
        self.assertEqual(oversized_response.status_code, 422)
        with patch("app.api.deps.has_permission", return_value=True):
            invalid_business = client.get(
                "/api/v1/operation/analysis?start_date=2026-09-01&end_date=2026-09-01&business_type=other"
            )
        self.assertEqual(invalid_business.status_code, 422)
        client.close()
        app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
