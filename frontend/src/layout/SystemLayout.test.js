import { afterEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import SystemLayout from './SystemLayout.vue'

const pathByName = {
  SystemUsers: '/system/users',
  SystemDirectory: '/system/directory',
  SystemOrganization: '/system/organization',
  SystemPositions: '/system/positions',
  SystemAssignments: '/system/assignments',
  SystemAudit: '/system/audit',
  SystemAiConversations: '/system/ai-conversations'
}

const systemChildren = Object.entries(pathByName).map(([name, path]) => ({
  name,
  meta: name === 'SystemDirectory'
    ? { title: '组织通讯录', permission: 'organization.directory.view' }
    : { title: name, requiresSuperuser: true }
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/system/users' }),
  useRouter: () => ({
    options: { routes: [{ path: '/system', children: systemChildren }] },
    resolve: ({ name }) => ({ path: pathByName[name] })
  })
}))

vi.mock('@/store/portal', () => ({
  usePortalStore: () => ({
    isSuperuser: true,
    hasPermission: () => true
  })
}))

const stubs = {
  GlobalHeader: true,
  RouterView: true,
  ElContainer: { template: '<div><slot /></div>' },
  ElAside: { props: ['width'], template: '<aside :data-aside-width="width"><slot /></aside>' },
  ElMain: { template: '<main><slot /></main>' },
  ElMenu: { template: '<nav><slot /></nav>' },
  ElMenuItem: { props: ['index'], template: '<div :data-menu-index="index"><slot /></div>' },
  ElIcon: { template: '<span><slot /></span>' }
}

describe('system layout navigation', () => {
  let wrapper

  afterEach(() => wrapper?.unmount())

  it('shows the six superuser administration items and directory route', () => {
    wrapper = shallowMount(SystemLayout, { global: { stubs } })

    expect(wrapper.findAll('[data-menu-index]').map(item => item.attributes('data-menu-index'))).toEqual([
      '/system/users',
      '/system/directory',
      '/system/organization',
      '/system/positions',
      '/system/assignments',
      '/system/audit',
      '/system/ai-conversations'
    ])
  })
})
