from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app.core.enums import InvoiceSourceKind
from app.db.base import Base
from app.models.ticket_ledger import TicketLedger
from app.services.ledger_period_lock import (
    lock_period_rows,
    period_rows_for_update_statement,
)


def test_period_lock_statement_has_stable_order_and_for_update():
    statement = period_rows_for_update_statement(
        InvoiceSourceKind.TICKET,
        "scenic-a",
        "period-1",
    )
    sql = str(statement.compile(dialect=mysql.dialect())).upper()
    assert "ORDER BY" in sql
    assert "FOR UPDATE" in sql


def test_edit_delete_and_confirm_paths_share_period_lock_helper():
    root = Path(__file__).resolve().parents[1]
    ticket = (root / "app/api/v1/endpoints/ticket_ledger.py").read_text(encoding="utf-8")
    hotel = (root / "app/api/v1/endpoints/hotel_ledger.py").read_text(encoding="utf-8")
    for source in (ticket, hotel):
        assert source.count("lock_period_rows_for_row(") >= 4
        assert "lock_period_invoices(" in source


@pytest.mark.skipif(
    not os.getenv("MYSQL_TEST_URL"),
    reason="set MYSQL_TEST_URL to run InnoDB blocking regression",
)
def test_innodb_second_session_waits_for_period_lock():
    engine = create_engine(os.environ["MYSQL_TEST_URL"], pool_pre_ping=True)
    Base.metadata.create_all(engine)
    first = Session(engine)
    try:
        first.add(
            TicketLedger(
                scenic_id="lock-test",
                row_no=1,
                platform="A",
                source_file="period-lock-test",
            )
        )
        first.commit()
        lock_period_rows(
            first,
            scenic_id="lock-test",
            source_kind=InvoiceSourceKind.TICKET,
            period_key="period-lock-test",
        )
        def acquire_in_second_session():
            with Session(engine) as second:
                rows = second.scalars(
                    period_rows_for_update_statement(
                        InvoiceSourceKind.TICKET,
                        "lock-test",
                        "period-lock-test",
                    )
                ).all()
                second.rollback()
                return rows

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(acquire_in_second_session)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.5)
            first.commit()
            assert future.result(timeout=5)
    finally:
        first.rollback()
        first.close()
        engine.dispose()
