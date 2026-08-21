import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseListView from './CaseListView.vue'

const mocks = vi.hoisted(() => ({
  listCases: vi.fn(),
  push: vi.fn(),
  route: { query: { status: 'enforcement' } },
  portal: {
    assignments: [],
    isSuperuser: false,
    permissionCodes: new Set(),
    hasPermission(code) { return this.isSuperuser || this.permissionCodes.has(code) }
  }
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ push: mocks.push })
}))

vi.mock('@/api/legalRisk', () => ({
  exportCases: vi.fn(),
  listCases: mocks.listCases
}))

vi.mock('@/store/portal', () => ({
  usePortalStore: () => mocks.portal
}))

describe('legal case list drilldown filters', () => {
  beforeEach(() => {
    mocks.listCases.mockReset().mockResolvedValue({ items: [], total: 0 })
    mocks.portal.assignments = [{ organization_code: 'investment.legal_risk' }]
    mocks.portal.permissionCodes = new Set([
      'investment.legal.cases.view',
      'investment.legal.cases.create',
      'investment.legal.cases.update',
      'investment.legal.cases.import',
      'investment.legal.cases.export'
    ])
  })

  it('loads the status passed by the statistics drilldown route', async () => {
    shallowMount(CaseListView)
    await flushPromises()

    expect(mocks.listCases).toHaveBeenCalledWith(expect.objectContaining({
      status: 'enforcement'
    }))
  })

  it('renders company and initiator organization columns', async () => {
    const wrapper = shallowMount(CaseListView, {
      global: { stubs: { ElTable: { template: '<div><slot /></div>' } } }
    })
    await flushPromises()

    expect(wrapper.html()).toContain('所属公司')
    expect(wrapper.html()).toContain('发起组织')
  })

  it('shows ownership filters to legal department users', async () => {
    const wrapper = shallowMount(CaseListView)
    await flushPromises()

    expect(wrapper.html()).toContain('placeholder="所属公司"')
    expect(wrapper.html()).toContain('placeholder="发起组织"')
  })

  it.each([
    ['新华岗位', 'xinhuaproperty.department.employee'],
    ['展威岗位', 'zhanwei.junior_manager'],
    ['新增投资岗位', 'investment.asset_finance.middle_manager']
  ])('shows create and update actions for %s from its permission snapshot', async (_label, positionCode) => {
    mocks.portal.assignments = [{ position_code: positionCode }]
    mocks.portal.permissionCodes = new Set([
      'investment.legal.cases.view',
      'investment.legal.cases.create',
      'investment.legal.cases.update'
    ])
    const wrapper = shallowMount(CaseListView)
    await flushPromises()

    expect(wrapper.vm.canCreate).toBe(true)
    expect(wrapper.vm.canWrite).toBe(true)
  })

  it('hides every case action whose exact permission is absent', async () => {
    mocks.portal.permissionCodes = new Set(['investment.legal.cases.view'])
    const wrapper = shallowMount(CaseListView)
    await flushPromises()

    expect(wrapper.vm.canCreate).toBe(false)
    expect(wrapper.vm.canWrite).toBe(false)
    expect(wrapper.vm.canImport).toBe(false)
    expect(wrapper.vm.canExport).toBe(false)
  })
})
