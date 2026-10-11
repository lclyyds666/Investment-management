import asyncio
from io import BytesIO
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from starlette.datastructures import UploadFile

from app.api.v1.endpoints import ticket_ledger as endpoint
from app.api.v1.endpoints.ticket_ledger import approve_confirm, delete_confirm, delete_row, update_row, upload_confirm
from app.core.enums import ContractStatus, InvoiceSourceKind
from app.db.base import Base
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink, ScenicContractPreference
from app.models.ticket_ledger import TicketLedger
from app.schemas.ledger_contract import LedgerConfirmApproveIn
from app.schemas.ticket_ledger import TicketLedgerUpdateIn
from app.services.invoice_generation import ticket_period_key


def test_ticket_period_key_matches_ledger_grouping_rule():
    class Row:
        source_file = "source.xlsx"
        detail_name = "detail.xlsx"
        period_text = "period"
        check_date_text = "date"

    assert ticket_period_key(Row()) == "source.xlsx"


def _approved_contract(db, contract_no="TICKET-001"):
    contract = Contract(
        contract_no=contract_no,
        title=contract_no,
        scenic_id="s",
        business_scopes=[InvoiceSourceKind.TICKET.value],
        status=ContractStatus.APPROVED,
        created_by=1,
    )
    db.add(contract)
    db.flush()
    return contract


def _confirmed_period():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    contract = _approved_contract(db)
    rows = [
        TicketLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=1, jinying_amount=2, confirm_stored="c.pdf"),
        TicketLedger(scenic_id="s", row_no=2, platform="B", source_file="p", hexiao_amount=3, jinying_amount=4, confirm_stored="c.pdf"),
    ]
    db.add_all(rows)
    db.commit()
    approve_confirm(
        "s",
        rows[0].id,
        LedgerConfirmApproveIn(contract_id=contract.id),
        db=db,
        _=SimpleNamespace(id=1),
    )
    return db, rows


def test_approve_then_update_unconfirms_period_and_removes_invoices():
    db, rows = _confirmed_period()
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2
    update_row("s", rows[0].id, TicketLedgerUpdateIn(jinying_amount=Decimal("9")), db=db, _=None)
    db.expire_all()
    assert all(not row.confirmed for row in db.scalars(select(TicketLedger)).all())
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_delete_unconfirms_surviving_ticket_rows():
    db, rows = _confirmed_period()
    delete_row("s", rows[0].id, db=db, _=None)
    survivor = db.scalar(select(TicketLedger))
    assert survivor is not None and not survivor.confirmed
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_approve_empty_source_period_returns_bad_request():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    contract = _approved_contract(db)
    row = TicketLedger(
        scenic_id="s",
        row_no=1,
        platform="合计",
        source_file="empty-period",
        confirm_stored="confirm.pdf",
    )
    db.add(row)
    db.commit()

    with pytest.raises(HTTPException) as raised:
        approve_confirm(
            "s",
            row.id,
            LedgerConfirmApproveIn(contract_id=contract.id),
            db=db,
            _=SimpleNamespace(id=1),
        )

    assert raised.value.status_code == 400
    assert raised.value.detail == "cannot generate invoices for an empty source period"
    db.expire_all()
    assert db.get(TicketLedger, row.id).confirmed is False
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_reupload_and_delete_confirmation_invalidate_period(tmp_path, monkeypatch):
    db, rows = _confirmed_period()
    monkeypatch.setattr(endpoint, "_confirm_dir", lambda _: tmp_path)
    (tmp_path / "c.pdf").write_bytes(b"old")
    upload = UploadFile(filename="new.pdf", file=BytesIO(b"new"))
    asyncio.run(upload_confirm("s", rows[0].id, upload, db=db, _=None))
    db.expire_all()
    period = db.scalars(select(TicketLedger)).all()
    assert all(not row.confirmed for row in period)
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0
    new_stored = period[0].confirm_stored
    assert not (tmp_path / "c.pdf").exists()
    assert (tmp_path / new_stored).exists()
    contract_id = db.scalar(select(Contract.id).where(Contract.contract_no == "TICKET-001"))
    approve_confirm(
        "s",
        period[0].id,
        LedgerConfirmApproveIn(contract_id=contract_id),
        db=db,
        _=SimpleNamespace(id=1),
    )
    delete_confirm("s", period[0].id, db=db, _=None)
    assert not (tmp_path / new_stored).exists()
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_failed_reupload_removes_new_file_and_restores_old_state(tmp_path, monkeypatch):
    db, rows = _confirmed_period()
    monkeypatch.setattr(endpoint, "_confirm_dir", lambda _: tmp_path)
    (tmp_path / "c.pdf").write_bytes(b"old")
    real_commit = db.commit

    def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)
    upload = UploadFile(filename="new.pdf", file=BytesIO(b"new"))
    try:
        asyncio.run(upload_confirm("s", rows[0].id, upload, db=db, _=None))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected commit failure")
    monkeypatch.setattr(db, "commit", real_commit)
    db.expire_all()
    period = db.scalars(select(TicketLedger)).all()
    assert all(row.confirmed and row.confirm_stored == "c.pdf" for row in period)
    assert (tmp_path / "c.pdf").exists()
    assert [path.name for path in tmp_path.iterdir()] == ["c.pdf"]
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2


