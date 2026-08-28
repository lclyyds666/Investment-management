import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import DataScreen from './DataScreen.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('@/api/operation', () => ({
  getFinancial: vi.fn().mockResolvedValue({
    total_realized_scale: 123456,
    total_gross_income: 45678,
    ledger_profit: [
      { scenic_id: 'quancheng-ouleb', realized_amount: 100000, service_fee: 20000 }
    ]
  })
}))

describe('fullscreen DataScreen', () => {
  let wrapper
  const global = {
    stubs: {
      CountTo: {
        props: ['value', 'decimals', 'prefix'],
        template: '<span class="count-to-stub" :data-value="value" />'
      },
      ScreenMap: true,
      ElButton: { template: '<button><slot /></button>' },
      ElIcon: { template: '<span><slot /></span>' }
    }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    push.mockClear()
  })

  afterEach(() => wrapper?.unmount())

  it('keeps an explicit AI assistant route available', async () => {
    wrapper = shallowMount(DataScreen, {
      props: { fullscreen: true },
      global
    })

    await wrapper.get('[aria-label="AI 助手"]').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'PortalHome' })
  })

  it('does not duplicate the assistant action when embedded under the shared header', () => {
    wrapper = shallowMount(DataScreen, { props: { fullscreen: false }, global })
    expect(wrapper.find('[aria-label="AI 助手"]').exists()).toBe(false)
  })

  it('passes national and regional amounts to CountTo in ten-thousands', async () => {
    wrapper = shallowMount(DataScreen, { props: { fullscreen: false }, global })
    await flushPromises()

    expect(wrapper.findAll('.count-to-stub').map((node) => Number(node.attributes('data-value'))))
      .toEqual([12.3456, 4.5678])
    expect(wrapper.findAll('.metric-unit').map((node) => node.text()))
      .toEqual(['人民币 · 万元', '人民币 · 万元'])

    const screenMap = wrapper.getComponent({ name: 'ScreenMap' })
    expect(screenMap.props('provinceData').find((item) => item.name === '山东省')).toMatchObject({
      revenue: 100000,
      profit: 20000
    })
    screenMap.vm.$emit('province-click', '山东省')
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.count-to-stub').map((node) => Number(node.attributes('data-value'))))
      .toEqual([10, 2])
  })

  it('formats map tooltip amounts from yuan to ten-thousands', async () => {
    const { formatScreenMapMoney } = await import('./ScreenMap.vue')
    expect(formatScreenMapMoney(100000)).toBe('¥10.00 万元')
  })
})
