import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ReassignTaskDialog from './ReassignTaskDialog.vue'

const api = vi.hoisted(() => ({
  listWorkflowCandidates: vi.fn(),
  reassignWorkflowTask: vi.fn()
}))
vi.mock('@/api/workflow', () => api)
vi.mock('element-plus', async importOriginal => ({
  ...await importOriginal(),
  ElMessage: { success: vi.fn(), error: vi.fn() }
}))

const task = {
  id: 41,
  target_title: '年度框架合同',
  node_name: '公司负责人审批',
  required_position_name: '公司负责人',
  previous_assignee: { id: 7, full_name: '原负责人' }
}

describe('ReassignTaskDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listWorkflowCandidates.mockResolvedValue([
      { user_id: 7, full_name: '原负责人', organization_name: '供应链公司', position_name: '公司负责人' },
      { user_id: 9, full_name: '新负责人', organization_name: '供应链公司', position_name: '公司负责人' }
    ])
    api.reassignWorkflowTask.mockResolvedValue({})
  })

  it('loads exact task candidates and disables the invalid previous user', async () => {
    const wrapper = mount(ReassignTaskDialog, { props: { modelValue: true, task }, global: { stubs: { ElDialog: { template: '<div><slot/><slot name="footer"/></div>' }, ElSelect: true, ElOption: true, ElInput: true, ElButton: true, ElTag: true } } })
    await flushPromises()
    expect(api.listWorkflowCandidates).toHaveBeenCalledWith({ taskId: 41 })
    expect(wrapper.vm.candidates.find(item => item.user_id === 7).disabled).toBe(true)
    expect(wrapper.text()).toContain('公司负责人')
  })

  it('requires a replacement and reason before reassignment', async () => {
    const wrapper = mount(ReassignTaskDialog, { props: { modelValue: true, task }, global: { stubs: { ElDialog: { template: '<div><slot/><slot name="footer"/></div>' }, ElSelect: true, ElOption: true, ElInput: true, ElButton: true, ElTag: true } } })
    await flushPromises()
    await wrapper.vm.submit()
    expect(api.reassignWorkflowTask).not.toHaveBeenCalled()
    wrapper.vm.userId = 9
    wrapper.vm.reason = '岗位调整'
    await wrapper.vm.submit()
    expect(api.reassignWorkflowTask).toHaveBeenCalledWith(41, 9, '岗位调整')
    expect(wrapper.emitted('reassigned')).toHaveLength(1)
  })

  it('ignores stale candidates after switching tasks and closing', async () => {
    let resolveA
    let resolveB
    api.listWorkflowCandidates
      .mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveB = resolve }))
    const wrapper = mount(ReassignTaskDialog, { props: { modelValue: true, task }, global: { stubs: { ElDialog: { template: '<div><slot/><slot name="footer"/></div>' }, ElSelect: true, ElOption: true, ElInput: true, ElButton: true, ElTag: true } } })
    await wrapper.setProps({ task: { ...task, id: 42, target_title: 'B合同' } })
    resolveB([{ user_id: 12, full_name: 'B候选人' }])
    await flushPromises()
    expect(wrapper.vm.candidates[0].full_name).toBe('B候选人')
    resolveA([{ user_id: 11, full_name: 'A候选人' }])
    await flushPromises()
    expect(wrapper.vm.candidates[0].full_name).toBe('B候选人')
    await wrapper.setProps({ modelValue: false })
    expect(wrapper.vm.candidates).toEqual([])
  })

  it('submits only once while a reassignment is pending', async () => {
    let resolveSubmit
    api.reassignWorkflowTask.mockImplementation(() => new Promise(resolve => { resolveSubmit = resolve }))
    const wrapper = mount(ReassignTaskDialog, { props: { modelValue: true, task }, global: { stubs: { ElDialog: { template: '<div><slot/><slot name="footer"/></div>' }, ElSelect: true, ElOption: true, ElInput: true, ElButton: true, ElTag: true } } })
    await flushPromises()
    wrapper.vm.userId = 9
    wrapper.vm.reason = '岗位调整'
    const first = wrapper.vm.submit()
    const second = wrapper.vm.submit()
    expect(api.reassignWorkflowTask).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.canSubmit).toBe(false)
    resolveSubmit({})
    await Promise.all([first, second])
  })
})
