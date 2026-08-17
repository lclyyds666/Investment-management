import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePortalStore } from '@/store/portal'
import * as userApi from '@/api/user'
import ProfileView from './index.vue'

vi.mock('@/api/user')

const passthrough = { template: '<div><slot /></div>' }
const descriptionItem = {
  props: ['label'],
  template: '<div><span>{{ label }}</span><slot /></div>'
}

describe('profile current assignment', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.resetAllMocks()
  })

  it('uses the same current assignment label as the shared header', async () => {
    userApi.getMe.mockResolvedValue({
      full_name: '徐璐',
      username: 'xulu',
      role: 'unassigned',
      role_label: '未配置岗位',
      is_superuser: false,
      assignment_summaries: []
    })
    const portalStore = usePortalStore()
    portalStore.permissions = {
      is_superuser: false,
      assignments: [{ organization_name: '法务风控部', position_name: '部门副总监' }],
      permissions: [],
      resources: [],
      company_roles: {}
    }
    portalStore.isLoaded = true

    const wrapper = shallowMount(ProfileView, {
      global: {
        stubs: {
          ElRow: passthrough,
          ElCol: passthrough,
          ElCard: passthrough,
          ElDescriptions: passthrough,
          ElDescriptionsItem: descriptionItem,
          ElTag: passthrough,
          ElForm: passthrough,
          ElFormItem: passthrough,
          ElInput: passthrough,
          ElButton: passthrough,
          ElAlert: passthrough,
          ElUpload: passthrough,
          ElIcon: passthrough,
          ElEmpty: passthrough
        }
      }
    })
    await flushPromises()

    expect(wrapper.vm.assignmentLabel).toBe('法务风控部 / 部门副总监')
    expect(wrapper.text()).toContain('当前任职')
    expect(wrapper.text()).not.toContain('未配置岗位')
  })
})
