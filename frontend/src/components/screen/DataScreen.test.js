import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import DataScreen from './DataScreen.vue'

const push = vi.fn()
const operationApi = vi.hoisted(() => ({ getFinancial: vi.fn() }))

const financialData = (scenicCompletion = []) => ({
  total_realized_scale: 123456,
  total_gross_income: 45678,
  ledger_profit: [
    { scenic_id: 'quancheng-ouleb', realized_amount: 100000, service_fee: 20000 }
  ],
  scenic_completion: scenicCompletion
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('@/api/operation', () => operationApi)

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
      ElIcon: { template: '<span><slot /></span>' },
      ElEmpty: { props: ['description'], template: '<div class="empty-stub">{{ description }}</div>' }
    }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    push.mockClear()
    operationApi.getFinancial.mockReset()
    operationApi.getFinancial.mockResolvedValue(financialData())
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
    expect(screenMap.props('provinceData').find((item) => item.name === '湖南省')).toMatchObject({
      revenue: 0,
      profit: 0,
      scenicCount: 1
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

  it('registers Hunan as a screen-map business node', async () => {
    const { SCREEN_PROVINCE_COORDS } = await import('./ScreenMap.vue')
    expect(SCREEN_PROVINCE_COORDS['湖南省']).toEqual([112.94, 28.23])
  })

  it('shows each scenic and business type separately for the selected province', async () => {
    operationApi.getFinancial.mockResolvedValue(financialData([
      { scenic_id: 'quanzhou-ouleb', business_type: 'hotel', cumulative_writeoff: 500, pending_writeoff: 500, completion_rate: 50 },
      { scenic_id: 'fuzhou-ouleb', business_type: 'ticket', cumulative_writeoff: 800, pending_writeoff: 200, completion_rate: 80 },
      { scenic_id: 'quanzhou-ouleb', business_type: 'ticket', cumulative_writeoff: 700, pending_writeoff: 300, completion_rate: 70 },
      { scenic_id: 'zunyi-zoo', business_type: 'ticket', cumulative_writeoff: 0, pending_writeoff: 0, completion_rate: null }
    ]))
    wrapper = shallowMount(DataScreen, { props: { fullscreen: false }, global })
    await flushPromises()

    wrapper.getComponent({ name: 'ScreenMap' }).vm.$emit('province-click', '福建省')
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('[data-test="completion-row"]').map((node) => node.text())).toEqual([
      '福州欧乐堡门票80.00%',
      '泉州欧乐堡门票70.00%',
      '泉州欧乐堡酒店50.00%'
    ])
  })

  it('shows an em dash for zero denominator and hides details in national mode', async () => {
    operationApi.getFinancial.mockResolvedValue(financialData([
      { scenic_id: 'zunyi-zoo', business_type: 'ticket', cumulative_writeoff: 0, pending_writeoff: 0, completion_rate: null }
    ]))
    wrapper = shallowMount(DataScreen, { props: { fullscreen: false }, global })
    await flushPromises()

    wrapper.getComponent({ name: 'ScreenMap' }).vm.$emit('province-click', '贵州省')
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="completion-row"]').text()).toBe('遵义动物园门票—')
    expect(wrapper.vm.formatCompletionRate(undefined)).toBe('—')

    await wrapper.get('.reset-button').trigger('click')
    expect(wrapper.find('[aria-label="景区完成度"]').exists()).toBe(false)
  })

  it('uses the latest financial refresh when a province is selected again', async () => {
    operationApi.getFinancial.mockResolvedValueOnce(financialData([
      { scenic_id: 'quancheng-ouleb', business_type: 'ticket', completion_rate: 80 }
    ]))
    wrapper = shallowMount(DataScreen, { props: { fullscreen: false }, global })
    await flushPromises()
    const screenMap = wrapper.getComponent({ name: 'ScreenMap' })
    screenMap.vm.$emit('province-click', '山东省')
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="completion-row"]').text()).toContain('80.00%')

    screenMap.vm.$emit('province-click', '贵州省')
    operationApi.getFinancial.mockResolvedValueOnce(financialData([
      { scenic_id: 'quancheng-ouleb', business_type: 'ticket', completion_rate: 92.345 }
    ]))
    await wrapper.vm.loadFinancial()
    screenMap.vm.$emit('province-click', '山东省')
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="completion-row"]').text()).toContain('92.34%')
  })
})
