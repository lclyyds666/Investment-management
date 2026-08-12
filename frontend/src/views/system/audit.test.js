import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AuditView from './audit.vue'
import * as api from '@/api/audit'

vi.mock('@/api/audit')
vi.mock('@/utils/file', () => ({ downloadBlob: vi.fn() }))
const stubs = { ElCard: { template: '<section><slot name="header" /><slot /></section>' }, ElIcon: true, ElForm: { template: '<form><slot /></form>' }, ElFormItem: true, ElInput: true, ElSelect: true, ElOption: true, ElDatePicker: true, ElButton: true, ElTable: { props: ['data'], template: '<div><slot v-for="row in data" :row="row" /></div>' }, ElTableColumn: { template: '<div><slot :row="$parent.data?.[0]" /></div>' }, ElTag: { template: '<span><slot /></span>' }, ElPagination: true }

describe('authorization audit display', () => {
  beforeEach(() => { vi.resetAllMocks(); api.getAuditMeta.mockResolvedValue({ actions: [], modules: [] }); api.listAuditLogs.mockResolvedValue({ total: 1, items: [{ id: 9, module: 'organization_authorization', action: 'assignment_replace', full_name: '管理员', username: 'admin', position_name: '信息维护', target_desc: 'user#24', reason: '岗位调整', before_json: [{ organization_code: 'supplymanagement', position_code: 'supply.business_handler' }], after_json: [{ organization_code: 'supplymanagement', position_code: 'supply.company_leader' }], created_at: '2026-08-12T09:30:00', status: 'success' }] }) })
  it('renders actor snapshot, target, reason, timestamp, and before-after position tags', async () => { const wrapper = mount(AuditView, { global: { stubs } }); await flushPromises(); expect(wrapper.text()).toContain('管理员'); expect(wrapper.text()).toContain('信息维护'); expect(wrapper.text()).toContain('目标用户：user#24'); expect(wrapper.text()).toContain('岗位调整'); expect(wrapper.text()).toContain('supplymanagement / supply.business_handler'); expect(wrapper.text()).toContain('supplymanagement / supply.company_leader'); expect(wrapper.text()).toContain('2026-08-12 09:30:00'); expect(wrapper.find('[data-testid="authorization-audit-detail"]').exists()).toBe(true) })
})
