from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.init_db  # noqa: F401
from app.api.deps import get_current_user
from app.core.enums import ContractStatus, ContractType, InvoiceDirection
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.fund import FundTransaction
from app.models.invoice import Invoice
from app.models.user import User
from app.services.cash_execution import ensure_payment_task, execute_task
from app.services.fund import FundIntegrityError, locked_fund, validate_fund_edit
from app.services.invoice_reconciliation import allocate


@pytest.fixture
def ledger():
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor = User(username="finance", hashed_password="x", is_superuser=True, is_active=True)
        db.add(actor)
        db.flush()
        contract = Contract(contract_no="EXACT-1", title="Contract", created_by=actor.id,
                            scenic_id="s", business_scopes=["ticket"], status=ContractStatus.APPROVED)
        db.add(contract)
        db.flush()
        form = ApprovalForm(form_type=ContractType.PAYMENT, status=ContractStatus.APPROVED,
                            contract_id=contract.id, scenic_id="s", created_by=actor.id, amount=100)
        db.add(form)
        db.commit()
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: actor
        with TestClient(app) as client:
            yield db, client, actor, contract, form
        app.dependency_overrides.clear()
    engine.dispose()


def historical(db, actor, **values):
    row = FundTransaction(direction="usage", category="business_payment", amount=100,
                          occurred_on=date(2020, 1, 1), created_by=actor.id, **values)
    db.add(row)
    db.commit()
    return row


def body(row, **changes):
    fields = ("direction", "category", "occurred_on", "counterparty", "summary",
              "maturity_date", "remark", "bank_reference")
    result = {key: getattr(row, key) for key in fields}
    result["occurred_on"] = row.occurred_on.isoformat()
    result["amount"] = str(row.amount)
    return {**result, **changes}


@pytest.mark.parametrize("direction,category", [("usage", "business_payment"), ("increase", "customer_payment")])
def test_direct_business_cash_and_conversion_blocked(ledger, direction, category):
    db, client, actor, _, _ = ledger
    payload = dict(direction=direction, category=category, amount="10", occurred_on="2026-01-01")
    assert client.post("/api/v1/funds", json=payload).status_code == 409
    allowed = {**payload, "category": "other"}
    response = client.post("/api/v1/funds", json=allowed)
    assert response.status_code == 200, response.text
    fund_id = response.json()["data"]["id"]
    assert client.put(f"/api/v1/funds/{fund_id}", json=payload).status_code == 409
    assert db.get(FundTransaction, fund_id).category == "other"


def test_execution_fund_cannot_desynchronize_task(ledger):
    db, client, actor, _, form = ledger
    task = ensure_payment_task(db, form)
    fund = execute_task(db, task.id, SimpleNamespace(amount=Decimal("40"), occurred_on=date(2026, 1, 1),
                        counterparty="supplier", summary="original", remark="", bank_reference="BANK"), actor.id)
    db.commit()
    for changes in ({"amount": "50"}, {"occurred_on": "2026-01-02"}, {"category": "expense"},
                    {"bank_reference": "CHANGED"}, {"counterparty": "other"},
                    {"direction": "increase", "category": "customer_payment"}):
        response = client.put(f"/api/v1/funds/{fund.id}", json=body(fund, **changes))
        assert response.status_code == 409, response.text
    assert client.delete(f"/api/v1/funds/{fund.id}").status_code == 409
    assert client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={"contract_id": form.contract_id}).status_code == 409
    response = client.put(f"/api/v1/funds/{fund.id}", json=body(fund, summary="corrected", remark="note"))
    assert response.status_code == 200, response.text
    db.refresh(task)
    db.refresh(fund)
    assert task.executed_amount == fund.amount == Decimal("40")
    assert task.status == "partial"
    assert fund.bank_reference == "BANK"
    assert fund.summary == "corrected"


def test_allocated_fund_financial_associations_and_delete_locked(ledger):
    db, client, actor, contract, _ = ledger
    fund = historical(db, actor, contract_id=contract.id, scenic_id="s")
    invoice = Invoice(invoice_title="Input", direction=InvoiceDirection.INPUT, amount=100,
                      contract_id=contract.id, scenic_id="s")
    db.add(invoice)
    db.flush()
    allocation = allocate(db, invoice.id, fund.id, "40", actor.id)
    db.commit()
    for changes in ({"amount": "120"}, {"category": "expense"}, {"direction": "increase", "category": "other"}):
        assert client.put(f"/api/v1/funds/{fund.id}", json=body(fund, **changes)).status_code == 409
    for changes in ({"contract_id": None}, {"scenic_id": "other"}):
        with pytest.raises(FundIntegrityError, match="unallocate"):
            validate_fund_edit(db, locked_fund(db, fund.id), changes)
    assert client.delete(f"/api/v1/funds/{fund.id}").status_code == 409
    assert client.put(f"/api/v1/funds/{fund.id}", json=body(fund, remark="note")).status_code == 200
    db.delete(allocation)
    db.commit()
    assert client.put(f"/api/v1/funds/{fund.id}", json=body(fund, amount="120")).status_code == 200
    assert client.delete(f"/api/v1/funds/{fund.id}").status_code == 200