def test_invalidation_failure_removes_new_ticket_file_and_rolls_back(tmp_path, monkeypatch):
    db, rows = _confirmed_period()
    monkeypatch.setattr(endpoint, "_confirm_dir", lambda _: tmp_path)
    (tmp_path / "c.pdf").write_bytes(b"old")

    def fail_invalidation(*args, **kwargs):
        raise RuntimeError("invalidation failed")

    monkeypatch.setattr(endpoint.invoice_svc, "invalidate_period_invoices", fail_invalidation)
    upload = UploadFile(filename="new.pdf", file=BytesIO(b"new"))
    try:
        asyncio.run(upload_confirm("s", rows[0].id, upload, db=db, _=None))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected invalidation failure")
    db.expire_all()
    period = db.scalars(select(TicketLedger)).all()
    assert all(row.confirmed and row.confirm_stored == "c.pdf" for row in period)
    assert [path.name for path in tmp_path.iterdir()] == ["c.pdf"]
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2


def test_approve_links_contract_before_generating_invoices():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    contract = _approved_contract(db)
    rows = [
        TicketLedger(
            scenic_id="s",
            row_no=1,
            platform="A",
            source_file="p",
            hexiao_amount=1,
            jinying_amount=2,
            confirm_stored="c.pdf",
        ),
        TicketLedger(
            scenic_id="s",
            row_no=2,
            platform="B",
            source_file="p",
            hexiao_amount=3,
            jinying_amount=4,
            confirm_stored="c.pdf",
        ),
    ]
    db.add_all(rows)
    db.commit()

    approve_confirm(
        "s",
        rows[0].id,
        LedgerConfirmApproveIn(contract_id=contract.id),
        db=db,
        _=SimpleNamespace(id=9),
    )

    link = db.scalar(select(LedgerContractLink))
    assert link.contract_id == contract.id
    assert link.selected_by == 9
    assert all(row.confirmed for row in db.scalars(select(TicketLedger)).all())
    assert db.scalar(select(ScenicContractPreference)).last_contract_id == contract.id
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2


def test_reconfirm_with_different_contract_returns_conflict():
    db, rows = _confirmed_period()
    other_contract = _approved_contract(db, "TICKET-002")
    db.commit()

    with pytest.raises(HTTPException) as raised:
        approve_confirm(
            "s",
            rows[0].id,
            LedgerConfirmApproveIn(contract_id=other_contract.id),
            db=db,
            _=SimpleNamespace(id=1),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail == "confirmed_period_contract_locked"
    db.expire_all()
    assert db.scalar(select(LedgerContractLink)).contract_id != other_contract.id
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2


def test_invoice_sync_failure_rolls_back_contract_link_and_confirmation(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    contract = _approved_contract(db)
    row = TicketLedger(
        scenic_id="s",
        row_no=1,
        platform="A",
        source_file="p",
        hexiao_amount=1,
        jinying_amount=2,
        confirm_stored="c.pdf",
    )
    db.add(row)
    db.commit()

    def fail_sync(*args, **kwargs):
        raise RuntimeError("sync failed")

    monkeypatch.setattr(endpoint.invoice_svc, "sync_confirmed_period_invoices", fail_sync)
    with pytest.raises(RuntimeError, match="sync failed"):
        approve_confirm(
            "s",
            row.id,
            LedgerConfirmApproveIn(contract_id=contract.id),
            db=db,
            _=SimpleNamespace(id=1),
        )

    db.expire_all()
    assert db.get(TicketLedger, row.id).confirmed is False
    assert db.scalar(select(LedgerContractLink)) is None
    assert db.scalar(select(ScenicContractPreference)) is None
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0
