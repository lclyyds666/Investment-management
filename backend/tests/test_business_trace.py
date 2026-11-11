import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.init_db  # noqa: F401
from app.db.base import Base
from app.core.enums import InvoiceDirection, InvoiceSourceKind, ContractType
from app.models.ticket_ledger import TicketLedger
from app.models.invoice import Invoice
from app.models.contract import Contract
from app.models.approval_form import ApprovalForm
from app.models.cash_execution import CashExecutionTask, InvoiceFundAllocation
from app.models.ledger_contract import LedgerContractLink
from app.models.hotel_ledger import HotelLedger
from app.models.fund import FundTransaction
from app.services.business_trace import build_business_trace, list_trace_periods


class BusinessTraceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = SimpleNamespace(id=1, is_superuser=True, is_active=True)
        self.contract = Contract(contract_no='SECRET-CONTRACT', title='Secret title', created_by=1)
        self.db.add(self.contract)
        self.db.flush()
        for scenic, period in [('a', 'P1'), ('a', 'P2'), ('b', 'P1')]:
            self.db.add(TicketLedger(scenic_id=scenic, source_file=period, platform='平台',
                                     confirmed=True, period_end=date(2026, 1, 31)))
        self.invoice = Invoice(invoice_title='SECRET-CUSTOMER', contract_id=self.contract.id,
            source_kind=InvoiceSourceKind.TICKET, scenic_id='a', period_key='P1',
            direction=InvoiceDirection.OUTPUT, amount=100)
        self.other = Invoice(invoice_title='other period', contract_id=self.contract.id,
            source_kind=InvoiceSourceKind.TICKET, scenic_id='a', period_key='P2',
            direction=InvoiceDirection.OUTPUT, amount=200)
        self.db.add_all([self.invoice, self.other])
        self.db.flush()
        self.form = ApprovalForm(form_type=ContractType.INVOICE, invoice_id=self.invoice.id,
                                 contract_id=self.contract.id, scenic_id='a', created_by=1)
        self.db.add(self.form)
        self.db.flush()
        self.task = CashExecutionTask(direction='inflow', invoice_id=self.invoice.id,
            scenic_id='a', contract_id=self.contract.id, planned_amount=100)
        self.db.add(self.task)
        self.db.flush()
        self.fund = FundTransaction(direction='increase', category='customer_payment', amount=30,
            occurred_on=date(2026, 1, 31), scenic_id='a', execution_task_id=self.task.id,
            approval_form_id=self.form.id, contract_id=self.contract.id,
            counterparty='SECRET-CUSTOMER', summary='SECRET-CONTRACT')
        self.db.add(self.fund)
        self.db.flush()
        self.db.add(InvoiceFundAllocation(invoice_id=self.invoice.id,
            fund_transaction_id=self.fund.id, amount=30, allocated_by=1))
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def trace(self):
        return build_business_trace(self.db, 'a', InvoiceSourceKind.TICKET, 'P1', self.user)

    def test_exact_period_chain_and_typed_minimal_payload(self):
        trace = self.trace()
        self.assertEqual([x.id for x in trace.invoices], [self.invoice.id])
        self.assertEqual([x.id for x in trace.contracts], [self.contract.id])
        self.assertEqual([x.id for x in trace.funds], [self.fund.id])
        self.assertEqual({x.scenic_id for x in trace.ledger_rows}, {'a'})
        self.assertEqual(len(trace.ledger_rows), 1)
        self.assertNotIn('SECRET-CUSTOMER', trace.model_dump_json())
        self.assertEqual(trace.restricted_count, 0)

    def test_pending_task_without_fund_is_included_by_source(self):
        self.db.query(InvoiceFundAllocation).delete()
        self.db.delete(self.fund)
        self.db.flush()
        trace = self.trace()
        self.assertEqual([x.id for x in trace.execution_tasks], [self.task.id])
        self.assertEqual(trace.funds, [])

    def test_module_redaction_does_not_leak_other_nodes_or_allocation_endpoints(self):
        def allowed(db, user, code, context=None):
            return code in {'supply.operation.view', 'supply.finance.view'}
        with patch('app.services.business_trace.has_permission', side_effect=allowed):
            trace = self.trace()
        self.assertEqual(trace.invoices, [])
        self.assertEqual(trace.allocations, [])
        self.assertEqual(trace.approvals, [])
        self.assertEqual(trace.contracts, [])
        self.assertEqual(trace.restricted_count, 4)  # invoice, allocation, approval, contract
        self.assertNotIn('SECRET', trace.model_dump_json())
        self.assertNotIn('invoice_id', trace.model_dump_json())

    def test_contract_scope_is_required_in_addition_to_permission(self):
        with patch('app.services.business_trace.can_access_contract', return_value=False):
            trace = self.trace()
        self.assertEqual(trace.contracts, [])
        self.assertEqual(trace.restricted_count, 6)
        self.assertEqual(trace.invoices, [])
        self.assertEqual(trace.funds, [])
        self.assertEqual(trace.execution_tasks, [])
        self.assertEqual(trace.approvals, [])
        self.assertEqual(trace.allocations, [])
        self.assertNotIn('SECRET', trace.model_dump_json())

    def test_real_legal_record_scope_hides_financial_nodes_even_with_module_permissions(self):
        self.user = SimpleNamespace(id=99, is_superuser=False, is_active=True)
        with patch('app.services.business_trace.has_permission', return_value=True):
            trace = self.trace()
        self.assertEqual(trace.contracts, [])
        self.assertEqual(trace.invoices, [])
        self.assertEqual(trace.funds, [])
        self.assertEqual(trace.restricted_count, 6)
        self.assertEqual(len(trace.ledger_rows), 1)

    def test_operation_permission_is_required_before_any_trace(self):
        from fastapi import HTTPException
        with patch('app.services.business_trace.has_permission', return_value=False):
            with self.assertRaises(HTTPException) as result:
                self.trace()
        self.assertEqual(result.exception.status_code, 403)

    def test_period_choices_use_canonical_source_key_and_valid_year(self):
        self.db.add(TicketLedger(scenic_id='a', source_file='unknown', confirmed=True))
        self.db.flush()
        periods = list_trace_periods(self.db, 'a', self.user, year=2026)
        self.assertEqual({x.period_key for x in periods}, {'P1', 'P2'})
        self.assertEqual(list_trace_periods(self.db, 'a', self.user, year=2025), [])

    def test_contract_is_terminal_and_unlinked_legacy_records_are_not_guessed(self):
        unrelated = ApprovalForm(form_type=ContractType.PAYMENT, scenic_id='a',
            contract_id=self.contract.id, contract_no=self.contract.contract_no, created_by=1)
        legacy = Invoice(invoice_title='legacy', scenic_id='a', contract_no=self.contract.contract_no)
        self.db.add_all([unrelated, legacy])
        self.db.flush()
        self.db.add(CashExecutionTask(direction='outflow', approval_form_id=unrelated.id,
            scenic_id='a', contract_id=self.contract.id, planned_amount=200))
        self.db.flush()
        trace = self.trace()
        self.assertEqual([x.id for x in trace.approvals], [self.form.id])
        self.assertEqual([x.id for x in trace.execution_tasks], [self.task.id])
        self.assertEqual([x.id for x in trace.invoices], [self.invoice.id])

    def test_hotel_and_other_scenic_do_not_mix_with_ticket_period(self):
        self.db.add(HotelLedger(scenic_id='a', source_file='P1', platform='hotel', confirmed=True))
        self.db.flush()
        result = build_business_trace(self.db, 'a', InvoiceSourceKind.HOTEL, 'P1', self.user)
        self.assertEqual(len(result.ledger_rows), 1)
        self.assertEqual(result.ledger_rows[0].platform, 'hotel')
        self.assertEqual(result.invoices, [])
        self.assertEqual(result.contracts, [])

    def test_ledger_link_only_returns_its_terminal_contract(self):
        self.db.add(LedgerContractLink(scenic_id='a', source_kind=InvoiceSourceKind.TICKET,
            period_key='P3', contract_id=self.contract.id,
            contract_no_snapshot=self.contract.contract_no, selected_by=1))
        self.db.flush()
        result = build_business_trace(self.db, 'a', InvoiceSourceKind.TICKET, 'P3', self.user)
        self.assertEqual([x.id for x in result.contracts], [self.contract.id])
        self.assertEqual(result.invoices, [])
        self.assertEqual(result.execution_tasks, [])
        self.assertEqual(result.approvals, [])

    def test_finance_denial_hides_tasks_funds_and_allocations(self):
        def allowed(db, user, code, context=None):
            return code != 'supply.finance.view'
        with patch('app.services.business_trace.has_permission', side_effect=allowed):
            trace = self.trace()
        self.assertEqual(trace.execution_tasks, [])
        self.assertEqual(trace.funds, [])
        self.assertEqual(trace.allocations, [])
        self.assertEqual(trace.restricted_count, 3)

    def test_http_trace_schema_and_query_validation(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sqlalchemy.pool import StaticPool
        from app.api.v1.endpoints import operation
        from app.db.session import get_db

        # The HTTP client runs in a separate thread; use a shared connection.
        engine = create_engine('sqlite+pysqlite:///:memory:',
            connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(TicketLedger(scenic_id='api', source_file='original.xlsx', platform='API', confirmed=True))
            session.commit()

        def session_dependency():
            with Session(engine) as session:
                yield session

        app = FastAPI()
        app.include_router(operation.router, prefix='/operation')
        app.dependency_overrides[get_db] = session_dependency
        app.dependency_overrides[operation._operation_guard] = lambda: self.user
        with TestClient(app) as client:
            response = client.get('/operation/trace', params={
                'scenic_id': 'api', 'source_kind': 'ticket', 'period_key': 'original.xlsx'})
            self.assertEqual(response.status_code, 200)
            result = response.json()['data']
            self.assertEqual(result['ledger_rows'][0]['platform'], 'API')
            self.assertEqual(result['restricted_count'], 0)
            self.assertEqual(client.get('/operation/trace', params={
                'scenic_id': 'api', 'source_kind': 'unknown', 'period_key': 'P1'}).status_code, 422)
            self.assertEqual(client.get('/operation/trace-periods', params={
                'scenic_id': 'api', 'year': 10000}).status_code, 422)
        engine.dispose()


