import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const approvalApi = vi.hoisted(() => ({
  listForms: vi.fn(), createForm: vi.fn(), updateForm: vi.fn(), deleteForm: vi.fn(), submitForm: vi.fn(), uploadFormAttachment: vi.fn(),
  approveForm: vi.fn(), rejectForm: vi.fn(), listActions: vi.fn(), proofreadForm: vi.fn(), downloadFormPrint: vi.fn(), getForm: vi.fn(), fetchFormAttachmentBlob: vi.fn()
}))
const workflowApi = vi.hoisted(() => ({ listWorkflowCandidates: vi.fn(() => Promise.resolve([])) }))
const badgeStore = vi.hoisted(() => ({ refresh: vi.fn() }))
vi.mock('@/api/approval', () => approvalApi)
vi.mock('@/api/customer', () => ({ listCustomers: vi.fn(() => Promise.resolve([])) }))
vi.mock('@/api/workflow', () => workflowApi)
vi.mock('@/components/workflow/DesignatedApproverFields.vue', () => ({
  default: {
    props: ['workflowCode'],
    async mounted() { await workflowApi.listWorkflowCandidates(this.workflowCode, 'company_leader') },
    template: '<div data-testid="selector-stub" />'
  }
}))
vi.mock('@/store/portal', () => ({ usePortalStore: () => ({ hasPermission: () => true }) }))
vi.mock('@/store/user', () => ({ useUserStore: () => ({ userInfo: { id: 99 } }) }))
vi.mock('@/store/approvalBadge', () => ({ useApprovalBadgeStore: () => badgeStore }))
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: () => true, canActOnWorkflow: () => false }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))

import ApprovalView from './index.vue'

function mountView() {
  return shallowMount(ApprovalView, {
    global: {
      stubs: {
        ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
        DesignatedApproverFields: false
      }
    }
  })
}

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
    const wrapper = mountView()
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
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 10, form_type: 'business', status: 'rejected', workflow_instance_id: 45, active_task: { node_code: 'handler' } })
    expect(approvalApi.submitForm).toHaveBeenCalledWith(10, undefined)
  })

  it('only mounts the candidate selector while open and reloads it when reopened', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).not.toHaveBeenCalled()

    await wrapper.vm.onSubmit({ id: 11, status: 'draft', form_type: 'payment', workflow_instance_id: null })
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).toHaveBeenCalledTimes(1)

    wrapper.vm.submitVisible = false
    await wrapper.vm.$nextTick()
    await wrapper.vm.onSubmit({ id: 11, status: 'draft', form_type: 'payment', workflow_instance_id: null })
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).toHaveBeenCalledTimes(2)
  })

  it('sends one request when confirm is invoked concurrently', async () => {
    let resolveSubmit
    approvalApi.submitForm.mockImplementationOnce(() => new Promise((resolve) => { resolveSubmit = resolve }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 12, status: 'draft', form_type: 'business', workflow_instance_id: null })
    wrapper.vm.selectedApprovers = { company_leader: 11, supply_governance_leader: 31 }
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true) }

    const first = wrapper.vm.confirmSubmit()
    const second = wrapper.vm.confirmSubmit()
    await flushPromises()
    expect(approvalApi.submitForm).toHaveBeenCalledTimes(1)
    resolveSubmit({})
    await Promise.all([first, second])
  })
})
