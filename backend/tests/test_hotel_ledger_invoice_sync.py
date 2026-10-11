import asyncio
from io import BytesIO
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

import app.db.init_db  # noqa: F401
from app.api.v1.endpoints import hotel_ledger as endpoint
from app.api.v1.endpoints.hotel_ledger import approve_confirm, delete_row, update_row, upload_confirm
from app.core.enums import ContractStatus, InvoiceSourceKind
from app.db.base import Base
from app.models.contract import Contract
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice, InvoiceAttachment
from app.models.ledger_contract import LedgerContractLink, ScenicContractPreference
from app.schemas.hotel_ledger import HotelUpdateIn
from app.schemas.ledger_contract import LedgerConfirmApproveIn
from app.services.invoice_generation import hotel_period_key


def test_hotel_period_key_matches_ledger_grouping_rule():
    class Row:
        source_file = ""
        detail_name = ""
        period_text = "period"
        check_date_text = "date"

    assert hotel_period_key(Row()) == "period"


def _approved_contract(db):
    contract = Contract(
        contract_no="HOTEL-001",
        title="HOTEL-001",
        scenic_id="s",
        business_scopes=[InvoiceSourceKind.HOTEL.value],
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
        HotelLedger(scenic_id="s", row_no=1, platform="A", source_file="p", hexiao_amount=1, jinying_amount=2, confirm_stored="c.pdf"),
        HotelLedger(scenic_id="s", row_no=2, platform="B", source_file="p", hexiao_amount=3, jinying_amount=4, confirm_stored="c.pdf"),
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


def test_approve_then_update_unconfirms_hotel_period():
    db, rows = _confirmed_period()
    update_row("s", rows[0].id, HotelUpdateIn(jinying_amount=Decimal("9")), db=db, _=None)
    db.expire_all()
    assert all(not row.confirmed for row in db.scalars(select(HotelLedger)).all())
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_delete_unconfirms_surviving_hotel_rows():
    db, rows = _confirmed_period()
    delete_row("s", rows[0].id, db=db, _=None)
    survivor = db.scalar(select(HotelLedger))
    assert survivor is not None and not survivor.confirmed
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0


def test_hotel_update_maps_used_invoice_lock_to_conflict():
    db, rows = _confirmed_period()
    invoice = db.scalar(select(Invoice).where(Invoice.direction == "output"))
    db.add(InvoiceAttachment(
        invoice_id=invoice.id,
        original_name="issued.pdf",
        stored_name="issued.pdf",
    ))
    db.commit()

    with pytest.raises(HTTPException) as raised:
        update_row(
            "s",
            rows[0].id,
            HotelUpdateIn(jinying_amount=Decimal("9")),
            db=db,
            _=None,
        )

    assert raised.value.status_code == 409
    assert raised.value.detail == "invoice_source_locked"
    db.expire_all()
    assert all(row.confirmed for row in db.scalars(select(HotelLedger)).all())
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2


def test_invalidation_failure_removes_new_hotel_file_and_rolls_back(tmp_path, monkeypatch):
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
    period = db.scalars(select(HotelLedger)).all()
    assert all(row.confirmed and row.confirm_stored == "c.pdf" for row in period)
    assert [path.name for path in tmp_path.iterdir()] == ["c.pdf"]
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2


def test_hotel_approve_links_hotel_preference_independently():
    db, rows = _confirmed_period()

    link = db.scalar(select(LedgerContractLink))
    preference = db.scalar(select(ScenicContractPreference))
    assert link.source_kind == InvoiceSourceKind.HOTEL
    assert preference.source_kind == InvoiceSourceKind.HOTEL
    assert link.contract_id == preference.last_contract_id