def test_explicit_legacy_association_preserves_money_date_and_no_task(ledger):
    db, client, actor, contract, form = ledger
    fund = historical(db, actor)
    response = client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={
        "contract_id": contract.id, "approval_form_id": form.id})
    assert response.status_code == 200, response.text
    db.refresh(fund)
    assert fund.amount == Decimal("100") and fund.occurred_on == date(2020, 1, 1)
    assert fund.contract_id == contract.id and fund.approval_form_id == form.id
    assert fund.scenic_id == "s" and fund.execution_task_id is None


@pytest.mark.parametrize("invalid", ["draft_contract", "scenic", "draft_approval", "business_approval",
                                      "wrong_contract", "inflow_approval", "direction", "allocated"])
def test_invalid_legacy_associations_rejected(ledger, invalid):
    db, client, actor, contract, form = ledger
    fund = historical(db, actor)
    if invalid == "draft_contract": contract.status = ContractStatus.DRAFT
    if invalid == "scenic": fund.scenic_id = "different"
    if invalid == "draft_approval": form.status = ContractStatus.DRAFT
    if invalid == "business_approval": form.form_type = ContractType.BUSINESS
    if invalid == "wrong_contract": form.contract_id = None
    if invalid == "inflow_approval":
        fund.direction, fund.category = "increase", "customer_payment"
    if invalid == "direction": fund.direction = "increase"
    if invalid == "allocated":
        invoice = Invoice(invoice_title="Input", direction=InvoiceDirection.INPUT, amount=100)
        db.add(invoice)
        db.flush()
        allocate(db, invoice.id, fund.id, 10, actor.id)
    db.commit()
    response = client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={
        "contract_id": contract.id, "approval_form_id": form.id})
    assert response.status_code == 409, response.text
    db.refresh(fund)
    assert fund.contract_id is None and fund.approval_form_id is None


def test_legacy_association_requires_finance_edit(ledger, monkeypatch):
    db, client, actor, contract, _ = ledger
    fund = historical(db, actor)
    actor.is_superuser = False
    db.commit()
    monkeypatch.setattr("app.api.deps.has_permission", lambda *args: False)
    response = client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={"contract_id": contract.id})
    assert response.status_code == 403


def test_legacy_contract_selection_and_submission_respect_legal_scope(ledger, monkeypatch):
    db, client, actor, contract, _ = ledger
    fund = historical(db, actor)
    outsider = User(username="outside", hashed_password="x")
    db.add(outsider)
    db.flush()
    hidden = Contract(contract_no="HIDDEN", title="Hidden", scenic_id="s", business_scopes=["ticket"],
                      created_by=outsider.id, company_code="zhanwei", organization_code="zhanwei",
                      status=ContractStatus.APPROVED)
    db.add(hidden)
    actor.is_superuser = False
    db.commit()
    monkeypatch.setattr("app.api.deps.has_permission", lambda *args: True)
    response = client.get("/api/v1/funds/legacy-contracts")
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["data"]] == [contract.id]
    hidden_response = client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={"contract_id": hidden.id})
    missing_response = client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={"contract_id": 999999})
    assert hidden_response.status_code == missing_response.status_code == 409
    assert hidden_response.json() == missing_response.json()
    assert client.post(f"/api/v1/funds/{fund.id}/legacy-association", json={"contract_id": contract.id}).status_code == 200


def test_mutation_guard_uses_current_locking_reads(ledger, monkeypatch):
    db, _, actor, _, _ = ledger
    fund = historical(db, actor)
    statements = []
    original = db.execute
    def capture(statement, *args, **kwargs):
        statements.append(str(statement.compile(dialect=mysql.dialect())))
        return original(statement, *args, **kwargs)
    monkeypatch.setattr(db, "execute", capture)
    # scalar/scalars use internal execution on modern SQLAlchemy; capture their inputs too.
    original_scalar, original_scalars = db.scalar, db.scalars
    monkeypatch.setattr(db, "scalar", lambda stmt, *a, **kw: (statements.append(str(stmt.compile(dialect=mysql.dialect()))), original_scalar(stmt, *a, **kw))[1])
    monkeypatch.setattr(db, "scalars", lambda stmt, *a, **kw: (statements.append(str(stmt.compile(dialect=mysql.dialect()))), original_scalars(stmt, *a, **kw))[1])
    locked = locked_fund(db, fund.id)
    validate_fund_edit(db, locked, {"amount": Decimal("200")})
    assert any("biz_fund_transaction" in sql and "FOR UPDATE" in sql for sql in statements)
    assert any("biz_invoice_fund_allocation" in sql and "FOR UPDATE" in sql for sql in statements)
