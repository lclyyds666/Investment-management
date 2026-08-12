import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import GlobalHeader from './GlobalHeader.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

const global = {
  stubs: {
    ThemeToggle: true,
    UserDropdown: true,
    ElIcon: { template: '<span><slot /></span>' },
    ElButton: { template: '<button><slot /></button>' }
  }
}

describe('GlobalHeader', () => {
  it('returns to the portal through the named assistant route', async () => {
    const wrapper = mount(GlobalHeader, {
      props: { contextLabel: '山东出版供应链管理有限公司', showAssistantAction: true },
      global
    })

    expect(wrapper.text()).toContain('山东出版投资有限公司工作平台')
    expect(wrapper.text()).toContain('山东出版供应链管理有限公司')
    await wrapper.get('[aria-label="AI 助手"]').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'PortalHome' })
  })

  it('does not render the supply assistant action in the portal shell', () => {
    const wrapper = mount(GlobalHeader, { global })
    expect(wrapper.find('[aria-label="AI 助手"]').exists()).toBe(false)
  })
})
