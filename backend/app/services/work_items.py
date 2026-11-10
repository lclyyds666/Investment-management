"""Read-only, permission-filtered operational exceptions; amounts remain in yuan."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.core.enums import ContractStatus, ContractType, InvoiceDirection, InvoiceStatus
from app.models.approval_form import ApprovalForm
from app.models.cash_execution import CashExecutionTask, InvoiceFundAllocation
from app.models.contract import Contract
from app.models.fund import FundTransaction
from app.models.invoice import Invoice
from app.models.ledger_contract import LedgerContractLink
from app.models.ticket_ledger import TicketLedger
from app.models.hotel_ledger import HotelLedger
from app.schemas.work_item import ContractClosureSummary, WorkItemOut
from app.services.assignment_permissions import PermissionContext, active_assignments, has_permission
from app.services.legal_record_scope import contract_access_predicate, legal_record_scope
from app.services.fund import maturity_state

ZERO = Decimal('0.00')
FUND_PATH = '/supplymanagement/finance/fund'
INVOICE_PATH = '/supplymanagement/finance/invoice'
CONTRACT_PATH = '/investment/legal-risk/contracts'


def permitted(db, user, code):
    contexts = [PermissionContext(company_code='supplymanagement')]
    if code.startswith('investment.'):
        contexts.append(PermissionContext(company_code='investment', assigned_user_id=user.id,
                                          participant_ids=frozenset({user.id})))
        contexts.extend(PermissionContext(company_code=a.organization.company_code,
                                          department_code=(a.organization.code if a.organization.organization_type.value == 'department' else None),
                                          assigned_user_id=user.id, participant_ids=frozenset({user.id}))
                        for a in active_assignments(db, user.id))
    return any(has_permission(db, user, code, context) for context in contexts)


def _total(rows):
    return sum((Decimal(row.amount or 0) for row in rows), ZERO)


def build_contract_closure_summary(db, contract_id, current_user):
    """Caller must enforce contract visibility; each financial field has its own gate."""
    result = ContractClosureSummary()
    finance = permitted(db, current_user, 'supply.finance.view')
    invoice = permitted(db, current_user, 'supply.invoice.view')
    if permitted(db, current_user, 'supply.approval.view'):
        result.approved_payment = _total(db.scalars(select(ApprovalForm).where(
            ApprovalForm.contract_id == contract_id, ApprovalForm.form_type == ContractType.PAYMENT,
            ApprovalForm.status == ContractStatus.APPROVED)).all())
    if finance:
        tasks = db.scalars(select(CashExecutionTask).where(
            CashExecutionTask.contract_id == contract_id, CashExecutionTask.direction == 'outflow',
            CashExecutionTask.status.in_(['pending', 'partial']))).all()
        funds = db.scalars(select(FundTransaction).where(FundTransaction.contract_id == contract_id)).all()
        result.pending_payment = sum((max(t.planned_amount - t.executed_amount, ZERO) for t in tasks), ZERO)
        result.actual_payment = _total([f for f in funds if f.direction == 'usage' and f.category == 'business_payment'])
        result.actual_receipt = _total([f for f in funds if f.direction == 'increase' and f.category == 'customer_payment'])
    if invoice:
        result.output_invoiced = _total(db.scalars(select(Invoice).where(
            Invoice.contract_id == contract_id, Invoice.direction == InvoiceDirection.OUTPUT,
            Invoice.status == InvoiceStatus.ISSUED)).all())
    if finance and invoice:
        paid_funds = [f for f in funds if f.direction == 'usage' and f.category == 'business_payment']
        allocated = db.scalars(select(InvoiceFundAllocation).join(Invoice).where(
            Invoice.direction == InvoiceDirection.INPUT,
            InvoiceFundAllocation.fund_transaction_id.in_([f.id for f in paid_funds]))).all()
        result.missing_input_invoice = max(result.actual_payment - _total(allocated), ZERO)
    return result


def build_work_items(db, current_user):
    finance = permitted(db, current_user, 'supply.finance.view')
    invoice_permission = permitted(db, current_user, 'supply.invoice.view')
    contract_permission = permitted(db, current_user, 'investment.legal.contracts.view')
    scope_contracts = {c.id: c for c in db.scalars(select(Contract).where(
        contract_access_predicate(legal_record_scope(db, current_user)))).all()}
    visible = scope_contracts if contract_permission else {}
    items = []

    def add(kind, row, amount, path, query=None, status='pending', due=None, priority=2):
        cid = getattr(row, 'contract_id', None)
        # A user with contract access must also satisfy the existing row visibility scope.
        if cid is not None and cid not in scope_contracts:
            return
        contract = visible.get(cid)
        items.append(WorkItemOut(id=f'{kind}:{row.id}', item_type=kind,
            scenic_id=getattr(row, 'scenic_id', None), contract_id=cid if contract else None,
            contract_name=contract.title if contract else None, amount=amount, status=status,
            due_date=due, priority=priority, target_path=path, target_query=query or {}))

    if permitted(db, current_user, 'supply.scenic.view'):
        links = {(r.scenic_id, r.source_kind.value, r.period_key) for r in db.scalars(select(LedgerContractLink))}
        for model, kind in [(TicketLedger, 'ticket'), (HotelLedger, 'hotel')]:
            seen = set()
            for row in db.scalars(select(model).order_by(model.id)):
                key = row.source_file or row.detail_name or row.period_text or row.check_date_text or 'NA'
                identity = (row.scenic_id, kind, key)
                if identity in seen or identity in links:
                    continue
                seen.add(identity)
                add('missing_contract', row, ZERO, f'/supplymanagement/cultural-tourism/{row.scenic_id}',
                    {'source_kind': kind, 'period_key': key}, status='未关联合同')
    if not (finance or invoice_permission or contract_permission):
        return items
    funds = db.scalars(select(FundTransaction)).all() if finance or invoice_permission else []
    invoices = db.scalars(select(Invoice)).all() if invoice_permission else []
    allocations = db.scalars(select(InvoiceFundAllocation)).all() if finance or invoice_permission else []
    by_fund, by_invoice = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    input_by_fund = defaultdict(lambda: ZERO)
    input_ids = set(db.scalars(select(Invoice.id).where(Invoice.direction == InvoiceDirection.INPUT)))
    for allocation in allocations:
        by_fund[allocation.fund_transaction_id] += allocation.amount
        by_invoice[allocation.invoice_id] += allocation.amount
        if allocation.invoice_id in input_ids:
            input_by_fund[allocation.fund_transaction_id] += allocation.amount
    if finance:
        for task in db.scalars(select(CashExecutionTask).where(CashExecutionTask.status.in_(['pending', 'partial']))):
            remaining = max(task.planned_amount - task.executed_amount, ZERO)
            if remaining:
                add('cash_execution' if task.direction == 'outflow' else 'receipt_confirmation', task,
                    remaining, FUND_PATH, {'tab': 'execution', 'task_id': str(task.id)}, status=task.status)
        for fund in funds:
            if fund.category in {'business_payment', 'customer_payment'}:
                remaining = max(fund.amount - by_fund[fund.id], ZERO)
                if remaining:
                    add('fund_unallocated', fund, remaining, FUND_PATH,
                        {'fund_id': str(fund.id), 'unallocated_only': 'true'})
            state = maturity_state(fund, date.today())
            if state in {'overdue', 'due_soon'}:
                add(f'fund_{state}', fund, fund.amount, FUND_PATH,
                    {'fund_id': str(fund.id), 'maturity_status': state}, due=fund.maturity_date,
                    status=state, priority=0 if state == 'overdue' else 1)
    if invoice_permission:
        missing_by_contract = {}
        for fund in funds:
            if fund.direction == 'usage' and fund.category == 'business_payment':
                remaining = max(fund.amount - input_by_fund[fund.id], ZERO)
                if remaining:
                    if fund.contract_id is not None:
                        previous = missing_by_contract.get(fund.contract_id)
                        missing_by_contract[fund.contract_id] = (fund, remaining + (previous[1] if previous else ZERO))
                        continue
                    query = {'direction': 'input'}
                    if fund.scenic_id:
                        query['scenic_id'] = fund.scenic_id
                    add('input_invoice_missing', fund, remaining, INVOICE_PATH, query, status='未补进项发票')
        for cid, (fund, remaining) in missing_by_contract.items():
            query = {'direction': 'input'}
            if cid in visible:
                query['contract_id'] = str(cid)
            if fund.scenic_id:
                query['scenic_id'] = fund.scenic_id
            add('input_invoice_missing', fund, remaining, INVOICE_PATH, query, status='未补进项发票')
        for row in invoices:
            remaining = max(row.amount - by_invoice[row.id], ZERO)
            if remaining:
                add('invoice_unallocated', row, remaining, INVOICE_PATH,
                    {'invoice_id': str(row.id), 'direction': row.direction.value if row.direction else 'input'},
                    status='未核销')
    if contract_permission:
        for contract in visible.values():
            summary = build_contract_closure_summary(db, contract.id, current_user)
            if not contract.amount and (summary.approved_payment is not None or summary.output_invoiced is not None):
                proxy = type('ContractItem', (), {'id': contract.id, 'contract_id': contract.id,
                                                 'scenic_id': contract.scenic_id})()
                add('contract_amount_exceeded', proxy, ZERO, CONTRACT_PATH,
                    {'contract_id': str(contract.id)}, status='未配置控制金额', priority=1)
                continue
            for label, total in [('已审批付款', summary.approved_payment), ('销项发票', summary.output_invoiced)]:
                if total is not None and total > contract.amount:
                    proxy = type('ContractItem', (), {'id': f'{contract.id}:{label}', 'contract_id': contract.id,
                                                     'scenic_id': contract.scenic_id})()
                    add('contract_amount_exceeded', proxy, total - contract.amount,
                        CONTRACT_PATH, {'contract_id': str(contract.id)},
                        status=f'{label}超额', priority=1)
    return sorted(items, key=lambda item: (item.priority, item.due_date or date.max, item.item_type, item.id))
