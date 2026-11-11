import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const fundApi = vi.hoisted(() => ({
  listFunds: vi.fn(),
  getFundSummary: vi.fn(),
  createFund: vi.fn(),
  updateFund: vi.fn(),
  deleteFund: vi.fn(),
  settleFund: vi.fn(),
  listCashExecutionTasks: vi.fn(),
  executeCashTask: vi.fn(),
  associateLegacyFund: vi.fn(),
  listLegacyFundContracts: vi.fn()
}))
const portal = vi.hoisted(() => ({
  isSuperuser: false,
  permissionCodes: new Set(['supply.finance.update'])
}))
const authorization = vi.hoisted(() => ({
  canUsePermission: vi.fn((store, code) => store.isSuperuser || store.permissionCodes.has(code))
}))
const messages = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
const messageBox = vi.hoisted(() => ({ confirm: vi.fn() }))
const route = vi.hoisted(() => ({ query: {} }))

vi.mock('@/api/fund', () => fundApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('@/utils/businessAuthorization', () => authorization)
vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(),
  ElMessage: messages,
  ElMessageBox: messageBox
}))

import FundView from './fund.vue'

const global = {
  stubs: {
    ElCard: { template: '<div><slot name="header" /><slot /></div>' },
    ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
    ElTable: true,
    ElPagination: true
  }
}

function mountView() {
  return shallowMount(FundView, { global })
}

