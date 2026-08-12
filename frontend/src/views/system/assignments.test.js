import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AssignmentsView from './assignments.vue'

const { api, workflowApi, store } = vi.hoisted(() => ({ api: { getUserAssignments: vi.fn(), replaceUserAssignments: vi.fn() }, workflowApi: { listAwaitingReassignmentTasks: vi.fn() }, store: { positions: [{ code: 'supply.business_handler', name: '业务经办', category: 'business' }, { code: 'governance.supply_leader', name: '供应链分管领导', category: 'governance' }, { code: 'external.legal_counsel', name: '外聘法律顾问', category: 'external' }], tree: [{ code: 'supplymanagement', name: '供应链公司', children: [] }, { code: 'external.legal', name: '外聘法务', children: [] }], loadTree: vi.fn(), loadPositions: vi.fn() } }))
vi.mock('@/api/organization', () => api); vi.mock('@/store/organization', () => ({ useOrganizationStore: () => store })); vi.mock('element-plus', async importOriginal => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))
vi.mock('@/api/workflow', () => workflowApi)
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/system/assignments', component: AssignmentsView }] }); const stubs = { ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElInput: true, ElSelect: true, ElOption: true, ElDatePicker: true, ElTag: true }

describe('AssignmentsView', () => {
  beforeEach(async () => { vi.clearAllMocks(); store.loadTree.mockResolvedValue(); store.loadPositions.mockResolvedValue(); api.getUserAssignments.mockResolvedValue([]); workflowApi.listAwaitingReassignmentTasks.mockResolvedValue([{ id: 41, target_title: '年度框架合同', node_name: '公司负责人审批', previous_assignee: { full_name: '原负责人' }, invalidation_reason: '原岗位任职失效', activated_at: '2026-08-13T09:00:00', required_position_name: '公司负责人' }]); await router.push('/system/assignments?user_id=12'); await router.isReady() })
  it('renders a governance-only reassignment queue without business actions', async () => { const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); expect(wrapper.get('[data-testid="reassignment-queue"]').text()).toContain('年度框架合同'); expect(wrapper.text()).toContain('改派'); expect(wrapper.text()).not.toContain('通过'); expect(wrapper.text()).not.toContain('退回') })
  it('loads assignments when the reassignment queue fails', async () => {
    workflowApi.listAwaitingReassignmentTasks.mockRejectedValue(new Error('queue unavailable'))
    api.getUserAssignments.mockResolvedValue([{ id: 52, organization_code: 'supplymanagement', position_code: 'supply.business_handler', valid_from: '2026-01-01', status: 'active' }])

    const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } })
    await flushPromises()

    expect(api.getUserAssignments).toHaveBeenCalledWith('12')
    expect(wrapper.vm.assignments).toHaveLength(1)
    expect(wrapper.vm.assignments[0].id).toBe(52)
    expect(wrapper.vm.reassignmentLoading).toBe(false)
    expect(wrapper.vm.reassignmentError).toBe('待改派任务加载失败')
  })
  it('adds multiple assignments for one user and preserves same-company rows', async () => { const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); await wrapper.get('[data-testid="add-assignment"]').trigger('click'); await wrapper.get('[data-testid="add-assignment"]').trigger('click'); expect(wrapper.findAll('[data-testid="assignment-row"]')).toHaveLength(2); wrapper.vm.assignments.forEach(item => { item.organization_code = 'supplymanagement' }); expect(wrapper.vm.assignments.map(item => item.organization_code)).toEqual(['supplymanagement', 'supplymanagement']) })
  it('requires external legal term and provider fields', async () => { const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); wrapper.vm.addAssignment(); Object.assign(wrapper.vm.assignments[0], { organization_code: 'external.legal', position_code: 'external.legal_counsel', valid_from: '2026-01-01' }); wrapper.vm.reason = '任职调整'; await wrapper.vm.save(); expect(api.replaceUserAssignments).not.toHaveBeenCalled(); expect(wrapper.find('[data-testid="user-permission-selector"]').exists()).toBe(false) })
  it('forces governance assignments to their required company scope', async () => { const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); wrapper.vm.addAssignment(); const assignment = wrapper.vm.assignments[0]; assignment.position_code = 'governance.supply_leader'; assignment.organization_code = 'external.legal'; wrapper.vm.applyGovernanceTarget(assignment); expect(assignment.organization_code).toBe('supplymanagement'); expect(wrapper.vm.assignmentPayload().assignments[0].governance_scopes).toEqual([{ scope_type: 'company', scope_ref: 'supplymanagement' }]) })
  it('highlights unsaved conflict rows from explicit client references', async () => { const { ElMessageBox } = await import('element-plus'); ElMessageBox.confirm.mockResolvedValue(); api.replaceUserAssignments.mockRejectedValue({ response: { data: { detail: { code: 'assignment_workflow_conflict', message: 'workflow conflict', assignment_ids: [], conflicting_client_refs: ['row-3', 'row-4'] } } } }); const wrapper = mount(AssignmentsView, { global: { plugins: [router], stubs } }); await flushPromises(); wrapper.vm.assignments = [{ client_ref: 'row-3', ...wrapper.vm.assignments[0] }, { client_ref: 'row-4', ...wrapper.vm.assignments[0] }]; wrapper.vm.reason = '任职调整'; await wrapper.vm.save(); expect(wrapper.findAll('.assignment-row.conflict')).toHaveLength(2) })
})
