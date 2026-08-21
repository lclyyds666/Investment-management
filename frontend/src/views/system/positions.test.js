import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PositionsView from './positions.vue'

const { api, store, defaultPositions } = vi.hoisted(() => {
  const defaultPositions = [{ id: 7, code: 'supply.business_handler', name: '业务经办', category: 'business', is_active: true, permissions: [{ permission_code: 'investment.legal.contracts.view', data_scope: 'company', scope_ref: 'supplymanagement' }] }]
  return { api: { createPosition: vi.fn(), updatePosition: vi.fn(), replacePositionPermissions: vi.fn() }, defaultPositions, store: { positions: defaultPositions, permissions: [{ code: 'investment.legal.contracts.view', name: '法务合同查看', resource: 'investment.legal.contracts', resource_name: '法务合同' }, { code: 'supply.portal.enter', name: '供应链门户', resource: 'supply.portal', resource_name: '供管平台' }], tree: [{ code: 'supplymanagement', name: '供应链公司', organization_type: 'company', is_active: true, children: [] }], loadPositions: vi.fn(), loadPermissions: vi.fn(), loadTree: vi.fn() } }
})
vi.mock('@/api/organization', () => api)
vi.mock('@/store/organization', async importOriginal => ({ ...await importOriginal(), useOrganizationStore: () => store }))
vi.mock('element-plus', async importOriginal => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))
const stubs = { ElTable: { props: ['data'], template: '<div>{{ data.map(item => item.name).join("|") }}<slot :row="data[0]" /></div>' }, ElTableColumn: true, ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElInput: { props: ['modelValue'], template: '<span>{{ modelValue }}</span>' }, ElSelect: { template: '<div><slot /></div>' }, ElOption: { props: ['label'], template: '<span>{{ label }}</span>' }, ElOptionGroup: { props: ['label'], template: '<section><span>{{ label }}</span><slot /></section>' }, ElForm: true, ElFormItem: true, ElSwitch: true, ElTag: true, ElDrawer: { template: '<div><slot /></div>' } }

describe('PositionsView', () => {
  beforeEach(() => { vi.clearAllMocks(); store.positions = defaultPositions.map(position => ({ ...position, permissions: [...position.permissions] })); store.loadPositions.mockResolvedValue(); store.loadPermissions.mockResolvedValue(); store.loadTree.mockResolvedValue(); api.updatePosition.mockResolvedValue({ id: 7 }); api.replacePositionPermissions.mockResolvedValue([]) })
  it('shows saved permission counts without a user selector', async () => { const wrapper = mount(PositionsView, { global: { stubs } }); await flushPromises(); expect(wrapper.text()).toContain('已配置 1 项权限'); expect(wrapper.find('[data-testid="user-permission-selector"]').exists()).toBe(false) })
  it('saves metadata without replacing permissions', async () => { const wrapper = mount(PositionsView, { global: { stubs } }); await flushPromises(); wrapper.vm.reason = '岗位信息调整'; await wrapper.vm.saveMetadata(); expect(api.updatePosition).toHaveBeenCalledWith(7, expect.objectContaining({ code: 'supply.business_handler' }), '岗位信息调整'); expect(api.replacePositionPermissions).not.toHaveBeenCalled() })
  it('reports permission failure without claiming metadata success', async () => { const { ElMessage, ElMessageBox } = await import('element-plus'); ElMessageBox.confirm.mockResolvedValue(); api.replacePositionPermissions.mockRejectedValue({ response: { data: { detail: { message: 'scope invalid' } } } }); const wrapper = mount(PositionsView, { global: { stubs } }); await flushPromises(); wrapper.vm.reason = '模板调整'; await wrapper.vm.savePermissions(); expect(ElMessage.success).not.toHaveBeenCalledWith('岗位信息已保存'); expect(ElMessage.error).toHaveBeenCalledWith('scope invalid') })
  it('normalizes portal and own scopes before sending a template', async () => { const { ElMessageBox } = await import('element-plus'); ElMessageBox.confirm.mockResolvedValue(); const wrapper = mount(PositionsView, { global: { stubs } }); await flushPromises(); wrapper.vm.reason = '模板调整'; wrapper.vm.form.permissions = [{ permission_code: 'supply.portal.enter', data_scope: 'platform', scope_ref: '' }, { permission_code: 'supply.contract.view', data_scope: 'own', scope_ref: 'bad' }]; wrapper.vm.normalizeScope(wrapper.vm.form.permissions[0]); wrapper.vm.normalizeScope(wrapper.vm.form.permissions[1]); await wrapper.vm.savePermissions(); expect(api.replacePositionPermissions).toHaveBeenCalledWith(7, [{ permission_code: 'supply.portal.enter', data_scope: 'platform', scope_ref: 'supplymanagement' }, { permission_code: 'supply.contract.view', data_scope: 'own', scope_ref: '' }], '模板调整') })
  it('renders Chinese category scope and resource labels', async () => { const wrapper = mount(PositionsView, { global: { stubs } }); await flushPromises(); expect(wrapper.text()).toContain('业务'); expect(wrapper.text()).toContain('公司'); expect(wrapper.text()).toContain('法务合同'); expect(wrapper.text()).not.toContain('business_domain'); expect(wrapper.text()).not.toContain('investment.legal.contracts'); expect(wrapper.text()).not.toContain('业务经办') })
  it('renders canonical catalog names for legacy API position names', async () => {
    store.positions = [
      { id: 1, code: 'governance.supply_leader', name: '供应链分管领导', category: 'governance', permissions: [] },
      { id: 2, code: 'investment.department.deputy_director', name: '部门副总监', category: 'department', permissions: [] },
      { id: 3, code: 'investment.department.director', name: '部门总监', category: 'department', permissions: [] },
      { id: 4, code: 'supply.company_leader', name: '供应链公司负责人', category: 'business', permissions: [] },
      { id: 5, code: 'supply.business_handler', name: '业务经办', category: 'business', permissions: [] },
      { id: 6, code: 'supply.business_reviewer', name: '业务复核', category: 'business', permissions: [] },
      { id: 7, code: 'supply.finance_handler', name: '财务经办', category: 'business', permissions: [] },
      { id: 8, code: 'investment.duty.supply_risk_review', name: '风控审核', category: 'duty', permissions: [] },
      { id: 9, code: 'investment.duty.supply_finance_review', name: '财务复核', category: 'duty', permissions: [] }
    ]

    const wrapper = mount(PositionsView, { global: { stubs } })
    await flushPromises()

    expect(wrapper.text()).toContain('供管公司分管领导')
    expect(wrapper.text()).toContain('部门副主任')
    expect(wrapper.text()).toContain('部门主任')
    expect(wrapper.text()).toContain('供管公司负责人')
    expect(wrapper.text()).toContain('供管公司初级经理')
    expect(wrapper.text()).toContain('供管公司中级经理')
    expect(wrapper.text()).toContain('投资公司资产财务部初级经理')
    expect(wrapper.text()).toContain('投资公司法务风控部主任')
    expect(wrapper.text()).toContain('投资公司资产财务部主任')
    expect(wrapper.vm.form.name).toBe('供管公司分管领导')
    for (const legacyName of ['供应链分管领导', '部门副总监', '部门总监', '供应链公司负责人', '业务经办', '业务复核', '财务经办', '风控审核', '财务复核']) {
      expect(wrapper.text()).not.toContain(legacyName)
    }
  })
})
