import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ApplicationEntry from '@/components/portal/ApplicationEntry.vue'
import PortalHome from './index.vue'

const push = vi.fn()
const applications = [
  {
    code: 'investment',
    company_name: '山东出版投资有限公司',
    route: '/investment',
    status: 'construction',
    accessible: true
  },
  {
    code: 'supplymanagement',
    company_name: '山东出版供应链管理有限公司',
    route: '/supplymanagement',
    status: 'online',
    accessible: true
  },
  {
    code: 'fundmanagement',
    company_name: '山东出版股权基金管理有限公司',
    route: '/fundmanagement',
    status: 'construction',
    accessible: false,
    denial_reason: '暂时无访问权限'
  }
]

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('@/store/portal', () => ({
  usePortalStore: () => ({
    applications,
    loadPortalContext: vi.fn()
  })
}))

describe('portal home', () => {
  it('renders the assistant before exactly three independent application entries', () => {
    const wrapper = mount(PortalHome, {
      global: {
        stubs: {
          ElSkeleton: true,
          ElAlert: true,
          ElButton: true,
          ElIcon: true
        }
      }
    })

    const assistant = wrapper.get('[data-testid="assistant-region"]')
    const applicationRegion = wrapper.get('[data-testid="application-region"]')
    expect(wrapper.findAll('[data-testid="application-entry"]')).toHaveLength(3)
    expect(assistant.element.compareDocumentPosition(applicationRegion.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('opens only the online and accessible supply application', async () => {
    push.mockClear()
    const wrapper = mount(PortalHome, {
      global: { stubs: { ElSkeleton: true, ElAlert: true, ElButton: true, ElIcon: true } }
    })
    const entries = wrapper.findAll('[data-testid="application-entry"]')

    await entries[0].trigger('click')
    await entries[1].trigger('click')
    await entries[2].trigger('click')

    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/supplymanagement')
  })
})

describe('ApplicationEntry', () => {
  it('marks denied construction applications as disabled', () => {
    const wrapper = mount(ApplicationEntry, {
      props: { application: applications[2] },
      global: { stubs: { ElIcon: true } }
    })

    expect(wrapper.attributes('aria-disabled')).toBe('true')
    expect(wrapper.text()).toContain('建设中')
    expect(wrapper.text()).toContain('暂时无访问权限')
  })
})
