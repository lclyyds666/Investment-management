import tempfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.api.deps import get_current_user
from app.core.enums import AssignmentStatus, ContractType, InvoiceDirection, InvoiceSourceKind, InvoiceStatus
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.approval_form import ApprovalForm
from app.models.invoice import Invoice, InvoiceAttachment, InvoiceDetail
from app.models.organization import Organization, Position, UserAssignment
from app.models.user import User
from app.schemas.invoice import InvoiceCreate
from app.services.assignment_permissions import PermissionContext, has_permission
from app.services.invoice_documents import assert_invoice_details_balanced
from app.services.invoice_generation import remove_period_invoices
from app.services.organization_catalog import seed_authorization_catalog


def _zip_bytes(*names):
    content = BytesIO()
    with ZipFile(content, "w", ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, b"content")
    return content.getvalue()


@pytest.fixture
def invoice_api(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    db = Session(engine)
    seed_authorization_catalog(db)

    def add_user(username, position_code):
        user = User(username=username, full_name=username, hashed_password="test", is_active=True)
        db.add(user)
        db.flush()
        db.add(UserAssignment(
            user_id=user.id,
            organization_id=db.scalar(select(Organization.id).where(Organization.code == "supplymanagement")),
            position_id=db.scalar(select(Position.id).where(Position.code == position_code)),
            valid_from=date(2026, 1, 1),
            status=AssignmentStatus.ACTIVE,
        ))
        db.flush()
        return user

    users = {
        "handler": add_user("handler", "supply.business_handler"),
        "reviewer": add_user("reviewer", "supply.business_reviewer"),
        "governance": add_user("governance", "governance.supply_leader"),
    }
    invoice = Invoice(
        invoice_title="景区销项发票",
        amount=Decimal("100.00"),
        status=InvoiceStatus.PENDING,
        direction=InvoiceDirection.OUTPUT,
        source_kind=InvoiceSourceKind.TICKET,
        scenic_id="scenic-a",
        period_key="2026-09",
        source_revision=1,
        source_fingerprint="fingerprint",
        generated_by_source=True,
    )
    invoice.details.extend([
        InvoiceDetail(line_no=1, platform="A", item_name="门票", amount=Decimal("40.00")),
        InvoiceDetail(line_no=2, platform="B", item_name="门票", amount=Decimal("60.00")),
    ])
    legacy = Invoice(invoice_title="历史手工发票", amount=Decimal("8.00"), status=InvoiceStatus.VOID)
    other = Invoice(
        invoice_title="酒店进项发票",
        amount=Decimal("50.00"),
        direction=InvoiceDirection.INPUT,
        source_kind=InvoiceSourceKind.HOTEL,
        scenic_id="scenic-b",
        period_key="2026-08",
        generated_by_source=True,
    )
    db.add_all([invoice, legacy, other])
    db.commit()

    app = create_app()
    current = {"user": users["reviewer"]}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    upload_dir = tempfile.TemporaryDirectory()
    monkeypatch.setattr("app.services.invoice_documents.settings.UPLOAD_DIR", upload_dir.name)
    client = TestClient(app, raise_server_exceptions=False)
    yield db, client, current, users, invoice, legacy, other, Path(upload_dir.name)
    client.close()
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
    upload_dir.cleanup()


def test_manual_create_delete_are_closed_and_create_schema_rejects_status(invoice_api):
    _, client, _, _, invoice, _, _, _ = invoice_api
    assert client.post("/api/v1/invoices", json={"invoice_title": "manual"}).status_code == 405
    assert client.delete(f"/api/v1/invoices/{invoice.id}").status_code == 405
    with pytest.raises(ValidationError):
        InvoiceCreate(invoice_title="manual", status=InvoiceStatus.ISSUED)


def test_invoice_permissions_are_separated(invoice_api):
    db, client, current, users, invoice, _, _, _ = invoice_api
    context = PermissionContext(company_code="supplymanagement")
    assert has_permission(db, users["reviewer"], "supply.invoice.manage", context)
    assert not has_permission(db, users["handler"], "supply.invoice.manage", context)
    assert not has_permission(db, users["governance"], "supply.invoice.manage", context)
    assert has_permission(db, users["governance"], "supply.invoice.approve", context)

    current["user"] = users["handler"]
    assert client.get("/api/v1/invoices").status_code == 200
    assert client.put(f"/api/v1/invoices/{invoice.id}", json={"remark": "x"}).status_code == 403
    assert client.post(
        f"/api/v1/invoices/{invoice.id}/attachments",
        files=[("files", ("invoice.pdf", b"%PDF-x", "application/pdf"))],
    ).status_code == 403
    current["user"] = users["governance"]
    assert client.get("/api/v1/invoices").status_code == 200
    assert client.put(f"/api/v1/invoices/{invoice.id}", json={"remark": "x"}).status_code == 403
    assert client.post(
        f"/api/v1/invoices/{invoice.id}/attachments",
        files=[("files", ("invoice.pdf", b"%PDF-x", "application/pdf"))],
    ).status_code == 403


def test_list_filters_and_global_stats_remain_compatible(invoice_api):
    _, client, _, _, invoice, legacy, _, _ = invoice_api
    response = client.get("/api/v1/invoices", params={
        "direction": "output",
        "scenic_id": "scenic-a",
        "source_kind": "ticket",
        "period_key": "2026-09",
        "status": "pending",
    })
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["data"]] == [invoice.id]
    response = client.get("/api/v1/invoices", params={"status": "void"})
    assert [row["id"] for row in response.json()["data"]] == [legacy.id]
    stats = client.get("/api/v1/invoices/stats").json()["data"]
    assert set(("total", "pending", "issued", "void", "issued_amount", "pending_amount")) <= stats.keys()


