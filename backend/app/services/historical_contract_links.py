"""Conservative, opt-in historical associations; never touches fund records.

Caller owns commit/rollback. Dry run is the default and performs no mutations.
Period selectors must be supplied from reviewed historical evidence, never inferred
from the operator, uploader or approval author.
"""
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ContractStatus, InvoiceDirection
from app.models.approval_form import ApprovalForm
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink
from app.models.user import User


def backfill_historical_contract_links(
    db: Session, *, apply: bool = False,
    period_selectors: dict[tuple[str, str, str], int] | None = None,
) -> dict:
    """Return candidate/applied counts and reasons, preserving printed snapshots.

    period_selectors maps (scenic_id, source_kind, period_key) to an evidenced
    historical selector's user ID. Without it period links are reported/skipped.
    Locks make apply safe with ordinary concurrent edits; run during maintenance
    to avoid a new period selection racing the unique period constraint.
    """
    counts = Counter()
    skips = Counter()
    unresolved = []
    contracts = defaultdict(list)
    for contract in db.scalars(select(Contract).with_for_update()):
        contracts[contract.contract_no].append(contract)
    effective_invoice_contracts = {}
    for model, label in ((ApprovalForm, "approval"), (Invoice, "invoice")):
        for row in db.scalars(select(model).order_by(model.id).with_for_update()
                              .execution_options(populate_existing=True)):
            if row.contract_id is not None:
                if model is Invoice:
                    effective_invoice_contracts[row.id] = row.contract_id
                continue
            matches = contracts.get(row.contract_no, []) if row.contract_no else []
            if len(matches) != 1:
                skips[f"{label}_snapshot_not_unique"] += 1
                if model is ApprovalForm:
                    unresolved.append(row.id)
                continue
            contract = matches[0]
            counts[f"{label}_candidates"] += 1
            if apply:
                row.contract_id = contract.id
                counts[f"{label}_applied"] += 1
            if model is Invoice:
                effective_invoice_contracts[row.id] = contract.id

    existing = {(row.scenic_id, row.source_kind.value, row.period_key): row
                for row in db.scalars(select(LedgerContractLink).with_for_update())}
    outputs = defaultdict(list)
    for row in db.scalars(select(Invoice).where(Invoice.direction == InvoiceDirection.OUTPUT)
                          .with_for_update()):
        if row.source_kind and row.scenic_id and row.period_key and row.generated_by_source:
            outputs[(row.scenic_id, row.source_kind.value, row.period_key)].append(row)
        else:
            skips["period_missing_source_provenance"] += 1
    by_id = {row.id: row for group in contracts.values() for row in group}
    for key, rows in outputs.items():
        if len(rows) != 1:
            skips["period_ambiguous_output"] += 1
            continue
        invoice = rows[0]
        contract = by_id.get(effective_invoice_contracts.get(invoice.id))
        if (not contract or contract.status != ContractStatus.APPROVED
                or contract.scenic_id != key[0] or key[1] not in (contract.business_scopes or [])
                or invoice.contract_no != contract.contract_no):
            skips["period_ineligible_contract"] += 1
            continue
        peers = db.scalars(select(Invoice).where(
            Invoice.scenic_id == key[0], Invoice.source_kind == invoice.source_kind,
            Invoice.period_key == key[2],
        ).with_for_update()).all()
        if any((effective_invoice_contracts.get(peer.id) not in (None, contract.id))
               or (peer.contract_no and peer.contract_no != invoice.contract_no) for peer in peers):
            skips["period_conflict"] += 1
            continue
        if key in existing:
            prior = existing[key]
            skips["period_already_linked" if prior.contract_id == contract.id
                  and prior.contract_no_snapshot == invoice.contract_no else "period_conflict"] += 1
            continue
        selector = (period_selectors or {}).get(key)
        if selector is None or db.get(User, selector) is None:
            skips["period_missing_selector_provenance"] += 1
            continue
        counts["period_candidates"] += 1
        if apply:
            db.add(LedgerContractLink(
                scenic_id=key[0], source_kind=invoice.source_kind, period_key=key[2],
                contract_id=contract.id, contract_no_snapshot=invoice.contract_no,
                selected_by=selector,
            ))
            counts["period_applied"] += 1
    if apply:
        db.flush()
    return {"mode": "apply" if apply else "dry_run", "counts": dict(counts),
            "skips": dict(skips), "unresolved_approval_ids": unresolved}
