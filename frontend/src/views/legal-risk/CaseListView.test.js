import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseListView from './CaseListView.vue'

const mocks = vi.hoisted(() => ({
  listCases: vi.fn(),
  push: vi.fn(),
  route: { query: { status: 'enforcement' } }
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
  usePortalStore: () => ({
    assignments: [{ position_code: 'investment.department.junior_manager' }],
    companyRole: () => 'business_handler',
    isSuperuser: false
  })
}))

describe('legal case list drilldown filters', () => {
  beforeEach(() => {
    mocks.listCases.mockReset().mockResolvedValue({ items: [], total: 0 })
  })

  it('loads the status passed by the statistics drilldown route', async () => {
    shallowMount(CaseListView)
    await flushPromises()

    expect(mocks.listCases).toHaveBeenCalledWith(expect.objectContaining({
      status: 'enforcement'
    }))
  })
})
