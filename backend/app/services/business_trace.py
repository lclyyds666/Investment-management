"""Read an explicitly linked scenic period graph, then project permitted nodes.

Contracts are terminal nodes: sharing a contract never expands a period into
another period's invoices, payment forms or funds. Free-text snapshots and
foreign keys on visible nodes are deliberately excluded from the projection.
"""
from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.enums import InvoiceSourceKind
from app.models.approval_form import ApprovalForm
from app.models.cash_execution import CashExecutionTask, InvoiceFundAllocation
from app.models.contract import Contract
from app.models.fund import FundTransaction
from app.models.hotel_ledger import HotelLedger
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink
from app.models.ticket_ledger import TicketLedger
from app.schemas.business_trace import (
    BusinessTraceOut, TraceAllocationOut, TraceApprovalOut, TraceContractOut,
    TraceExecutionTaskOut, TraceFundOut, TraceInvoiceOut, TraceLedgerOut, TracePeriodOut,
)
from app.services.assignment_permissions import PermissionContext, active_assignments, has_permission
from app.services.invoice_generation import hotel_period_key, ticket_period_key
from app.services.legal_record_scope import can_access_contract, legal_record_scope


SUPPLY_CONTEXT = PermissionContext(company_code='supplymanagement')


def _operation_access(db, user):
    if not has_permission(db, user, 'supply.operation.view', SUPPLY_CONTEXT):
        raise HTTPException(status_code=403, detail='权限不足')


def list_trace_periods(db, scenic_id, current_user, year=None):
    _operation_access(db, current_user)
    periods = {}
    for kind, model, key_fn in (
        (InvoiceSourceKind.TICKET, TicketLedger, ticket_period_key),
        (InvoiceSourceKind.HOTEL, HotelLedger, hotel_period_key),
    ):
        for row in db.scalars(select(model).where(model.scenic_id == scenic_id)):
            period_date = row.period_end or row.period_start
            if year is not None and (period_date is None or period_date.year != year):
                continue
            key = key_fn(row)
            entry = periods.setdefault((kind, key), TracePeriodOut(
                scenic_id=scenic_id, source_kind=kind, period_key=key, period_end=period_date,
            ))
            if period_date and (entry.period_end is None or period_date > entry.period_end):
                entry.period_end = period_date
    return sorted(periods.values(), key=lambda x: (x.source_kind.value, x.period_key))


def _contract_visible(db, user, contract, scope):
    # Match legal module permission contexts as well as its record predicate.
    contexts = [PermissionContext(company_code='investment',
        participant_ids=frozenset({user.id}), assigned_user_id=user.id)]
    contexts.extend(PermissionContext(
        company_code=a.organization.company_code,
        department_code=a.organization.code if a.organization.organization_type.value == 'department' else None,
        participant_ids=frozenset({user.id}), assigned_user_id=user.id,
    ) for a in active_assignments(db, user.id))
    return any(has_permission(db, user, 'investment.legal.contracts.view', c) for c in contexts) and can_access_contract(db, contract, scope)