@pytest.mark.parametrize("field,value", [
    ("status", "issued"),
    ("direction", "input"),
    ("source_kind", "hotel"),
    ("scenic_id", "other"),
    ("period_key", "other"),
    ("source_revision", 99),
    ("source_fingerprint", "other"),
    ("generated_by_source", False),
    ("workflow_instance_id", 1),
    ("approval_status", "approved"),
])
def test_update_rejects_identity_and_workflow_fields(invoice_api, field, value):
    _, client, _, _, invoice, _, _, _ = invoice_api
    response = client.put(f"/api/v1/invoices/{invoice.id}", json={field: value})
    assert response.status_code == 422, response.text


def test_update_allows_business_snapshot_fields(invoice_api):
    db, client, _, _, invoice, _, _, _ = invoice_api
    response = client.put(f"/api/v1/invoices/{invoice.id}", json={
        "invoice_title": "新抬头",
        "tax_no": "9137",
        "amount": "120.00",
        "contract_no": "HT-1",
        "customer_name": "客户",
        "customer_social_credit_code": "913700",
        "customer_address": "地址",
        "customer_phone": "123",
        "customer_bank_name": "银行",
        "customer_bank_account": "账号",
        "remark": "备注",
    })
    assert response.status_code == 200, response.text
    db.refresh(invoice)
    assert invoice.amount == Decimal("120.00")
    assert invoice.customer_bank_account == "账号"


@pytest.mark.parametrize("field", ["amount", "tax_no", "customer_name"])
def test_update_rejects_explicit_null_for_non_nullable_fields(invoice_api, field):
    _, client, _, _, invoice, _, _, _ = invoice_api
    response = client.put(f"/api/v1/invoices/{invoice.id}", json={field: None})
    assert response.status_code == 422, response.text


