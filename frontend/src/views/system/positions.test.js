import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PositionsView from './positions.vue'

const { api, store } = vi.hoisted(() => ({ api: { createPosition: vi.fn(), updatePosition: vi.fn(), replacePositionPermissions: vi.fn() }, store: {
  positions: [{ id: 7, code: 'supply.business_handler', name: '业务经办', category: 'business', is_active: true, permissions: [{ permission_code: 'supply.contract.view', data_scope: 'company', scope_ref: 'supplymanagement' }] }],
  permissions: [{ code: 'supply.contract.view', name: '查看合同', resource: 'supply.contract' }],
  loadPositions: vi.fn(), loadPermissions: vi.fn()
} }))
vi.mock('@/api/organization', () => api)
vi.mock('@/store/organization', () => ({ useOrganizationStore: () => store }))
vi.mock('element-plus', async importOriginal => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))

const stubs = { ElTable: { props: ['data'], emits: ['row-click'], template: '<div><slot :row="data[0]" /><button @click="$emit(\'row-click\', data[0])">row</button></div>' }, ElTableColumn: true, ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElInput: true, ElSelect: true, ElOption: true, ElOptionGroup: true, ElForm: true, ElFormItem: true, ElSwitch: true, ElTag: true, ElDrawer: { template: '<div><slot /></div>' } }

describe('PositionsView', () => {
  beforeEach(() => { vi.clearAllMocks(); store.loadPositions.mockResolvedValue(); store.loadPermissions.mockResolvedValue(); api.updatePosition.mockResolvedValue({ id: 7 }); api.replacePositionPermissions.mockResolvedValue([]) })
  it('shows saved permission counts without a user selector', async () => {
    const wrapper = mount(PositionsView, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('已配置 1 项权限')
    expect(wrapper.find('[data-testid="user-permission-selector"]').exists()).toBe(false)
  })
  it('replaces the complete template only after confirmation and with a reason', async () => {
    const { ElMessageBox } = await import('element-plus'); ElMessageBox.confirm.mockResolvedValue()
    const wrapper = mount(PositionsView, { global: { stubs } }); await flushPromises()
    wrapper.vm.reason = '岗位授权调整'
    await wrapper.vm.save()
    expect(api.updatePosition).toHaveBeenCalledWith(7, expect.objectContaining({ code: 'supply.business_handler' }), '岗位授权调整')
    expect(api.replacePositionPermissions).toHaveBeenCalledWith(7, [{ permission_code: 'supply.contract.view', data_scope: 'company', scope_ref: 'supplymanagement' }], '岗位授权调整')
  })
})
