import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const invoiceApi = vi.hoisted(() => ({
  listInvoices: vi.fn(),
  invoiceStats: vi.fn(),
  invoiceRecordStats: vi.fn(),
  updateInvoice: vi.fn(),
  listInvoiceAttachments: vi.fn(),
  uploadInvoiceAttachments: vi.fn(),
  listInvoiceDetails: vi.fn(),
  updateInvoiceDetail: vi.fn(),
  createInvoiceApprovalForm: vi.fn(),
  downloadInvoiceDocument: vi.fn()
}))
const contractApi = vi.hoisted(() => ({ listContracts: vi.fn() }))
const customerApi = vi.hoisted(() => ({ listCustomers: vi.fn(), getCustomer: vi.fn() }))
const portal = vi.hoisted(() => ({
  isSuperuser: false,
  hasPermission: vi.fn(code => code === 'supply.invoice.view' || code === 'supply.invoice.manage' || code === 'supply.invoice.approve')
}))

vi.mock('@/api/invoice', () => invoiceApi)
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/api/customer', () => customerApi)
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
        ProTable: { props: ['fetch'], mounted() { this.fetch() }, methods: { reload() { this.fetch() } }, template: '<div><slot name="toolbar" /><slot name="prepend" /><slot name="status" /><slot name="actions" /></div>' },
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
    invoiceApi.listInvoices.mockResolvedValue([])
    invoiceApi.invoiceStats.mockResolvedValue({ pending: 0, issued: 0, issued_amount: 0 })
    invoiceApi.invoiceRecordStats.mockResolvedValue({ attachment_count: 0, detail_count: 1, detail_total: 100, difference: 0 })
    invoiceApi.listInvoiceAttachments.mockResolvedValue([])
    invoiceApi.uploadInvoiceAttachments.mockResolvedValue([])
    invoiceApi.listInvoiceDetails.mockResolvedValue({ items: [], detail_total: 0, difference: 0 })
    invoiceApi.updateInvoice.mockResolvedValue({})
    invoiceApi.updateInvoiceDetail.mockResolvedValue({ items: [], detail_total: 0, difference: 0 })
    invoiceApi.createInvoiceApprovalForm.mockResolvedValue({})
    invoiceApi.downloadInvoiceDocument.mockResolvedValue(new Blob(['ok']))
    contractApi.listContracts.mockResolvedValue([{ id: 7, contract_no: 'HT-001', title: '测试合同' }])
    customerApi.listCustomers.mockResolvedValue([])
    customerApi.getCustomer.mockResolvedValue(null)
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
})
