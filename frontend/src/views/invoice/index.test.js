import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const invoiceApi = vi.hoisted(() => ({
  listInvoices: vi.fn(),
  invoiceStats: vi.fn(),
  invoiceRecordStats: vi.fn(),
  updateInvoice: vi.fn(),
  listInvoiceAllocations: vi.fn(),
  createInvoiceAllocation: vi.fn(),
  deleteInvoiceAllocation: vi.fn(),
  listInvoiceAttachments: vi.fn(),
  uploadInvoiceAttachments: vi.fn(),
  listInvoiceDetails: vi.fn(),
  updateInvoiceDetail: vi.fn(),
  createInvoiceApprovalForm: vi.fn(),
  downloadInvoiceDocument: vi.fn()
}))
const contractApi = vi.hoisted(() => ({ listContracts: vi.fn(), listEligibleContracts: vi.fn() }))
const customerApi = vi.hoisted(() => ({ listCustomers: vi.fn(), getCustomer: vi.fn() }))
const fundApi = vi.hoisted(() => ({ listFunds: vi.fn() }))
const route = vi.hoisted(() => ({ query: {} }))
vi.mock('vue-router', () => ({ useRoute: () => route }))
const portal = vi.hoisted(() => ({
  isSuperuser: false,
  hasPermission: vi.fn(code => code === 'supply.invoice.view' || code === 'supply.invoice.manage' || code === 'supply.invoice.approve')
}))

