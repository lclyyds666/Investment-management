import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import View from './ai-conversations.vue'
import * as api from '@/api/aiAssistant'

vi.mock('@/api/aiAssistant')

const stubs = {
  ElTabs: { template: '<div><slot /></div>' },
  ElTabPane: { template: '<section><slot /></section>' },
  ElTable: { template: '<div><slot /></div>' },
  ElTableColumn: { template: '<span />' },
  ElPagination: true,
  ElDrawer: { template: '<div><slot /></div>' },
  ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  ElForm: { template: '<form><slot /></form>' },
  ElFormItem: { template: '<label><slot /></label>' },
  ElInput: true,
  ElSelect: true,
  ElOption: true,
  ElDatePicker: true,
  ElButton: true,
  ElTag: true,
  ElAlert: true,
  ElEmpty: true,
  ElSkeleton: true
}

describe('AI conversation audit view', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.listAdminConversations.mockResolvedValue({ items: [], total: 0 })
    api.listDeletionAudits.mockResolvedValue({ items: [], total: 0 })
  })

  it('does not expose an export action', () => {
    const wrapper = mount(View, { global: { stubs } })
    expect(wrapper.text()).not.toContain('导出')
  })

  it('requires a deletion reason', () => {
    const wrapper = mount(View, { global: { stubs } })
    const button = wrapper.find('[data-testid="confirm-admin-delete"]')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('uses the admin list filters and authenticated admin endpoints', async () => {
    const wrapper = mount(View, { global: { stubs } })
    await wrapper.vm.loadConversations(1)
    expect(api.listAdminConversations).toHaveBeenCalledWith({ page: 1, size: 20 })
    expect(api.listDeletionAudits).not.toHaveBeenCalled()
  })
})
