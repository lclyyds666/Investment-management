import { afterEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import ScreenView from './index.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

describe('screen view', () => {
  let wrapper

  afterEach(() => wrapper?.unmount())

  it('uses the named portal route when Escape leaves browser fullscreen', async () => {
    wrapper = shallowMount(ScreenView)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(push).toHaveBeenCalledWith({ name: 'PortalHome' })
  })
})