describe('fund management view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    portal.isSuperuser = false
    portal.permissionCodes = new Set(['supply.finance.update'])
    route.query = {}
    fundApi.getFundSummary.mockResolvedValue({
      available_funds: 850000,
      total_increase: 1200000,
      total_usage: 350000,
      due_within_30_amount: 1000000,
      due_within_30_count: 1,
      overdue_count: 0
    })
    fundApi.listFunds.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    fundApi.createFund.mockResolvedValue({ id: 1 })
    fundApi.updateFund.mockResolvedValue({ id: 1 })
    fundApi.deleteFund.mockResolvedValue({ id: 1 })
    fundApi.settleFund.mockResolvedValue({ id: 1 })
    fundApi.listCashExecutionTasks.mockResolvedValue([])
    fundApi.executeCashTask.mockResolvedValue({ id: 1 })
    fundApi.associateLegacyFund.mockResolvedValue({ id: 1 })
    fundApi.listLegacyFundContracts.mockResolvedValue([{ id: 3, scenic_id: 's', contract_no: 'C', title: 'Contract' }])
    messageBox.confirm.mockResolvedValue()
  })

  it('offers manual non-business categories and explicit historic association without rewriting money', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openCreate()
    expect(wrapper.vm.form.category).toBe('own_funds')
    expect(wrapper.vm.formCategoryOptions.some(item => item.value === 'customer_payment')).toBe(false)
    const row = { id: 7, category: 'business_payment', direction: 'usage', scenic_id: 's', amount: '100', occurred_on: '2020-01-01' }
    await wrapper.vm.openAssociation(row)
    Object.assign(wrapper.vm.associationForm, { contract_id: 3, approval_form_id: 9 })
    await wrapper.vm.submitAssociation()
    expect(fundApi.associateLegacyFund).toHaveBeenCalledWith(7, { contract_id: 3, approval_form_id: 9 })
    expect(row.amount).toBe('100')
    expect(row.occurred_on).toBe('2020-01-01')
    expect(wrapper.vm.taskSource({ ...row, contract_id: 3 })).toContain('合同 #3')
  })

  it('preserves execution bank evidence for descriptive corrections', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openEdit({ id: 1, execution_task_id: 2, direction: 'usage', category: 'business_payment',
      amount: '100', occurred_on: '2026-01-01', bank_reference: 'BANK', counterparty: ' Supplier  ' })
    expect(wrapper.vm.editingExecution).toBe(true)
    wrapper.vm.form.summary = 'corrected'
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.submitForm()
    expect(fundApi.updateFund).toHaveBeenCalledWith(1, expect.objectContaining({ bank_reference: 'BANK', counterparty: ' Supplier  ', amount: 100, summary: 'corrected' }))
  })

  it('uses a valid maturity deep link on the initial ledger request only once', async () => {
    route.query = { maturity_status: 'overdue' }
    mountView()
    await flushPromises()

    expect(fundApi.listFunds).toHaveBeenCalledTimes(1)
    expect(fundApi.listFunds).toHaveBeenCalledWith(expect.objectContaining({
      maturity_status: 'overdue',
      page: 1
    }))
  })

  it('ignores an unsupported maturity deep link', async () => {
    route.query = { maturity_status: 'unexpected' }
    mountView()
    await flushPromises()

    expect(fundApi.listFunds).toHaveBeenCalledTimes(1)
    expect(fundApi.listFunds.mock.calls[0][0]).not.toHaveProperty('maturity_status')
  })

  it('renders summary in ten-thousand yuan', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('85.00')
    expect(wrapper.text()).toContain('万元')
  })

  it('submits wan input as API yuan and blocks credit without maturity', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openCreate()
    Object.assign(wrapper.vm.form, {
      direction: 'increase',
      category: 'bank_credit',
      amountWan: 12.345678,
      occurred_on: '2026-08-28',
      maturity_date: '2026-09-27',
      counterparty: '测试银行',
      summary: '流动资金授信'
    })
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.submitForm()

    expect(fundApi.createFund).toHaveBeenCalledWith(expect.objectContaining({
      amount: 123456.78
    }))

    fundApi.createFund.mockClear()
    wrapper.vm.openCreate()
    Object.assign(wrapper.vm.form, {
      direction: 'increase',
      category: 'bank_credit',
      amountWan: 12,
      occurred_on: '2026-08-28',
      maturity_date: null
    })
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.submitForm()

    expect(fundApi.createFund).not.toHaveBeenCalled()
    expect(messages.error).toHaveBeenCalledWith('银行授信和公司借款必须填写到期日')
  })

  it('maps filters to the ledger API and resets the page when searching', async () => {
    const wrapper = mountView()
    await flushPromises()
    Object.assign(wrapper.vm.filters, {
      direction: 'usage',
      category: 'expense',
      settlement_status: 'open',
      maturity_status: 'due_soon',
      dateRange: ['2026-08-01', '2026-08-28'],
      keyword: '供应商',
      unallocated_only: false,
      page: 3
    })

    await wrapper.vm.search()

    expect(fundApi.listFunds).toHaveBeenLastCalledWith({
      direction: 'usage',
      category: 'expense',
      settlement_status: 'open',
      maturity_status: 'due_soon',
      start_date: '2026-08-01',
      end_date: '2026-08-28',
      keyword: '供应商',
      unallocated_only: false,
      page: 1,
      page_size: 20
    })
  })

  it('settles only an open credit and refreshes list and summary', async () => {
    const wrapper = mountView()
    await flushPromises()
    fundApi.listFunds.mockClear()
    fundApi.getFundSummary.mockClear()
    const row = {
      id: 7,
      category: 'bank_credit',
      settlement_status: 'open',
      occurred_on: '2026-08-01'
    }

    expect(wrapper.vm.canSettle(row)).toBe(true)
    expect(wrapper.vm.canSettle({ ...row, settlement_status: 'settled' })).toBe(false)
    expect(wrapper.vm.canSettle({ ...row, settlement_status: '' })).toBe(false)
    expect(wrapper.vm.canSettle({ ...row, settlement_status: 'unknown' })).toBe(false)
    expect(wrapper.vm.canSettle({ ...row, settlement_status: undefined })).toBe(false)
    expect(wrapper.vm.canSettle({ ...row, category: 'customer_payment' })).toBe(false)
    await wrapper.vm.onSettle(row)

    expect(fundApi.settleFund).toHaveBeenCalledWith(7, expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/))
    expect(fundApi.listFunds).toHaveBeenCalledTimes(1)
    expect(fundApi.getFundSummary).toHaveBeenCalledTimes(1)
  })

  it('edits yuan data in wan without sending settlement state through update', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openEdit({
      id: 9,
      direction: 'increase',
      category: 'company_loan',
      amount: 123456.78,
      occurred_on: '2026-08-01',
      counterparty: '测试公司',
      summary: '周转借款',
      maturity_date: '2026-12-31',
      remark: '测试',
      settlement_status: 'open',
      settled_on: null
    })
    expect(wrapper.vm.form.amountWan).toBe(12.345678)
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.submitForm()

    expect(fundApi.updateFund).toHaveBeenCalledWith(9, {
      direction: 'increase',
      category: 'company_loan',
      amount: 123456.78,
      occurred_on: '2026-08-01',
      counterparty: '测试公司',
      summary: '周转借款',
      maturity_date: '2026-12-31',
      remark: '测试',
      bank_reference: ''
    })
  })

  it('locks direction and category when editing a settled financing record', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openEdit({
      id: 10,
      direction: 'increase',
      category: 'bank_credit',
      amount: 200000,
      occurred_on: '2026-08-01',
      counterparty: '测试银行',
      summary: '已结清授信',
      maturity_date: '2026-08-20',
      remark: '',
      settlement_status: 'settled',
      settled_on: '2026-08-21'
    })
    expect(wrapper.vm.editingSettled).toBe(true)
    Object.assign(wrapper.vm.form, {
      direction: 'usage',
      category: 'expense',
      summary: '只允许修改非分类字段'
    })
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.submitForm()

    expect(fundApi.updateFund).toHaveBeenCalledWith(10, expect.objectContaining({
      direction: 'increase',
      category: 'bank_credit',
      summary: '只允许修改非分类字段'
    }))
    expect(fundApi.updateFund.mock.calls[0][1]).not.toHaveProperty('settlement_status')
    expect(fundApi.updateFund.mock.calls[0][1]).not.toHaveProperty('settled_on')
  })

  it('deletes after confirmation and refreshes list and summary', async () => {
    const wrapper = mountView()
    await flushPromises()
    fundApi.listFunds.mockClear()
    fundApi.getFundSummary.mockClear()

    await wrapper.vm.onDelete({ id: 11, occurred_on: '2026-08-28', category: 'expense' })

    expect(messageBox.confirm).toHaveBeenCalledTimes(1)
    expect(fundApi.deleteFund).toHaveBeenCalledWith(11)
    expect(fundApi.listFunds).toHaveBeenCalledTimes(1)
    expect(fundApi.getFundSummary).toHaveBeenCalledTimes(1)
  })

  it('uses the finance update permission for all write actions', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.vm.canWrite).toBe(true)
    expect(authorization.canUsePermission).toHaveBeenCalledWith(portal, 'supply.finance.update')
  })
})
