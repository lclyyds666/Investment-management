import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import WorkflowTimeline from './WorkflowTimeline.vue'

const tasks = [{
  id: 11,
  sequence: 2,
  node_name: '供管公司负责人审批',
  mode: 'designated_user',
  required_position_code: 'supply.company_leader',
  required_position_name: '供管公司负责人',
  designated_user: { id: 7, full_name: '张负责人' },
  status: 'approved',
  actions: [
    { id: 21, action: 'reassign', actor_name: '系统管理员', position_name: '信息维护者', previous_assignee_name: '王负责人', new_assignee_name: '张负责人', reason: '岗位调整', created_at: '2026-08-12T09:00:00' },
    { id: 22, action: 'approve', actor_name: '张负责人', position_name: '供管公司负责人', comment: '同意办理', created_at: '2026-08-12T10:00:00' }
  ]
}]

describe('WorkflowTimeline', () => {
  it('renders real sequence, assignment mode, actor audit, and reassignment history', () => {
    const wrapper = mount(WorkflowTimeline, { props: { tasks } })
    const text = wrapper.text()
    expect(text).toContain('03')
    expect(text).toContain('指定人员')
    expect(text).toContain('供管公司负责人')
    expect(text).toContain('张负责人')
    expect(text).toContain('同意办理')
    expect(text).toContain('王负责人 → 张负责人')
    expect(text).toContain('岗位调整')
    expect(text).toContain('改派 · 系统管理员')
    expect(text).toContain('信息维护者')
    expect(text).toContain('已通过')
  })

  it.each([
    ['pending', '待激活'], ['active', '办理中'], ['approved', '已通过'],
    ['returned', '已退回'], ['skipped', '已跳过'], ['awaiting_reassignment', '待改派']
  ])('renders real task status %s', (status, label) => {
    const wrapper = mount(WorkflowTimeline, { props: { tasks: [{ ...tasks[0], status, actions: [] }] } })
    expect(wrapper.text()).toContain(label)
  })

  it('renders a directional empty state without inventing pending nodes', () => {
    const wrapper = mount(WorkflowTimeline, { props: { tasks: [] } })
    expect(wrapper.text()).toContain('暂无可展示的岗位责任轨道')
    expect(wrapper.findAll('[data-task-row]')).toHaveLength(0)
  })
})