def test_multi_file_upload_marks_issued_and_later_upload_appends(invoice_api):
    db, client, _, _, invoice, _, _, upload_root = invoice_api
    first = client.post(f"/api/v1/invoices/{invoice.id}/attachments", files=[
        ("files", ("invoice-a.pdf", b"%PDF-a", "text/plain")),
        ("files", ("invoice-b.jpg", b"\xff\xd8\xffb", "application/pdf")),
    ])
    assert first.status_code == 200, first.text
    assert len(first.json()["data"]) == 2
    assert [row["content_type"] for row in first.json()["data"]] == [
        "application/pdf",
        "image/jpeg",
    ]
    assert len(client.get(f"/api/v1/invoices/{invoice.id}/attachments").json()["data"]) == 2
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.ISSUED
    assert len(list((upload_root / "invoices" / str(invoice.id)).iterdir())) == 2
    second = client.post(
        f"/api/v1/invoices/{invoice.id}/attachments",
        files=[("files", ("invoice-c.png", b"\x89PNG\r\n\x1a\n", "application/octet-stream"))],
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["data"]) == 3
    assert second.json()["data"][-1]["content_type"] == "image/png"


def test_attachment_rejects_fake_pdf_content(invoice_api):
    db, client, _, _, invoice, _, _, upload_root = invoice_api
    response = client.post(
        f"/api/v1/invoices/{invoice.id}/attachments",
        files=[("files", ("fake.pdf", b"not a pdf", "application/pdf"))],
    )
    assert response.status_code == 400, response.text
    assert db.scalar(select(func.count()).select_from(InvoiceAttachment)) == 0
    directory = upload_root / "invoices" / str(invoice.id)
    assert not directory.exists() or list(directory.iterdir()) == []


def test_office_and_ofd_attachments_validate_containers_and_derive_mime(invoice_api):
    _, client, _, _, invoice, _, _, _ = invoice_api
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy"
    response = client.post(f"/api/v1/invoices/{invoice.id}/attachments", files=[
        ("files", ("invoice.ofd", _zip_bytes("OFD.xml", "Doc_0/Document.xml"), "text/plain")),
        ("files", ("invoice.docx", _zip_bytes("[Content_Types].xml", "word/document.xml"), "text/plain")),
        ("files", ("invoice.xlsx", _zip_bytes("[Content_Types].xml", "xl/workbook.xml"), "text/plain")),
        ("files", ("invoice.doc", ole, "application/octet-stream")),
        ("files", ("invoice.xls", ole, "application/octet-stream")),
    ])
    assert response.status_code == 200, response.text
    assert [row["content_type"] for row in response.json()["data"]] == [
        "application/ofd",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/msword",
        "application/vnd.ms-excel",
    ]


def test_office_and_ofd_attachments_reject_spoofed_content(invoice_api):
    db, client, _, _, invoice, _, _, upload_root = invoice_api
    fake_files = [
        ("fake.ofd", _zip_bytes("random.xml")),
        ("fake.docx", _zip_bytes("[Content_Types].xml", "xl/workbook.xml")),
        ("fake.xlsx", _zip_bytes("[Content_Types].xml", "word/document.xml")),
        ("fake.doc", b"%PDF-not-ole"),
        ("fake.xls", b"%PDF-not-ole"),
    ]
    for filename, content in fake_files:
        response = client.post(
            f"/api/v1/invoices/{invoice.id}/attachments",
            files=[("files", (filename, content, "application/octet-stream"))],
        )
        assert response.status_code == 400, (filename, response.text)
    assert db.scalar(select(func.count()).select_from(InvoiceAttachment)) == 0
    directory = upload_root / "invoices" / str(invoice.id)
    assert not directory.exists() or list(directory.iterdir()) == []
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PENDING