def build_business_trace(db, scenic_id, source_kind, period_key, current_user):
    _operation_access(db, current_user)
    source_kind = InvoiceSourceKind(source_kind)
    model, key_fn = ((TicketLedger, ticket_period_key) if source_kind == InvoiceSourceKind.TICKET
                     else (HotelLedger, hotel_period_key))
    ledger = [r for r in db.scalars(select(model).where(model.scenic_id == scenic_id))
              if key_fn(r) == period_key]
    invoices = list(db.scalars(select(Invoice).where(
        Invoice.scenic_id == scenic_id, Invoice.source_kind == source_kind,
        Invoice.period_key == period_key,
    ).order_by(Invoice.id)))
    invoice_ids = {r.id for r in invoices}
    allocations = list(db.scalars(select(InvoiceFundAllocation).where(
        InvoiceFundAllocation.invoice_id.in_(invoice_ids)
    ).order_by(InvoiceFundAllocation.id)))
    # Only invoice sources establish a period on an approval form. A contract
    # alone has no period and cannot anchor a pending payment task here.
    forms = list(db.scalars(select(ApprovalForm).where(
        ApprovalForm.invoice_id.in_(invoice_ids),
        or_(ApprovalForm.scenic_id == scenic_id, ApprovalForm.scenic_id.is_(None), ApprovalForm.scenic_id == ''),
    ).order_by(ApprovalForm.id)))
    form_ids = {r.id for r in forms}
    tasks = list(db.scalars(select(CashExecutionTask).where(
        CashExecutionTask.scenic_id == scenic_id,
        or_(CashExecutionTask.invoice_id.in_(invoice_ids), CashExecutionTask.approval_form_id.in_(form_ids)),
    ).order_by(CashExecutionTask.id)))
    funds = list(db.scalars(select(FundTransaction).where(
        or_(FundTransaction.scenic_id == scenic_id, FundTransaction.scenic_id.is_(None), FundTransaction.scenic_id == ''),
        or_(FundTransaction.id.in_({a.fund_transaction_id for a in allocations}),
            FundTransaction.invoice_id.in_(invoice_ids),
            FundTransaction.execution_task_id.in_({t.id for t in tasks}),
            FundTransaction.approval_form_id.in_(form_ids)),
    ).order_by(FundTransaction.id)))
    # Include the exact source of an allocated fund, but do not traverse its
    # contract to unrelated business records.
    linked_task_ids = {f.execution_task_id for f in funds if f.execution_task_id}
    tasks = list(db.scalars(select(CashExecutionTask).where(
        CashExecutionTask.scenic_id == scenic_id,
        CashExecutionTask.id.in_({t.id for t in tasks} | linked_task_ids),
    ).order_by(CashExecutionTask.id)))
    linked_form_ids = {r.approval_form_id for r in [*tasks, *funds] if r.approval_form_id}
    forms = list(db.scalars(select(ApprovalForm).where(
        ApprovalForm.id.in_(form_ids | linked_form_ids),
        or_(ApprovalForm.scenic_id == scenic_id, ApprovalForm.scenic_id.is_(None), ApprovalForm.scenic_id == ''),
    ).order_by(ApprovalForm.id)))
    contract_ids = {r.contract_id for r in [*invoices, *tasks, *funds, *forms] if r.contract_id}
    contract_ids.update(db.scalars(select(LedgerContractLink.contract_id).where(
        LedgerContractLink.scenic_id == scenic_id, LedgerContractLink.source_kind == source_kind,
        LedgerContractLink.period_key == period_key,
    )))
    contracts = list(db.scalars(select(Contract).where(Contract.id.in_(contract_ids)).order_by(Contract.id)))
    scope = legal_record_scope(db, current_user)
    scope_contract_ids = {c.id for c in contracts if can_access_contract(db, c, scope)}
    visible = {}
    restricted = 0
    for name, code, rows in (
        ('invoices', 'supply.invoice.view', invoices),
        ('funds', 'supply.finance.view', funds),
        ('execution_tasks', 'supply.finance.view', tasks),
        ('approvals', 'supply.approval.view', forms),
    ):
        visible[name] = [r for r in rows if r.contract_id is None or r.contract_id in scope_contract_ids] if has_permission(db, current_user, code, SUPPLY_CONTEXT) else []
        restricted += len(rows) - len(visible[name])
    visible['contracts'] = [c for c in contracts if _contract_visible(db, current_user, c, scope)]
    restricted += len(contracts) - len(visible['contracts'])
    visible_invoice_ids = {i.id for i in visible['invoices']}
    visible_fund_ids = {f.id for f in visible['funds']}
    visible_allocations = [a for a in allocations if a.invoice_id in visible_invoice_ids
                           and a.fund_transaction_id in visible_fund_ids]
    restricted += len(allocations) - len(visible_allocations)

    def project(schema, rows):
        return [schema(**{key: getattr(row, key) for key in schema.model_fields}) for row in rows]

    return BusinessTraceOut(
        scenic_id=scenic_id, source_kind=source_kind, period_key=period_key,
        ledger_rows=project(TraceLedgerOut, ledger),
        invoices=project(TraceInvoiceOut, visible['invoices']),
        allocations=project(TraceAllocationOut, visible_allocations),
        funds=project(TraceFundOut, visible['funds']),
        execution_tasks=project(TraceExecutionTaskOut, visible['execution_tasks']),
        approvals=project(TraceApprovalOut, visible['approvals']),
        contracts=project(TraceContractOut, visible['contracts']),
        restricted_count=restricted,
    )
