import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import DataScreen from './DataScreen.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('@/api/operation', () => ({
  getFinancial: vi.fn().mockResolvedValue({
    total_realized_scale: 0,
    total_gross_income: 0,
    ledger_profit: []
  })
}))

describe('fullscreen DataScreen', () => {
  let wrapper
  const global = {
    stubs: {
      CountTo: {
        props: ['value', 'decimals', 'prefix'],
        template: '<span />'
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
})
