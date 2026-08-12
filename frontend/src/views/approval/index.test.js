import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const approvalApi = vi.hoisted(() => ({
  listForms: vi.fn(), createForm: vi.fn(), updateForm: vi.fn(), deleteForm: vi.fn(), submitForm: vi.fn(), uploadFormAttachment: vi.fn(),
  approveForm: vi.fn(), rejectForm: vi.fn(), listActions: vi.fn(), proofreadForm: vi.fn(), downloadFormPrint: vi.fn(), getForm: vi.fn(), fetchFormAttachmentBlob: vi.fn()
}))
const badgeStore = vi.hoisted(() => ({ refresh: vi.fn() }))
vi.mock('@/api/approval', () => approvalApi)
vi.mock('@/api/customer', () => ({ listCustomers: vi.fn(() => Promise.resolve([])) }))
vi.mock('@/store/portal', () => ({ usePortalStore: () => ({ hasPermission: () => true }) }))
vi.mock('@/store/approvalBadge', () => ({ useApprovalBadgeStore: () => badgeStore }))
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: () => true, canActOnWorkflow: () => false }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))

import ApprovalView from './index.vue'

describe('approval form designated submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    approvalApi.listForms.mockResolvedValue([])
    approvalApi.submitForm.mockResolvedValue({})
  })

  it.each([
    ['payment', 'supply.payment.v2'],
    ['business', 'supply.business.v2']
  ])('submits %s forms with two designated users through the matching workflow', async (formType, workflowCode) => {
    const wrapper = shallowMount(ApprovalView)
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 9, status: 'draft', form_type: formType, workflow_instance_id: null })
    expect(wrapper.vm.submitWorkflowCode).toBe(workflowCode)
    expect(approvalApi.submitForm).not.toHaveBeenCalled()

    wrapper.vm.selectedApprovers = { company_leader: 11, supply_governance_leader: 31 }
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.confirmSubmit()
    expect(approvalApi.submitForm).toHaveBeenCalledWith(9, { designated_users: { company_leader: 11, supply_governance_leader: 31 } })
  })

  it('resubmits an active handler task with an empty payload', async () => {
    const wrapper = shallowMount(ApprovalView)
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 10, form_type: 'business', status: 'rejected', workflow_instance_id: 45, active_task: { node_code: 'handler' } })
    expect(approvalApi.submitForm).toHaveBeenCalledWith(10, undefined)
  })
})
