import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FundDueAlertModal from './FundDueAlertModal.vue'
import { useFundAlertStore } from '@/store/fundAlerts'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/fund', () => ({ acknowledgeTodayFundAlerts: vi.fn(), getTodayFundAlerts: vi.fn() }))

const stubs = {
  ElDialog: { props: ['modelValue'], emits: ['update:modelValue', 'opened'], template: '<div><slot name="header"/><slot/><slot name="footer"/></div>' },
  ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot/></button>' }
}

describe('FundDueAlertModal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    push.mockReset()
  })

  it('sorts overdue before due soon and acknowledges displayed items', async () => {
    const store = useFundAlertStore()
    store.items = [
      { id: 2, stage: 'due_soon', category: 'company_loan', counterparty: '乙公司', summary: '借款', amount: 20000, maturity_date: '2026-10-20', days_remaining: 10 },
      { id: 1, stage: 'overdue', category: 'bank_credit', counterparty: '甲银行', summary: '授信', amount: 10000, maturity_date: '2026-10-09', days_remaining: -1 }
    ]
    store.visible = true
    store.acknowledgeShown = vi.fn().mockRejectedValue(new Error('offline'))
    const wrapper = mount(FundDueAlertModal, { global: { stubs } })

    expect(wrapper.text().indexOf('已逾期')).toBeLessThan(wrapper.text().indexOf('即将到期'))
    await wrapper.findComponent(stubs.ElDialog).vm.$emit('opened')
    await Promise.resolve()
    expect(store.acknowledgeShown).toHaveBeenCalledTimes(1)
  })

  it.each(['overdue', 'due_soon'])('deep-links to the existing %s maturity filter', async (stage) => {
    const store = useFundAlertStore()
    store.items = [{ id: 1, stage, category: 'bank_credit', amount: 10000, maturity_date: '2026-10-09', days_remaining: stage === 'overdue' ? -1 : 1 }]
    store.visible = true
    const wrapper = mount(FundDueAlertModal, { global: { stubs } })

    await wrapper.vm.goToFunds(stage)

    expect(store.visible).toBe(false)
    expect(push).toHaveBeenCalledWith({ path: '/supplymanagement/finance/fund', query: { maturity_status: stage } })
  })
})
