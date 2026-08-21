import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const portalStore = vi.hoisted(() => ({
  hasResource: vi.fn(),
  hasPermission: vi.fn()
}))
const alertStore = vi.hoisted(() => ({
  count: 0,
  importantAlerts: [],
  startPolling: vi.fn(),
  stopPolling: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/investment/legal-risk/dashboard' }),
  useRouter: () => ({ push: vi.fn() })
}))
vi.mock('@/store/portal', () => ({ usePortalStore: () => portalStore }))
vi.mock('@/store/legalAlerts', () => ({ useLegalAlertsStore: () => alertStore }))
vi.mock('@/components/GlobalHeader.vue', () => ({ default: { template: '<div />' } }))

import InvestmentLayout from './InvestmentLayout.vue'

function mountLayout() {
  return mount(InvestmentLayout, {
    global: {
      stubs: {
        ElContainer: { template: '<div><slot /></div>' },
        ElAside: { template: '<aside><slot /></aside>' },
        ElMain: { template: '<main><slot /></main>' },
        ElDrawer: { template: '<div><slot /></div>' },
        ElButton: { template: '<button><slot /></button>' },
        RouterView: true
      }
    }
  })
}

describe('investment legal-risk navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    portalStore.hasResource.mockReturnValue(true)
    portalStore.hasPermission.mockReturnValue(true)
  })

  it('shows contract management when its legal resource is available', () => {
    const wrapper = mountLayout()

    expect(wrapper.text()).toContain('合同管理')
  })

  it('hides contract management without the legal contract resource', () => {
    portalStore.hasResource.mockImplementation((code) => code !== 'invest.legal.contracts')
    const wrapper = mountLayout()

    expect(wrapper.text()).not.toContain('合同管理')
  })
})
