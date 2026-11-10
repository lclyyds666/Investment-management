import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import app.db.init_db  # noqa
from app.db.base import Base
from app.models.fund import FundTransaction
from app.models.invoice import Invoice
from app.models.cash_execution import CashExecutionTask, InvoiceFundAllocation
from app.models.contract import Contract
from app.models.approval_form import ApprovalForm
from app.models.ticket_ledger import TicketLedger
from app.core.enums import ContractStatus, ContractType, InvoiceDirection, InvoiceStatus
from app.services.work_items import build_work_items, build_contract_closure_summary
from app.services.legal_record_scope import LegalRecordScope
from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app


class WorkItemsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = SimpleNamespace(id=1, is_active=True, is_superuser=True)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_prepaid_amount_is_payment_minus_input_allocations(self):
        fund = FundTransaction(direction='usage', category='business_payment', amount=100,
                               occurred_on=date.today())
        invoice = Invoice(invoice_title='test', direction=InvoiceDirection.INPUT, amount=30)
        self.db.add_all([fund, invoice])
        self.db.flush()
        self.db.add(InvoiceFundAllocation(fund_transaction_id=fund.id, invoice_id=invoice.id,
                                         amount=30, allocated_by=1))
        self.db.flush()
        items = build_work_items(self.db, self.user)
        item = next(row for row in items if row.item_type == 'input_invoice_missing')
        self.assertEqual(item.amount, Decimal('70.00'))
        self.assertEqual(next(row for row in items if row.item_type == 'fund_unallocated').amount,
                         Decimal('70.00'))

    def test_user_without_invoice_permission_cannot_see_invoice_items(self):
        self.db.add(Invoice(invoice_title='test', direction=InvoiceDirection.INPUT, amount=100))
        self.db.flush()
        with patch('app.services.work_items.permitted', return_value=False):
            self.assertEqual(build_work_items(self.db, self.user), [])

    def contract(self, amount=100):
        contract = Contract(contract_no='C1', title='Secret contract', amount=amount,
                            created_by=99, scenic_id='test-scenic')
        self.db.add(contract)
        self.db.flush()
        return contract

    def test_all_types_and_deterministic_priority_order(self):
        contract = self.contract()
        form = ApprovalForm(form_type=ContractType.PAYMENT, amount=150,
                            status=ContractStatus.APPROVED, created_by=1, contract_id=contract.id)
        invoice = Invoice(invoice_title='output', amount=200, contract_id=contract.id,
                          direction=InvoiceDirection.OUTPUT, status=InvoiceStatus.ISSUED)
        self.db.add_all([form, invoice])
        self.db.flush()
        self.db.add_all([
            CashExecutionTask(direction='outflow', approval_form_id=form.id, contract_id=contract.id,
                              scenic_id='test-scenic', planned_amount=150, executed_amount=20),
            CashExecutionTask(direction='inflow', invoice_id=invoice.id, contract_id=contract.id,
                              scenic_id='test-scenic', planned_amount=200, executed_amount=0),
            FundTransaction(direction='usage', category='business_payment', amount=100,
                            contract_id=contract.id, occurred_on=date.today()),
            FundTransaction(direction='increase', category='bank_credit', amount=50,
                            occurred_on=date.today(), maturity_date=date.today() + timedelta(days=5)),
            FundTransaction(direction='increase', category='company_loan', amount=30,
                            occurred_on=date.today(), maturity_date=date.today() - timedelta(days=1)),
            TicketLedger(scenic_id='test-scenic', source_file='one.xlsx'),
            TicketLedger(scenic_id='test-scenic', source_file='one.xlsx'),
        ])
        self.db.flush()
        items = build_work_items(self.db, self.user)
        self.assertEqual({row.item_type for row in items}, {
            'missing_contract', 'cash_execution', 'receipt_confirmation', 'input_invoice_missing',
            'invoice_unallocated', 'fund_unallocated', 'contract_amount_exceeded', 'fund_due_soon', 'fund_overdue'})
        self.assertEqual(items[0].item_type, 'fund_overdue')
        self.assertEqual(len([row for row in items if row.item_type == 'missing_contract']), 1)
        controls = [row for row in items if row.item_type == 'contract_amount_exceeded']
        self.assertEqual({row.amount for row in controls}, {Decimal('50'), Decimal('100')})
        summary = build_contract_closure_summary(self.db, contract.id, self.user)
        self.assertEqual(summary.model_dump(), dict(approved_payment=Decimal('150'),
            pending_payment=Decimal('130'), actual_payment=Decimal('100'), output_invoiced=Decimal('200'),
            actual_receipt=Decimal('0'), missing_input_invoice=Decimal('100')))

    def test_finance_only_user_has_no_contract_identity_or_invoice_items(self):
        contract = self.contract()
        self.db.add(FundTransaction(direction='usage', category='business_payment', amount=100,
                                   contract_id=contract.id, occurred_on=date.today()))
        self.db.flush()
        with patch('app.services.work_items.permitted', side_effect=lambda db, user, code: code == 'supply.finance.view'):
            items = build_work_items(self.db, self.user)
        self.assertEqual([row.item_type for row in items], ['fund_unallocated'])
        self.assertIsNone(items[0].contract_id)
        self.assertIsNone(items[0].contract_name)
        self.assertNotIn('contract_id', items[0].target_query)

    def test_existing_contract_scope_excludes_inaccessible_financial_records(self):
        contract = self.contract()
        self.db.add(FundTransaction(direction='usage', category='business_payment', amount=100,
                                   contract_id=contract.id, occurred_on=date.today()))
        self.db.flush()
        scope = LegalRecordScope(user_id=1, global_access=False, company_codes=frozenset(),
                                 organization_codes=frozenset())
        with patch('app.services.work_items.legal_record_scope', return_value=scope):
            self.assertEqual(build_work_items(self.db, self.user), [])

    def test_contract_summary_redacts_each_downstream_module(self):
        contract = self.contract()
        self.db.add(FundTransaction(direction='usage', category='business_payment', amount=100,
                                   contract_id=contract.id, occurred_on=date.today()))
        self.db.flush()
        with patch('app.services.work_items.permitted', return_value=False):
            summary = build_contract_closure_summary(self.db, contract.id, self.user)
        self.assertTrue(all(value is None for value in summary.model_dump().values()))
        with patch('app.services.work_items.permitted', side_effect=lambda db, user, code: code == 'supply.finance.view'):
            summary = build_contract_closure_summary(self.db, contract.id, self.user)
        self.assertEqual(summary.actual_payment, Decimal('100'))
        self.assertIsNone(summary.output_invoiced)
        self.assertIsNone(summary.missing_input_invoice)
        self.assertIsNone(summary.approved_payment)

    def test_zero_control_amount_is_configuration_prompt(self):
        self.contract(amount=0)
        item = next(row for row in build_work_items(self.db, self.user) if row.item_type == 'contract_amount_exceeded')
        self.assertEqual(item.status, '未配置控制金额')
        self.assertEqual(item.amount, 0)

    def test_missing_input_is_aggregated_per_contract_and_ignores_other_fund_categories(self):
        contract = self.contract()
        self.db.add_all([
            FundTransaction(direction='usage', category='business_payment', amount=100,
                            contract_id=contract.id, occurred_on=date.today()),
            FundTransaction(direction='usage', category='business_payment', amount=20,
                            contract_id=contract.id, occurred_on=date.today()),
            FundTransaction(direction='usage', category='expense', amount=50,
                            contract_id=contract.id, occurred_on=date.today()),
        ])
        self.db.flush()
        items = [row for row in build_work_items(self.db, self.user) if row.item_type == 'input_invoice_missing']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].amount, Decimal('120'))
        self.assertEqual(items[0].target_query['contract_id'], str(contract.id))


class WorkItemsApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:',
                                    connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = SimpleNamespace(id=1, is_active=True, is_superuser=True)
        self.app = create_app()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_work_item_fund_target_query_filters_original_module(self):
        fund = FundTransaction(direction='usage', category='business_payment', amount=100,
                               occurred_on=date.today())
        other = FundTransaction(direction='usage', category='business_payment', amount=30,
                                occurred_on=date.today())
        self.db.add_all([fund, other])
        self.db.commit()
        response = self.client.get('/api/v1/work-items')
        self.assertEqual(response.status_code, 200, response.text)
        item = next(row for row in response.json()['data'] if row['id'] == f'fund_unallocated:{fund.id}')
        result = self.client.get('/api/v1/funds', params=item['target_query'])
        self.assertEqual([row['id'] for row in result.json()['data']['items']], [fund.id])

    def test_summary_endpoint_enforces_visibility_and_redacts_fields(self):
        contract = Contract(contract_no='one', title='one', amount=100, created_by=99)
        self.db.add(contract)
        self.db.commit()
        response = self.client.get(f'/api/v1/contracts/{contract.id}/closure-summary')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Decimal(response.json()['data']['actual_payment']), 0)
        with patch('app.services.work_items.permitted', return_value=False):
            response = self.client.get(f'/api/v1/contracts/{contract.id}/closure-summary')
        self.assertTrue(all(value is None for value in response.json()['data'].values()))
        self.user.is_superuser = False
        response = self.client.get(f'/api/v1/contracts/{contract.id}/closure-summary')
        self.assertEqual(response.status_code, 404, response.text)

    def test_invoice_contract_query_filters_original_module(self):
        self.db.add_all([Invoice(invoice_title='one', amount=10, contract_id=1),
                         Invoice(invoice_title='two', amount=20, contract_id=2)])
        self.db.commit()
        response = self.client.get('/api/v1/invoices', params={'contract_id': 1, 'include_legacy': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row['invoice_title'] for row in response.json()['data']], ['one'])

    def test_nullable_direction_invoice_destination_preserves_legacy_record(self):
        invoice = Invoice(invoice_title='legacy', amount=10, direction=None)
        self.db.add(invoice)
        self.db.commit()
        response = self.client.get('/api/v1/work-items')
        item = next(row for row in response.json()['data'] if row['id'] == f'invoice_unallocated:{invoice.id}')
        self.assertNotIn('direction', item['target_query'])
        response = self.client.get('/api/v1/invoices', params={**item['target_query'], 'include_legacy': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(invoice.id, [row['id'] for row in response.json()['data']])
