import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import UsersView from './users.vue'
import { ElMessageBox } from 'element-plus'
import * as userApi from '@/api/user'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/user', () => ({ listUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), resetUserPassword: vi.fn() }))
vi.mock('@/api/organization', () => ({ getOrganizationTree: vi.fn().mockResolvedValue([]), listPositions: vi.fn().mockResolvedValue([]) }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(),
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}))

const ProTable = defineComponent({
  setup(_, { slots }) {
    const row = { id: 7, username: 'worker', has_signature: true, assignment_summaries: [
      { assignment_id: 1, organization_name: '投资公司', position_name: '总经理' },
      { assignment_id: 2, organization_name: '供管公司', position_name: '分管领导' }
    ] }
    return () => h('div', [slots.assignments?.({ row }), slots.actions?.({ row })])
  }
})

const stubs = { ProTable, ElTag: { template: '<span><slot /></span>' }, ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElDialog: true, ElForm: true, ElFormItem: true, ElInput: true, ElSelect: true, ElOption: true, ElSwitch: true }

describe('UsersView', () => {
  beforeEach(() => { vi.clearAllMocks(); userApi.listUsers.mockResolvedValue([]) })
  it('renders assignment tags without an authorization editor and routes to assignments', async () => {
    const wrapper = mount(UsersView, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('投资公司 / 总经理')
    expect(wrapper.text()).toContain('供管公司 / 分管领导')
    expect(wrapper.find('[data-testid="company-role-select"]').exists()).toBe(false)
    await wrapper.get('button:nth-of-type(2)').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'SystemAssignments', query: { user_id: 7 } })
  })
  it('resets a password only after explicit confirmation', async () => {
    ElMessageBox.confirm.mockResolvedValue()
    const wrapper = mount(UsersView, { global: { stubs } })
    await wrapper.get('button:nth-of-type(3)').trigger('click')
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(userApi.resetUserPassword).toHaveBeenCalledWith(7)
  })
  it('does not reset a password when confirmation is cancelled', async () => {
    ElMessageBox.confirm.mockRejectedValue('cancel')
    const wrapper = mount(UsersView, { global: { stubs } })
    await wrapper.get('button:nth-of-type(3)').trigger('click')
    await flushPromises()
    expect(userApi.resetUserPassword).not.toHaveBeenCalled()
  })
})