vi.mock('@/api/invoice', () => invoiceApi)
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/api/customer', () => customerApi)
vi.mock('@/api/fund', () => fundApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('@/utils/file', () => ({ downloadBlob: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}))

import InvoiceView from './index.vue'

const passthrough = { template: '<div><slot /><slot name="header" /><slot name="footer" /></div>' }
const labeled = { props: ['label'], template: '<div><span>{{ label }}</span><slot /></div>' }

function mountView() {
  return shallowMount(InvoiceView, {
    global: {
      directives: { loading: () => {} },
      stubs: {
        ProTable: { props: ['fetch'], mounted() { this.fetch() }, methods: { reload() { this.fetch() } }, template: '<div><slot name="toolbar" /><slot name="prepend" /><slot name="status" /><slot name="actions" :row="{ id: 6, direction: \'input\' }" /></div>' },
        ElTabs: { template: '<div><slot /></div>' },
        ElTabPane: { props: ['label'], template: '<div>{{ label }}<slot /></div>' },
        ElDialog: passthrough,
        ElDrawer: passthrough,
        ElForm: passthrough,
        ElFormItem: labeled,
        ElDescriptions: passthrough,
        ElDescriptionsItem: labeled,
        ElInput: true,
        ElInputNumber: true,
        ElSelect: passthrough,
        ElOption: true,
        ElDatePicker: true,
        ElUpload: passthrough,
        ElButton: passthrough,
        ElTag: passthrough,
        ElRow: passthrough,
        ElCol: passthrough,
        ElIcon: passthrough,
        ElTable: true,
        ElTableColumn: true
      }
    }
  })
}

describe('invoice management redesign', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    portal.hasPermission.mockImplementation(code => ['supply.invoice.view', 'supply.invoice.manage',
      'supply.invoice.approve', 'supply.finance.view', 'supply.finance.update'].includes(code))
    route.query = {}
    invoiceApi.listInvoices.mockResolvedValue([])
    invoiceApi.invoiceStats.mockResolvedValue({ pending: 0, issued: 0, issued_amount: 0 })
    invoiceApi.invoiceRecordStats.mockResolvedValue({ attachment_count: 0, detail_count: 1, detail_total: 100, difference: 0 })
    invoiceApi.listInvoiceAttachments.mockResolvedValue([])
    invoiceApi.uploadInvoiceAttachments.mockResolvedValue([])
    invoiceApi.listInvoiceDetails.mockResolvedValue({ items: [], detail_total: 0, difference: 0 })
    invoiceApi.updateInvoice.mockResolvedValue({})
    invoiceApi.listInvoiceAllocations.mockResolvedValue([])
    invoiceApi.createInvoiceAllocation.mockResolvedValue({})
    invoiceApi.deleteInvoiceAllocation.mockResolvedValue({})
    invoiceApi.updateInvoiceDetail.mockResolvedValue({ items: [], detail_total: 0, difference: 0 })
    invoiceApi.createInvoiceApprovalForm.mockResolvedValue({})
    invoiceApi.downloadInvoiceDocument.mockResolvedValue(new Blob(['ok']))
    contractApi.listContracts.mockResolvedValue([{ id: 7, contract_no: 'HT-001', title: '测试合同' }])
    contractApi.listEligibleContracts.mockResolvedValue([{ id: 7, contract_no: 'HT-001', title: '测试合同' }])
    customerApi.listCustomers.mockResolvedValue([])
    customerApi.getCustomer.mockResolvedValue(null)
    fundApi.listFunds.mockResolvedValue({ items: [], total: 0 })
  })

  it('opens a nullable-direction legacy work item without an input API filter', async () => {
    route.query = { invoice_id: '9' }
    invoiceApi.listInvoices.mockImplementation(async ({ direction }) => direction ? [] : [
      { id: 8, direction: 'input' }, { id: 9, direction: null, invoice_title: 'legacy' }
    ])
    const wrapper = mountView()
    await flushPromises()
    const rows = await wrapper.vm.fetchRows()
    expect(invoiceApi.listInvoices).toHaveBeenLastCalledWith(expect.objectContaining({ direction: undefined, include_legacy: true }))
    expect(rows).toEqual([{ id: 9, direction: null, invoice_title: 'legacy' }])
    wrapper.unmount()
  })

  it('exposes input/output tabs and never exposes create or delete actions', () => {
    const wrapper = mountView()
    expect(wrapper.text()).toContain('进项发票')
    expect(wrapper.text()).toContain('销项发票')
    expect(wrapper.text()).not.toContain('新建发票')
    expect(wrapper.text()).not.toContain('删除')
  })

  it('loads invoices with the active direction filter', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(invoiceApi.listInvoices).toHaveBeenCalledWith(expect.objectContaining({ direction: 'input' }))
    wrapper.vm.activeDirection = 'output'
    await wrapper.vm.reload()
    expect(invoiceApi.listInvoices).toHaveBeenLastCalledWith(expect.objectContaining({ direction: 'output' }))
  })

  it('keeps invoice status read-only while editing input invoices', async () => {
    const wrapper = mountView()
    wrapper.vm.openEdit({ id: 1, direction: 'input', invoice_title: '供应商', amount: 100, status: 'pending' })
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.form.status).toBe('pending')
    expect(wrapper.text()).toContain('状态由附件上传自动更新')
  })

  it('uploads multiple input attachments and refreshes the list', async () => {
    const wrapper = mountView()
    const files = [new File(['a'], 'a.pdf'), new File(['b'], 'b.pdf')]
    await wrapper.vm.uploadFiles({ id: 2, direction: 'input' }, files)
    expect(invoiceApi.uploadInvoiceAttachments).toHaveBeenCalledWith(2, files)
    expect(invoiceApi.listInvoices).toHaveBeenCalled()
  })

  it('loads output contract choices and customer snapshot fields', async () => {
    const wrapper = mountView()
    await wrapper.vm.openEdit({ id: 3, direction: 'output', contract_no: 'HT-001', customer_name: '客户', amount: 200 })
    expect(contractApi.listContracts).toHaveBeenCalled()
    expect(wrapper.vm.form.contract_no).toBe('HT-001')
    expect(wrapper.vm.form.customer_name).toBe('客户')
  })

  it('shows contract, scenic, source business and period columns', () => {
    const wrapper = mountView()
    expect(wrapper.vm.columns.map(column => column.label)).toEqual(expect.arrayContaining([
      '合同编号', '景区', '来源业务', '台账期次'
    ]))
  })

  it('keeps inherited source contract read-only', async () => {
    const wrapper = mountView()
    wrapper.vm.openEdit({
      id: 21, direction: 'output', generated_by_source: true,
      contract_id: 7, contract_no: 'HT-001', scenic_id: 'scenic-a', source_kind: 'ticket'
    })
    await flushPromises()
    expect(wrapper.vm.canBackfillContract).toBe(false)
    expect(contractApi.listEligibleContracts).not.toHaveBeenCalled()
  })

  it('backfills a historical source contract once from eligible choices', async () => {
    const wrapper = mountView()
    wrapper.vm.openEdit({
      id: 22, direction: 'output', generated_by_source: true,
      contract_id: null, contract_no: '', scenic_id: 'scenic-a', source_kind: 'ticket', status: 'pending'
    })
    await flushPromises()
    expect(wrapper.vm.canBackfillContract).toBe(true)
    expect(contractApi.listEligibleContracts).toHaveBeenCalledWith('scenic-a', 'ticket')
    wrapper.vm.form.contract_id = 7
    await wrapper.vm.saveEdit()
    expect(invoiceApi.updateInvoice).toHaveBeenCalledWith(22, expect.objectContaining({ contract_id: 7 }))
    expect(invoiceApi.updateInvoice.mock.calls.at(-1)[1]).not.toHaveProperty('contract_no')
  })

  it('hides historical backfill when backend reports source usage', async () => {
    const wrapper = mountView()
    wrapper.vm.openEdit({
      id: 23, direction: 'output', generated_by_source: true,
      contract_id: null, contract_no: '', scenic_id: 'scenic-a', source_kind: 'ticket',
      status: 'pending', source_locked: true, has_approval_form: true
    })
    await flushPromises()
    expect(wrapper.vm.canBackfillContract).toBe(false)
    expect(contractApi.listEligibleContracts).not.toHaveBeenCalled()
  })

  it('only enables output detail save and print when totals balance', async () => {
    invoiceApi.listInvoiceDetails.mockResolvedValue({ items: [{ id: 9, amount: 80 }], detail_total: 80, difference: 20 })
    const wrapper = mountView()
    await wrapper.vm.openDetails({ id: 4, direction: 'output', amount: 100 })
    expect(wrapper.vm.detailDifference).toBe(20)
    expect(wrapper.vm.canPrintDetails).toBe(false)
    wrapper.vm.detailDifference = 0
    expect(wrapper.vm.canPrintDetails).toBe(true)
  })

  it('gates approval generation to manage and approval printing to approve', async () => {
    const wrapper = mountView()
    await wrapper.vm.generateApproval({ id: 5, direction: 'output' })
    expect(invoiceApi.createInvoiceApprovalForm).toHaveBeenCalledWith(5)
    expect(wrapper.vm.canPrintApproval({ approval_status: 'approved' })).toBe(true)
  })

  it('allows a view-only user to print balanced detail and approved approval documents', async () => {
    portal.hasPermission.mockImplementation(code => code === 'supply.invoice.view')
    invoiceApi.listInvoiceDetails.mockResolvedValue({ items: [], detail_total: 100, difference: 0 })
    const wrapper = mountView()
    expect(wrapper.vm.canPrintApproval({ approval_status: 'approved' })).toBe(true)
    await wrapper.vm.printDetails({ id: 8, direction: 'output', amount: 100 })
    await wrapper.vm.printApproval({ id: 8, direction: 'output', approval_status: 'approved' })
    expect(invoiceApi.downloadInvoiceDocument).toHaveBeenCalledTimes(2)
  })

  it('uploads multiple files for output rows through the shared attachment API', async () => {
    const wrapper = mountView()
    const files = [new File(['a'], 'a.pdf'), new File(['b'], 'b.pdf')]
    await wrapper.vm.uploadFiles({ id: 12, direction: 'output' }, files)
    expect(invoiceApi.uploadInvoiceAttachments).toHaveBeenCalledWith(12, files)
  })

  it('remembers an output contract per scenic and direction and fills its customer snapshot', async () => {
    contractApi.listContracts.mockResolvedValue([{ id: 7, contract_no: 'HT-001', title: '测试合同', customer_name: '客户甲' }])
    customerApi.listCustomers.mockResolvedValue([{
      name: '客户甲', social_credit_code: '9137', address: '地址', phone: '123', bank_name: '银行', bank_account: '456'
    }])
    localStorage.setItem('invoice-contract-default:scenic-a:output', 'HT-001')
    const wrapper = mountView()
    await wrapper.vm.openEdit({ id: 13, direction: 'output', scenic_id: 'scenic-a', amount: 200 })
    await flushPromises()
    expect(wrapper.vm.form.contract_no).toBe('HT-001')
    expect(wrapper.vm.form.customer_name).toBe('客户甲')
    expect(wrapper.vm.form.customer_social_credit_code).toBe('9137')
    expect(wrapper.vm.form.customer_bank_account).toBe('456')
  })

  it('loads the real difference before approval or print and blocks nonzero totals', async () => {
    invoiceApi.listInvoiceDetails.mockResolvedValue({ items: [], detail_total: 80, difference: 20 })
    const wrapper = mountView()
    await wrapper.vm.generateApproval({ id: 14, direction: 'output' })
    await wrapper.vm.printApproval({ id: 14, direction: 'output', approval_status: 'approved' })
    expect(invoiceApi.createInvoiceApprovalForm).not.toHaveBeenCalled()
    expect(invoiceApi.downloadInvoiceDocument).not.toHaveBeenCalled()
    expect(invoiceApi.listInvoiceDetails).toHaveBeenCalledWith(14)
  })

  it('labels the fixed detail total column as 价税合计', () => {
    expect(mountView().text()).toContain('价税合计')
  })

  it('opens reconciliation with matching contract direction and remaining funds', async () => {
    invoiceApi.listInvoiceAllocations.mockResolvedValue([{ id: 3, amount: 20 }])
    fundApi.listFunds.mockResolvedValue({ items: [{ id: 9, amount: 100 }], total: 1 })
    const wrapper = mountView()
    await wrapper.vm.openReconciliation({
      id: 6, direction: 'input', contract_id: 7, amount: 100,
      reconciliation_state: 'partial', unallocated_amount: 80
    })
    expect(invoiceApi.listInvoiceAllocations).toHaveBeenCalledWith(6)
    expect(fundApi.listFunds).toHaveBeenCalledWith({
      contract_id: 7, direction: 'usage', unallocated_only: true, page_size: 200
    })
    expect(wrapper.vm.reconciliation.allocations).toHaveLength(1)
    expect(wrapper.vm.reconciliation.candidates).toHaveLength(1)
    expect(wrapper.vm.reconciliationVisible).toBe(true)
  })

  it('shows reconciliation for finance handlers and hides it for business reviewers', async () => {
    portal.hasPermission.mockImplementation(code => ['supply.invoice.view', 'supply.finance.view', 'supply.finance.update'].includes(code))
    const finance = mountView()
    expect(finance.vm.canManage).toBe(false)
    expect(finance.text()).toContain('收付款核销')
    await finance.vm.openReconciliation({ id: 6, direction: 'input', amount: 100 })
    expect(invoiceApi.listInvoiceAllocations).toHaveBeenCalledWith(6)
    finance.unmount()

    invoiceApi.listInvoiceAllocations.mockClear()
    portal.hasPermission.mockImplementation(code => ['supply.invoice.view', 'supply.invoice.manage'].includes(code))
    const reviewer = mountView()
    expect(reviewer.vm.canManage).toBe(true)
    expect(reviewer.text()).not.toContain('收付款核销')
    await reviewer.vm.openReconciliation({ id: 6 })
    expect(invoiceApi.listInvoiceAllocations).not.toHaveBeenCalled()
    reviewer.unmount()
  })

  it('displays and limits candidates to remaining funds and refreshes after add and remove', async () => {
    invoiceApi.listInvoices.mockResolvedValue([{ id: 6, direction: 'input', amount: 100, unallocated_amount: 80 }])
    fundApi.listFunds.mockResolvedValue({ items: [{ id: 9, amount: 100, allocated_amount: 40, unallocated_amount: 60 }] })
    const wrapper = mountView()
    await wrapper.vm.openReconciliation({ id: 6, direction: 'input', amount: 100 })
    expect(wrapper.vm.fundOptionLabel(wrapper.vm.reconciliation.candidates[0])).toContain('总额 ¥100.00 / 可核销 ¥60.00')
    wrapper.vm.allocationForm.fund_transaction_id = 9
    wrapper.vm.onAllocationFundChange()
    expect(wrapper.vm.allocationForm.amount).toBe(60)
    expect(wrapper.vm.allocationLimit).toBe(60)
    invoiceApi.listInvoices.mockResolvedValue([{ id: 6, direction: 'input', amount: 100, unallocated_amount: 20 }])
    fundApi.listFunds.mockResolvedValue({ items: [] })
    await wrapper.vm.addAllocation()
    expect(wrapper.vm.currentInvoice.unallocated_amount).toBe(20)
    expect(wrapper.vm.reconciliation.candidates).toEqual([])
    invoiceApi.listInvoices.mockResolvedValue([{ id: 6, direction: 'input', amount: 100, unallocated_amount: 80 }])
    fundApi.listFunds.mockResolvedValue({ items: [{ id: 9, amount: 100, unallocated_amount: 60 }] })
    await wrapper.vm.removeAllocation({ id: 5 })
    expect(wrapper.vm.currentInvoice.unallocated_amount).toBe(80)
    expect(wrapper.vm.reconciliation.candidates[0].unallocated_amount).toBe(60)
    wrapper.unmount()
  })

  it('adds and removes allocations then reloads reconciliation and invoice rows', async () => {
    const wrapper = mountView()
    await wrapper.vm.openReconciliation({ id: 7, direction: 'output', contract_id: 8, amount: 100 })
    wrapper.vm.allocationForm.fund_transaction_id = 12
    wrapper.vm.allocationForm.amount = 40
    await wrapper.vm.addAllocation()
    expect(invoiceApi.createInvoiceAllocation).toHaveBeenCalledWith(7, {
      fund_transaction_id: 12, amount: 40
    })
    await wrapper.vm.removeAllocation({ id: 5 })
    expect(invoiceApi.deleteInvoiceAllocation).toHaveBeenCalledWith(7, 5)
    expect(invoiceApi.listInvoiceAllocations).toHaveBeenCalledTimes(3)
    expect(invoiceApi.listInvoices).toHaveBeenCalled()
  })

  it('labels input as payment and output as receipt reconciliation', () => {
    const wrapper = mountView()
    expect(wrapper.vm.reconciliationStatusText({ direction: 'input', reconciliation_state: 'allocated' })).toBe('已付款')
    expect(wrapper.vm.reconciliationStatusText({ direction: 'input', reconciliation_state: 'partial' })).toBe('未补票')
    expect(wrapper.vm.reconciliationStatusText({ direction: 'output', reconciliation_state: 'allocated' })).toBe('已回款')
    expect(wrapper.vm.reconciliationStatusText({ direction: 'output', reconciliation_state: 'partial' })).toBe('待回款')
  })
})
