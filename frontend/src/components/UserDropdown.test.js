import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
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
    push.mockClear()
  })

  it('opens the namespaced profile route from the shared user menu', async () => {
    const wrapper = shallowMount(UserDropdown)
    wrapper.findComponent({ name: 'ElDropdown' }).vm.$emit('command', 'info')
    await wrapper.vm.$nextTick()
    expect(push).toHaveBeenCalledWith({ name: 'Profile' })
  })
})
