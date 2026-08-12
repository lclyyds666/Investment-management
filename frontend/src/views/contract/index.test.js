import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const contractApi = vi.hoisted(() => ({
  listContracts: vi.fn(), createContract: vi.fn(), updateContract: vi.fn(), deleteContract: vi.fn(), submitContract: vi.fn(),
  uploadContractAttachment: vi.fn(), approveContract: vi.fn(), rejectContract: vi.fn(), aiReviewContract: vi.fn(), fetchContractAttachmentBlob: vi.fn()
}))
const badgeStore = vi.hoisted(() => ({ refresh: vi.fn() }))
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/api/customer', () => ({ listCustomers: vi.fn(() => Promise.resolve([])) }))
vi.mock('@/api/knowledge', () => ({ listKnowledge: vi.fn(), uploadKnowledge: vi.fn(), deleteKnowledge: vi.fn() }))
vi.mock('@/store/portal', () => ({ usePortalStore: () => ({ hasPermission: () => true }) }))
vi.mock('@/store/approvalBadge', () => ({ useApprovalBadgeStore: () => badgeStore }))
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: () => true, canActOnWorkflow: () => false }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))

import ContractView from './index.vue'

describe('contract designated submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contractApi.listContracts.mockResolvedValue([])
    contractApi.submitContract.mockResolvedValue({})
  })

  it('blocks first submission until the selector validates and sends designated users', async () => {
    const wrapper = shallowMount(ContractView)
    await flushPromises()
    const row = { id: 7, status: 'draft', workflow_instance_id: null }
    await wrapper.vm.onSubmit(row)
    expect(contractApi.submitContract).not.toHaveBeenCalled()

    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(false) }
    await wrapper.vm.confirmSubmit()
    expect(contractApi.submitContract).not.toHaveBeenCalled()

    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.confirmSubmit()
    expect(contractApi.submitContract).toHaveBeenCalledWith(7, { designated_users: { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 } })
  })

  it('resubmits an active handler task without forcing approver reselection', async () => {
    const wrapper = shallowMount(ContractView)
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 8, status: 'rejected', workflow_instance_id: 44, active_task: { node_code: 'handler' } })
    expect(contractApi.submitContract).toHaveBeenCalledWith(8, undefined)
  })

  it('reloads candidates after an eligibility conflict and preserves the dialog', async () => {
    contractApi.submitContract.mockRejectedValueOnce({ response: { status: 422 } })
    const wrapper = shallowMount(ContractView)
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 9, status: 'draft', workflow_instance_id: null })
    const reloadCandidates = vi.fn().mockResolvedValue(true)
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true), reloadCandidates }
    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }

    await wrapper.vm.confirmSubmit()

    expect(reloadCandidates).toHaveBeenCalledWith({ preserve: true })
    expect(wrapper.vm.submitVisible).toBe(true)
  })
})
