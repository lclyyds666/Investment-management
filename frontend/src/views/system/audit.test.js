import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AuditView from './audit.vue'
import * as api from '@/api/audit'
import * as workflowApi from '@/api/workflow'

vi.mock('@/api/audit'); vi.mock('@/utils/file', () => ({ downloadBlob: vi.fn() }))
vi.mock('@/api/workflow')
const stubs = { ElCard: { template: '<section><slot name="header" /><slot /></section>' }, ElAlert: { props: ['title'], template: '<div>{{ title }}</div>' }, ElIcon: true, ElForm: { template: '<form><slot /></form>' }, ElFormItem: true, ElInput: true, ElSelect: true, ElOption: true, ElDatePicker: true, ElButton: true, ElTable: { props: ['data'], template: '<div><slot v-for="row in data" :row="row" /></div>' }, ElTableColumn: { template: '<div><slot :row="$parent.data?.[0]" /></div>' }, ElTag: { template: '<span><slot /></span>' }, ElPagination: true }
const authorization = (action, target_desc, before_json, after_json) => ({ id: action, module: 'organization_authorization', action, full_name: '管理员', username: 'admin', position_name: '信息维护', target_desc, reason: '调整原因', before_json, after_json, created_at: '2026-08-12T09:30:00', status: 'success' })
async function mountRows(items, reassignmentAudits = []) { api.getAuditMeta.mockResolvedValue({ actions: [], modules: [] }); api.listAuditLogs.mockResolvedValue({ total: items.length, items }); workflowApi.listReassignmentAudits.mockResolvedValue({ items: reassignmentAudits, total: reassignmentAudits.length }); const wrapper = mount(AuditView, { global: { stubs } }); await flushPromises(); return wrapper }

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('authorization audit display', () => {
  beforeEach(() => vi.resetAllMocks())
  it('renders assignment replacement details without raw JSON', async () => { const wrapper = await mountRows([authorization('assignment_replace', 'user#24', [{ organization_code: 'supplymanagement', position_code: 'supply.business_handler', status: 'active', valid_from: '2026-01-01', governance_scopes: [{ scope_type: 'company', scope_ref: 'supplymanagement' }] }], [{ organization_code: 'supplymanagement', position_code: 'supply.company_leader', valid_from: '2026-02-01', valid_until: '2026-12-31', external: { provider_name: 'Firm', service_scopes: ['review'] } }])]); expect(wrapper.text()).toContain('管理员'); expect(wrapper.text()).toContain('信息维护'); expect(wrapper.text()).toContain('目标用户：user#24'); expect(wrapper.text()).toContain('调整原因'); expect(wrapper.text()).toContain('supplymanagement / supply.business_handler'); expect(wrapper.text()).toContain('2026-01-01'); expect(wrapper.text()).toContain('Firm'); expect(wrapper.html()).not.toContain('before_json') })
  it('renders assignment termination as removed', async () => { const wrapper = await mountRows([authorization('assignment_terminate', 'user#24', [{ organization_code: 'supplymanagement', position_code: 'supply.business_handler' }], [])]); expect(wrapper.text()).toContain('已移除') })
  it('renders an empty replacement state as none', async () => { const wrapper = await mountRows([authorization('assignment_replace', 'user#24', [], [])]); expect(wrapper.text()).toContain('无') })
  it.each([
    ['organization_update', 'organization#5', { code: 'supplymanagement', name: '供应链', organization_type: 'company', parent_code: 'investment', company_code: 'supplymanagement', is_active: true, sort_order: 20 }, '组织：supplymanagement / 供应链'],
    ['position_update', 'position#7', { code: 'supply.business_handler', name: '业务经办', category: 'business', is_active: true }, '岗位：supply.business_handler / 业务经办'],
    ['position_create', 'position#8', { code: 'fund.general_manager', name: '基金总经理', category: 'executive', is_active: true }, '岗位：fund.general_manager / 基金总经理 / executive / 启用'],
    ['position_permissions_replace', 'position#7', [{ permission_code: 'supply.contract.view', data_scope: 'company', scope_ref: 'supplymanagement' }], '权限：supply.contract.view / company / supplymanagement']
  ])('renders %s structured snapshots and derived target label', async (action, target, snapshot, text) => { const wrapper = await mountRows([authorization(action, target, snapshot, snapshot)]); expect(wrapper.text()).toContain(text); expect(wrapper.text()).toContain(`${action === 'organization_update' ? '目标组织' : '目标岗位'}：${target}`) })
  it('keeps generic request rows generic', async () => { const wrapper = await mountRows([{ id: 3, module: 'contract', action: 'update', target_desc: '合同#3', method: 'PUT', path: '/contracts/3', ip: '127.0.0.1', status: 'success' }]); expect(wrapper.text()).toContain('合同#3'); expect(wrapper.text()).toContain('PUT /contracts/3'); expect(wrapper.find('[data-testid="authorization-audit-detail"]').exists()).toBe(false) })
  it('renders structured reassignment audits', async () => { const wrapper = await mountRows([], [{ id: 8, old_assignee_name: '原负责人', new_assignee_name: '新负责人', required_position_name: '供应链公司负责人', operator_name: '信息维护员', reason: '原任职失效', created_at: '2026-08-13T09:00:00' }]); const detail = wrapper.get('[data-testid="reassignment-audits"]'); expect(detail.text()).toContain('原负责人 → 新负责人'); expect(detail.text()).toContain('供应链公司负责人'); expect(detail.text()).toContain('信息维护员'); expect(detail.text()).toContain('原任职失效'); expect(detail.text()).toContain('2026-08-13 09:00:00') })
  it('loads reassignment pages independently from meta failures', async () => { api.getAuditMeta.mockRejectedValue(new Error('meta failed')); api.listAuditLogs.mockResolvedValue({ total: 0, items: [] }); workflowApi.listReassignmentAudits.mockResolvedValue({ items: [{ id: 9, old_assignee_name: '甲', new_assignee_name: '乙', required_position_name: '岗位', operator_name: '超管', reason: '失效', created_at: '2026-08-13T09:00:00' }], total: 21 }); const wrapper = mount(AuditView, { global: { stubs } }); await flushPromises(); expect(wrapper.get('[data-testid="reassignment-audits"]').text()).toContain('甲 → 乙'); expect(wrapper.vm.reassignmentTotal).toBe(21); await wrapper.vm.onReassignmentPage(2); expect(workflowApi.listReassignmentAudits).toHaveBeenLastCalledWith({ page: 2, page_size: 10 }) })
  it('keeps the selected reassignment page when an older page resolves late', async () => {
    const wrapper = await mountRows([], [])
    const pageTwo = deferred()
    const pageThree = deferred()
    workflowApi.listReassignmentAudits.mockImplementation(({ page }) => page === 2 ? pageTwo.promise : pageThree.promise)

    const pageTwoLoad = wrapper.vm.onReassignmentPage(2)
    const pageThreeLoad = wrapper.vm.onReassignmentPage(3)
    pageThree.resolve({ items: [{ id: 30, old_assignee_name: '第三页原负责人', new_assignee_name: '第三页新负责人' }], total: 35 })
    await pageThreeLoad

    expect(wrapper.vm.reassignmentPage).toBe(3)
    expect(wrapper.vm.reassignmentAudits[0].id).toBe(30)
    expect(wrapper.vm.reassignmentLoading).toBe(false)

    pageTwo.resolve({ items: [{ id: 20, old_assignee_name: '第二页原负责人', new_assignee_name: '第二页新负责人' }], total: 35 })
    await pageTwoLoad

    expect(wrapper.vm.reassignmentPage).toBe(3)
    expect(wrapper.vm.reassignmentAudits[0].id).toBe(30)
    expect(wrapper.vm.reassignmentLoading).toBe(false)
    expect(wrapper.vm.reassignmentError).toBe('')
  })
  it('keeps meta when reassignment audit loading fails', async () => { api.getAuditMeta.mockResolvedValue({ actions: [{ value: 'login', label: '登录' }], modules: [] }); api.listAuditLogs.mockResolvedValue({ total: 0, items: [] }); workflowApi.listReassignmentAudits.mockRejectedValue(new Error('audit failed')); const wrapper = mount(AuditView, { global: { stubs } }); await flushPromises(); expect(wrapper.vm.meta.actions[0].label).toBe('登录'); expect(wrapper.vm.reassignmentAudits).toEqual([]); expect(wrapper.vm.reassignmentError).toBe('改派审计加载失败'); expect(wrapper.text()).toContain('改派审计加载失败') })
})
