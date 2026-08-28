import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const fundApi = vi.hoisted(() => ({
  listFunds: vi.fn(),
  getFundSummary: vi.fn(),
  createFund: vi.fn(),
  updateFund: vi.fn(),
  deleteFund: vi.fn(),
  settleFund: vi.fn()
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

vi.mock('@/api/fund', () => fundApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('@/utils/businessAuthorization', () => authorization)
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
    messageBox.confirm.mockResolvedValue()
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
      remark: '测试'
    })
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
