import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import SupplyLayout from './index.vue'

const pathByName = {
  Dashboard: '/supplymanagement/dashboard',
  Contract: '/supplymanagement/contract',
  Profile: '/supplymanagement/profile'
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/supplymanagement/dashboard' }),
  useRouter: () => ({
    options: {
      routes: [{
        path: '/supplymanagement',
        children: [
          { name: 'Dashboard', meta: { title: '战略总览', icon: 'HomeFilled' } },
          { name: 'Contract', meta: { title: '合同管理', icon: 'Document', group: '经营合规' } },
          { name: 'Profile', meta: { title: '个人设置', icon: 'User' } }
        ]
      }]
    },
    resolve: ({ name }) => ({ path: pathByName[name] })
  })
}))

vi.mock('@/store/user', () => ({
  useUserStore: () => ({
    isSuperuser: true,
    role: 'info_maintainer',
    hasRole: () => true
  })
}))

vi.mock('@/store/approvalBadge', () => ({
  useApprovalBadgeStore: () => ({
    contract: 0,
    business: 0,
    startPolling: vi.fn(),
    stopPolling: vi.fn()
  })
}))

describe('supply layout navigation', () => {
  let wrapper

  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
  })

  afterEach(() => wrapper?.unmount())

  it('passes absolute namespaced paths to every supply menu item', () => {
    wrapper = shallowMount(SupplyLayout, {
      global: {
        stubs: {
          GlobalHeader: true,
          RouterView: true,
          ElContainer: { template: '<div><slot /></div>' },
          ElAside: {
            props: ['width'],
            template: '<aside :data-aside-width="width"><slot /></aside>'
          },
          ElMain: { template: '<main><slot /></main>' },
          ElMenu: { template: '<nav><slot /></nav>' },
          ElSubMenu: { template: '<section><slot name="title" /><slot /></section>' },
          ElMenuItem: {
            props: ['index'],
            template: '<div :data-menu-index="index"><slot /></div>'
          },
          ElIcon: { template: '<span><slot /></span>' }
        }
      }
    })

    const indices = wrapper.findAll('[data-menu-index]').map((item) => item.attributes('data-menu-index'))
    expect(indices).toEqual([
      '/supplymanagement/dashboard',
      '/supplymanagement/contract',
      '/supplymanagement/profile'
    ])
  })

  it('collapses the supply sidebar on narrow viewports', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 375 })
    wrapper = shallowMount(SupplyLayout, {
      global: {
        stubs: {
          GlobalHeader: true,
          RouterView: true,
          ElContainer: { template: '<div><slot /></div>' },
          ElAside: {
            props: ['width'],
            template: '<aside :data-aside-width="width"><slot /></aside>'
          },
          ElMain: { template: '<main><slot /></main>' },
          ElMenu: { template: '<nav><slot /></nav>' },
          ElSubMenu: { template: '<section><slot name="title" /><slot /></section>' },
          ElMenuItem: { props: ['index'], template: '<div><slot /></div>' },
          ElIcon: { template: '<span><slot /></span>' }
        }
      }
    })

    expect(wrapper.get('[data-aside-width]').attributes('data-aside-width')).toBe('64px')
    expect(wrapper.find('.collapse-bar').exists()).toBe(false)
  })
})
