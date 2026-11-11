from datetime import date

from sqlalchemy import select

from app.core.enums import ContractStatus, ContractType, InvoiceDirection, InvoiceSourceKind
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.fund import FundTransaction
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink
from app.services.historical_contract_links import backfill_historical_contract_links
from test_fund_integrity import ledger  # noqa: F401


def output(db, contract, period="p", **changes):
    values = dict(invoice_title="Printed", contract_no=contract.contract_no,
                  direction=InvoiceDirection.OUTPUT, source_kind=InvoiceSourceKind.TICKET,
                  scenic_id="s", period_key=period, generated_by_source=True, amount=100)
    db.add(row := Invoice(**{**values, **changes}))
    db.flush()
    return row


def test_dryrun_apply_idempotent_preserves_snapshots_and_funds(ledger):
    db, _, actor, contract, _ = ledger
    form = ApprovalForm(form_type=ContractType.BUSINESS, contract_no=contract.contract_no,
                        customer_name="Printed old customer", created_by=actor.id)
    db.add(form)
    invoice = output(db, contract)
    fund = FundTransaction(direction="increase", category="customer_payment", amount=20,
                           occurred_on=date(2020, 1, 1), created_by=actor.id)
    db.add(fund)
    db.commit()
    selectors = {("s", "ticket", "p"): actor.id}
    report = backfill_historical_contract_links(db, period_selectors=selectors)
    assert report["counts"] == {"approval_candidates": 1, "invoice_candidates": 1, "period_candidates": 1}
    assert form.contract_id is None and invoice.contract_id is None
    assert db.scalar(select(LedgerContractLink)) is None
    report = backfill_historical_contract_links(db, apply=True, period_selectors=selectors)
    db.commit()
    assert report["counts"]["period_applied"] == 1
    db.refresh(form)
    db.refresh(invoice)
    db.refresh(fund)
    assert form.contract_id == invoice.contract_id == contract.id
    assert form.contract_no == invoice.contract_no == "EXACT-1"
    assert form.customer_name == "Printed old customer" and invoice.invoice_title == "Printed"
    assert fund.contract_id is None and fund.approval_form_id is None and fund.execution_task_id is None
    assert fund.amount == 20 and fund.occurred_on == date(2020, 1, 1)
    again = backfill_historical_contract_links(db, apply=True, period_selectors=selectors)
    assert not again["counts"]
    assert again["skips"]["period_already_linked"] == 1


def test_exact_number_only_nonnull_never_overwritten_and_unresolved_reported(ledger):
    db, _, actor, contract, _ = ledger
    missing = ApprovalForm(form_type=ContractType.BUSINESS, contract_no="UNKNOWN", created_by=actor.id)
    spaces = ApprovalForm(form_type=ContractType.BUSINESS, contract_no=" EXACT-1 ", created_by=actor.id)
    pinned = ApprovalForm(form_type=ContractType.BUSINESS, contract_no="DIFFERENT", contract_id=contract.id, created_by=actor.id)
    db.add_all([missing, spaces, pinned])
    db.commit()
    report = backfill_historical_contract_links(db, apply=True)
    assert report["skips"]["approval_snapshot_not_unique"] == 2
    assert set(report["unresolved_approval_ids"]) == {missing.id, spaces.id}
    assert pinned.contract_id == contract.id and pinned.contract_no == "DIFFERENT"
    assert missing.contract_id is None and spaces.contract_id is None


def test_periods_require_eligible_matching_contract_and_explicit_selector_evidence(ledger):
    db, _, actor, contract, _ = ledger
    good = output(db, contract, "good")
    output(db, contract, "other-scenic", scenic_id="other")
    output(db, contract, "no-source", generated_by_source=False)
    output(db, contract, "conflict")
    output(db, contract, "snapshot-conflict", contract_id=contract.id, contract_no="different")
    db.add(LedgerContractLink(scenic_id="s", source_kind=InvoiceSourceKind.TICKET,
                              period_key="conflict", contract_id=contract.id,
                              contract_no_snapshot="old-snapshot", selected_by=actor.id))
    db.commit()
    report = backfill_historical_contract_links(db, apply=True)
    assert report["skips"]["period_missing_selector_provenance"] == 1
    assert report["skips"]["period_ineligible_contract"] == 2
    assert report["skips"]["period_conflict"] == 1
    assert report["skips"]["period_missing_source_provenance"] == 1
    assert good.contract_id == contract.id
    assert len(db.scalars(select(LedgerContractLink)).all()) == 1
    for status, scopes in ((ContractStatus.DRAFT, ["ticket"]), (ContractStatus.APPROVED, ["hotel"])):
        contract.status, contract.business_scopes = status, scopes
        db.commit()
        report = backfill_historical_contract_links(db, period_selectors={("s", "ticket", "good"): actor.id})
        assert not report["counts"]
        assert report["skips"]["period_ineligible_contract"] >= 1


def test_conflicting_period_input_and_ambiguous_snapshot_never_create_links(ledger, monkeypatch):
    db, _, actor, contract, _ = ledger
    invoice = output(db, contract)
    input_invoice = Invoice(invoice_title="Input", direction=InvoiceDirection.INPUT,
                            source_kind=InvoiceSourceKind.TICKET, scenic_id="s", period_key="p",
                            contract_no="OTHER", contract_id=contract.id)
    form = ApprovalForm(form_type=ContractType.BUSINESS, contract_no=contract.contract_no, created_by=actor.id)
    db.add_all([input_invoice, form])
    db.commit()
    report = backfill_historical_contract_links(db, apply=True,
        period_selectors={("s", "ticket", "p"): actor.id})
    assert report["skips"]["period_conflict"] == 1
    assert db.scalar(select(LedgerContractLink)) is None
    # The production model enforces unique numbers. Simulate a legacy/import
    # dataset with duplicate matches so the helper still refuses ambiguity.
    original = db.scalars
    def legacy_contracts(statement, *args, **kwargs):
        if statement.column_descriptions[0].get("entity") is Contract:
            return iter([contract, contract])
        return original(statement, *args, **kwargs)
    form.contract_id = None
    invoice.contract_id = None
    db.flush()
    monkeypatch.setattr(db, "scalars", legacy_contracts)
    report = backfill_historical_contract_links(db, apply=True)
    assert report["skips"]["approval_snapshot_not_unique"] >= 1
    assert report["skips"]["invoice_snapshot_not_unique"] >= 1
    assert form.contract_id is None and invoice.contract_id is None
