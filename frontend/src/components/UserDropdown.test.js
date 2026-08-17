import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import UserDropdown from './UserDropdown.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push, replace: vi.fn() })
}))

vi.mock('@/api/user', () => ({
  getMe: vi.fn(),
  updateSignature: vi.fn(),
  changeMyPassword: vi.fn(),
  changeMyUsername: vi.fn()
}))

vi.mock('@/api/audit', () => ({ logout: vi.fn() }))

describe('UserDropdown', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
  })

  it('opens the namespaced profile route from the shared user menu', async () => {
    const wrapper = shallowMount(UserDropdown)
    wrapper.findComponent({ name: 'ElDropdown' }).vm.$emit('command', 'info')
    await wrapper.vm.$nextTick()
    expect(push).toHaveBeenCalledWith({ name: 'Profile' })
  })

  it('shows every current normalized assignment instead of the legacy unassigned role', () => {
    const userStore = useUserStore()
    const portalStore = usePortalStore()
    userStore.setUserInfo({
      full_name: '徐璐',
      role: 'unassigned',
      role_label: '未配置岗位',
      is_superuser: false,
      assignment_summaries: []
    })
    portalStore.permissions = {
      is_superuser: false,
      assignments: [
        { organization_name: '法务风控部', position_name: '部门副总监' },
        { organization_name: '资产财务部', position_name: '财务复核' }
      ],
      permissions: [],
      resources: [],
      company_roles: {}
    }
    portalStore.isLoaded = true

    const wrapper = shallowMount(UserDropdown, {
      global: {
        stubs: {
          ElDropdown: { template: '<div><slot /></div>' },
          ElTag: { template: '<span><slot /></span>' }
        }
      }
    })
    expect(wrapper.get('.user-role').text()).toBe(
      '法务风控部 / 部门副总监、资产财务部 / 财务复核'
    )
  })
})
