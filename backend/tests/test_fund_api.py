import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.models.fund import FundTransaction


class FakeSession:
    def __init__(self):
        self.row = None

    def add(self, row):
        row.id = 1
        self.row = row

    def get(self, _model, fund_id, **_kwargs):
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

    def test_all_mutations_require_update_permission_via_http(self):
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7, is_superuser=False, is_active=True
        )
        payload = {
            "direction": "increase",
            "category": "company_loan",
            "amount": "100000",
            "occurred_on": "2026-08-28",
            "maturity_date": "2026-09-27",
        }
        requests = (
            ("post", "/api/v1/funds", payload),
            ("put", "/api/v1/funds/1", payload),
            ("delete", "/api/v1/funds/1", None),
            ("post", "/api/v1/funds/1/settle", {"settled_on": "2026-08-29"}),
        )

        with patch("app.api.deps.has_permission", return_value=False) as permission_check:
            for method, path, body in requests:
                with self.subTest(method=method, path=path):
                    response = self.client.request(method.upper(), path, json=body)
                    self.assertEqual(response.status_code, 403, response.text)

        self.assertEqual(permission_check.call_count, 4)
        self.assertEqual(
            {call.args[2] for call in permission_check.call_args_list},
            {"supply.finance.update"},
        )

    def test_update_and_settle_missing_return_404_via_http(self):
        self.db.get.return_value = None
        payload = {
            "direction": "increase",
            "category": "company_loan",
            "amount": "100000",
            "occurred_on": "2026-08-28",
            "maturity_date": "2026-09-27",
        }

        updated = self.client.put("/api/v1/funds/404", json=payload)
        settled = self.client.post(
            "/api/v1/funds/404/settle",
            json={"settled_on": "2026-08-29"},
        )

        self.assertEqual(updated.status_code, 404, updated.text)
        self.assertEqual(settled.status_code, 404, settled.text)

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

        with self.assertRaises(HTTPException) as raised:
            settle_fund(
                1, FundSettleIn(settled_on=date(2026, 8, 27)), db, user
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(db.row.settlement_status, "open")

        from app.services.fund import summarize_funds

        balance_before = summarize_funds([db.row], date(2026, 8, 28)).available_funds

        settled = settle_fund(
            1, FundSettleIn(settled_on=date(2026, 8, 29)), db, user
        )
        self.assertEqual(settled.data.settlement_status, "settled")
        self.assertEqual(
            summarize_funds([db.row], date(2026, 8, 28)).available_funds,
            balance_before,
        )

        with self.assertRaises(HTTPException) as raised:
            settle_fund(
                1, FundSettleIn(settled_on=date(2026, 8, 30)), db, user
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(db.row.settled_on, date(2026, 8, 29))

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

    def test_settled_fund_rejects_direction_or_category_changes(self):
        from app.api.v1.endpoints.fund import create_fund, settle_fund, update_fund
        from app.schemas.fund import (
            FundSettleIn,
            FundTransactionCreate,
            FundTransactionUpdate,
        )

        db = FakeSession()
        user = SimpleNamespace(id=9)
        create_fund(
            FundTransactionCreate(
                direction="increase",
                category="company_loan",
                amount=Decimal("100000"),
                occurred_on=date(2026, 8, 28),
                maturity_date=date(2026, 9, 27),
                summary="流动资金借款",
            ),
            db,
            user,
        )
        settle_fund(1, FundSettleIn(settled_on=date(2026, 8, 29)), db, user)

        changed_classifications = (
            FundTransactionUpdate(
                direction="usage",
                category="expense",
                amount=Decimal("100000"),
                occurred_on=date(2026, 8, 28),
                summary="改变方向",
            ),
            FundTransactionUpdate(
                direction="increase",
                category="customer_payment",
                amount=Decimal("100000"),
                occurred_on=date(2026, 8, 28),
                summary="改变类型",
            ),
        )
        for payload in changed_classifications:
            with self.subTest(direction=payload.direction, category=payload.category):
                with self.assertRaises(HTTPException) as raised:
                    update_fund(1, payload, db, user)
                self.assertEqual(raised.exception.status_code, 409)

        with self.assertRaises(HTTPException) as raised:
            update_fund(
                1,
                FundTransactionUpdate(
                    direction="increase",
                    category="company_loan",
                    amount=Decimal("100000"),
                    occurred_on=date(2026, 8, 30),
                    maturity_date=date(2026, 9, 27),
                    summary="发生日期晚于结清日期",
                ),
                db,
                user,
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(db.row.occurred_on, date(2026, 8, 28))

        updated = update_fund(
            1,
            FundTransactionUpdate(
                direction="increase",
                category="company_loan",
                amount=Decimal("100000"),
                occurred_on=date(2026, 8, 28),
                maturity_date=date(2026, 9, 27),
                counterparty="更新后的对方单位",
                summary="只修改非分类字段",
            ),
            db,
            user,
        )
        self.assertEqual(updated.data.counterparty, "更新后的对方单位")
        self.assertEqual(updated.data.summary, "只修改非分类字段")
        self.assertEqual(updated.data.settlement_status, "settled")
        self.assertEqual(updated.data.settled_on, date(2026, 8, 29))


class FundListDatabasePaginationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        FundTransaction.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.executed_sql = []
        event.listen(
            self.engine,
            "before_cursor_execute",
            lambda _conn, _cursor, statement, _parameters, _context, _executemany:
                self.executed_sql.append(statement),
        )
        self.db.add_all([
            FundTransaction(
                id=1,
                direction="increase",
                category="bank_credit",
                amount=Decimal("500000"),
                occurred_on=date(2026, 8, 25),
                counterparty="星河银行",
                summary="流动资金授信",
                maturity_date=date(2026, 9, 25),
                settlement_status="open",
                remark="",
            ),
            FundTransaction(
                id=2,
                direction="increase",
                category="company_loan",
                amount=Decimal("300000"),
                occurred_on=date(2026, 8, 20),
                counterparty="股东公司",
                summary="已结清借款",
                maturity_date=date(2026, 9, 20),
                settlement_status="settled",
                settled_on=date(2026, 8, 22),
                remark="",
            ),
            FundTransaction(
                id=3,
                direction="increase",
                category="customer_payment",
                amount=Decimal("120000"),
                occurred_on=date(2026, 8, 15),
                counterparty="海洋客户",
                summary="项目回款",
                settlement_status="open",
                remark="",
            ),
            FundTransaction(
                id=4,
                direction="usage",
                category="business_payment",
                amount=Decimal("80000"),
                occurred_on=date(2026, 8, 24),
                counterparty="景区供应商",
                summary="门票业务付款",
                settlement_status="open",
                remark="",
            ),
            FundTransaction(
                id=5,
                direction="usage",
                category="expense",
                amount=Decimal("6000"),
                occurred_on=date(2026, 8, 18),
                counterparty="差旅平台",
                summary="差旅费用",
                settlement_status="open",
                remark="南阳项目拜访",
            ),
            FundTransaction(
                id=6,
                direction="usage",
                category="principal_interest_payment",
                amount=Decimal("50000"),
                occurred_on=date(2026, 8, 26),
                counterparty="星河银行",
                summary="还本付息",
                settlement_status="open",
                remark="",
            ),
        ])
        self.db.commit()
        self.app = create_app()
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7, is_superuser=True, is_active=True
        )
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_plain_list_uses_database_count_limit_offset_and_keeps_total(self):
        self.executed_sql.clear()

        response = self.client.get(
            "/api/v1/funds",
            params={"direction": "usage", "page": 2, "page_size": 2},
        )

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["total"], 3)
        self.assertEqual([item["id"] for item in data["items"]], [5])
        normalized_sql = [" ".join(statement.lower().split()) for statement in self.executed_sql]
        self.assertTrue(
            any("select count(" in statement for statement in normalized_sql),
            normalized_sql,
        )
        self.assertTrue(
            any(
                "from biz_fund_transaction" in statement
                and " limit " in statement
                and " offset " in statement
                for statement in normalized_sql
            ),
            normalized_sql,
        )

    def test_core_filters_run_through_http_and_preserve_sorting_and_totals(self):
        cases = (
            ({"category": "expense"}, [5]),
            ({"settlement_status": "settled"}, [2]),
            ({"start_date": "2026-08-20", "end_date": "2026-08-25"}, [1, 4, 2]),
            ({"keyword": "南阳"}, [5]),
        )

        for params, expected_ids in cases:
            with self.subTest(params=params):
                response = self.client.get("/api/v1/funds", params=params)
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()["data"]
                self.assertEqual(data["total"], len(expected_ids))
                self.assertEqual([item["id"] for item in data["items"]], expected_ids)


if __name__ == "__main__":
    unittest.main()