def test_attachment_batch_failure_keeps_files_and_database_consistent(invoice_api):
    db, client, _, _, invoice, _, _, upload_root = invoice_api
    response = client.post(f"/api/v1/invoices/{invoice.id}/attachments", files=[
        ("files", ("invoice.docx", _zip_bytes("[Content_Types].xml", "word/document.xml"), "application/zip")),
        ("files", ("fake.xlsx", _zip_bytes("[Content_Types].xml", "word/document.xml"), "application/zip")),
    ])
    assert response.status_code == 400, response.text
    assert db.scalar(select(func.count()).select_from(InvoiceAttachment)) == 0
    directory = upload_root / "invoices" / str(invoice.id)
    assert not directory.exists() or list(directory.iterdir()) == []
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PENDING

    for unsafe_name in ("../escape.pdf", "..\\escape.pdf"):
        response = client.post(
            f"/api/v1/invoices/{invoice.id}/attachments",
            files=[("files", (unsafe_name, b"%PDF-unsafe", "application/pdf"))],
        )
        assert response.status_code == 400, response.text


def test_attachment_download_is_authorized_and_scoped(invoice_api):
    _, client, current, users, invoice, _, other, _ = invoice_api
    uploaded = client.post(
        f"/api/v1/invoices/{invoice.id}/attachments",
        files=[("files", ("invoice.pdf", b"%PDF-download", "application/pdf"))],
    ).json()["data"][0]
    current["user"] = users["handler"]
    response = client.get(f"/api/v1/invoices/{invoice.id}/attachments/{uploaded['id']}")
    assert response.status_code == 200
    assert response.content == b"%PDF-download"
    assert client.get(f"/api/v1/invoices/{other.id}/attachments/{uploaded['id']}").status_code == 404


def test_detail_update_may_be_unbalanced_but_public_guard_blocks(invoice_api):
    db, client, _, _, invoice, _, _, _ = invoice_api
    details = client.get(f"/api/v1/invoices/{invoice.id}/details")
    assert details.status_code == 200, details.text
    assert details.json()["data"]["detail_total"] == "100.00"
    detail_id = invoice.details[0].id
    updated = client.put(
        f"/api/v1/invoices/{invoice.id}/details/{detail_id}",
        json={"amount": "30.00", "platform": "A1", "item_name": "调整门票"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["difference"] == "10.00"
    db.refresh(invoice)
    with pytest.raises(HTTPException) as raised:
        assert_invoice_details_balanced(invoice)
    assert raised.value.status_code == 409
    assert client.put(
        f"/api/v1/invoices/{invoice.id}/details/{detail_id}", json={"amount": "40.00"}
    ).status_code == 200
    db.refresh(invoice)
    assert_invoice_details_balanced(invoice)


def test_detail_source_identity_is_rejected_and_stats_are_available(invoice_api):
    _, client, _, _, invoice, _, input_invoice, _ = invoice_api
    detail_id = invoice.details[0].id
    assert client.put(
        f"/api/v1/invoices/{invoice.id}/details/{detail_id}", json={"source_row_id": 999}
    ).status_code == 422
    response = client.get(f"/api/v1/invoices/{invoice.id}/stats")
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "attachment_count": 0,
        "detail_count": 2,
        "detail_total": "100.00",
        "difference": "0.00",
    }
    assert client.get(f"/api/v1/invoices/{input_invoice.id}/details").status_code == 409


@pytest.mark.parametrize("field", ["amount", "item_name"])
def test_detail_update_rejects_explicit_null(invoice_api, field):
    _, client, _, _, invoice, _, _, _ = invoice_api
    detail_id = invoice.details[0].id
    response = client.put(
        f"/api/v1/invoices/{invoice.id}/details/{detail_id}", json={field: None}
    )
    assert response.status_code == 422, response.text


def test_source_lifecycle_delete_cascades_approval_form(invoice_api):
    db, _, _, users, invoice, _, _, _ = invoice_api
    db.add(ApprovalForm(
        form_type=ContractType.INVOICE,
        invoice_id=invoice.id,
        created_by=users["reviewer"].id,
    ))
    db.commit()
    remove_period_invoices(
        db,
        scenic_id=invoice.scenic_id,
        source_kind=invoice.source_kind,
        period_key=invoice.period_key,
    )
    db.commit()
    assert db.scalar(select(func.count()).select_from(ApprovalForm)) == 0
