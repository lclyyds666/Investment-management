import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AssignmentsView from './assignments.vue'

const { api, store } = vi.hoisted(() => ({ api: { getUserAssignments: vi.fn(), replaceUserAssignments: vi.fn() }, store: { positions: [{ code: 'supply.business_handler', name: '业务经办', category: 'business' }, { code: 'external.legal_counsel', name: '外聘法律顾问', category: 'external' }], tree: [{ code: 'supplymanagement', name: '供应链公司', children: [] }, { code: 'external.legal', name: '外聘法务', children: [] }], loadTree: vi.fn(), loadPositions: vi.fn() } }))
vi.mock('@/api/organization', () => api)
vi.mock('@/store/organization', () => ({ useOrganizationStore: () => store }))
vi.mock('element-plus', async importOriginal => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/system/assignments', component: AssignmentsView }] })
const stubs = { ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElInput: true, ElSelect: true, ElOption: true, ElDatePicker: true }

describe('AssignmentsView', () => {
  beforeEach(async () => { vi.clearAllMocks(); store.loadTree.mockResolvedValue(); store.loadPositions.mockResolvedValue(); api.getUserAssignments.mockResolvedValue([]); await router.push('/system/assignments?user_id=12'); await router.isReady() })
  it('adds multiple assignments for one user and preserves same-company rows', async () => {
    const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises()
    await wrapper.get('[data-testid="add-assignment"]').trigger('click'); await wrapper.get('[data-testid="add-assignment"]').trigger('click')
    expect(wrapper.findAll('[data-testid="assignment-row"]')).toHaveLength(2)
    wrapper.vm.assignments[0].organization_code = 'supplymanagement'; wrapper.vm.assignments[1].organization_code = 'supplymanagement'
    expect(wrapper.vm.assignments.map(item => item.organization_code)).toEqual(['supplymanagement', 'supplymanagement'])
  })
  it('requires external legal term and provider fields', async () => {
    const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); wrapper.vm.addAssignment()
    Object.assign(wrapper.vm.assignments[0], { organization_code: 'external.legal', position_code: 'external.legal_counsel', valid_from: '2026-01-01' }); wrapper.vm.reason = '任职调整'
    await wrapper.vm.save()
    expect(api.replaceUserAssignments).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="user-permission-selector"]').exists()).toBe(false)
  })
  it('highlights both conflict rows from the 409 assignment ids', async () => {
    const { ElMessageBox } = await import('element-plus'); ElMessageBox.confirm.mockResolvedValue(); api.replaceUserAssignments.mockRejectedValue({ response: { data: { detail: { code: 'assignment_workflow_conflict', message: 'workflow conflict', assignment_ids: [3, 4] } } } })
    const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); wrapper.vm.assignments = [{ id: 3, ...wrapper.vm.assignments[0] }, { id: 4, ...wrapper.vm.assignments[0] }]; wrapper.vm.reason = '任职调整'
    await wrapper.vm.save()
    expect(wrapper.findAll('.assignment-row.conflict')).toHaveLength(2)
  })
})
