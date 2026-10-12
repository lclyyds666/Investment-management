import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from './App.vue'

describe('App', () => {
  it('mounts the global fund alert modal beside the router view', () => {
    const wrapper = shallowMount(App, {
      global: {
        stubs: {
          ElConfigProvider: { template: '<div><slot /></div>' },
          RouterView: { name: 'RouterView', template: '<div />' },
          FundDueAlertModal: { name: 'FundDueAlertModal', template: '<div />' }
        }
      }
    })
    expect(wrapper.findComponent({ name: 'FundDueAlertModal' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'RouterView' }).exists()).toBe(true)
  })
})
