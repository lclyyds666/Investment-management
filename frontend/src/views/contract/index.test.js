import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const contractApi = vi.hoisted(() => ({
  listContracts: vi.fn(), createContract: vi.fn(), updateContract: vi.fn(), deleteContract: vi.fn(), submitContract: vi.fn(),
  uploadContractAttachment: vi.fn(), approveContract: vi.fn(), rejectContract: vi.fn(), aiReviewContract: vi.fn(), fetchContractAttachmentBlob: vi.fn()
}))
const workflowApi = vi.hoisted(() => ({ listWorkflowCandidates: vi.fn(() => Promise.resolve([])), getWorkflowTimeline: vi.fn() }))
const badgeStore = vi.hoisted(() => ({ refresh: vi.fn() }))
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/api/customer', () => ({ listCustomers: vi.fn(() => Promise.resolve([])) }))
vi.mock('@/api/knowledge', () => ({ listKnowledge: vi.fn(), uploadKnowledge: vi.fn(), deleteKnowledge: vi.fn() }))
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
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: () => true }))
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: messages, ElMessageBox: { confirm: vi.fn() } }))

import ContractView from './index.vue'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mountView() {
  return shallowMount(ContractView, {
    global: {
      stubs: {
        ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
        DesignatedApproverFields: false
      }
    }
  })
}

describe('contract designated submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contractApi.listContracts.mockResolvedValue([])
    contractApi.submitContract.mockResolvedValue({})
  })

  it('blocks first submission until the selector validates and sends designated users', async () => {
    const wrapper = mountView()
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
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 8, status: 'rejected', workflow_instance_id: 44, active_task: { node_code: 'handler' } })
    expect(contractApi.submitContract).toHaveBeenCalledWith(8, undefined)
  })

  it('reloads candidates after an eligibility conflict and preserves the dialog', async () => {
    contractApi.submitContract.mockRejectedValueOnce({ response: { status: 422 } })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 9, status: 'draft', workflow_instance_id: null })
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true), reloadCandidates: vi.fn().mockResolvedValue(true) }
    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }

    await wrapper.vm.confirmSubmit()

    expect(wrapper.vm.submitVisible).toBe(true)
  })

  it('only mounts the candidate selector while open and reloads it when reopened', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).not.toHaveBeenCalled()

    await wrapper.vm.onSubmit({ id: 11, status: 'draft', workflow_instance_id: null })
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).toHaveBeenCalledTimes(1)

    wrapper.vm.submitVisible = false
    await wrapper.vm.$nextTick()
    await wrapper.vm.onSubmit({ id: 11, status: 'draft', workflow_instance_id: null })
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).toHaveBeenCalledTimes(2)
  })

  it('sends one request when confirm is invoked concurrently', async () => {
    let resolveSubmit
    contractApi.submitContract.mockImplementationOnce(() => new Promise((resolve) => { resolveSubmit = resolve }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 12, status: 'draft', workflow_instance_id: null })
    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true) }

    const first = wrapper.vm.confirmSubmit()
    const second = wrapper.vm.confirmSubmit()
    await flushPromises()
    expect(contractApi.submitContract).toHaveBeenCalledTimes(1)
    resolveSubmit({})
    await Promise.all([first, second])
  })
})

describe('contract active-task actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contractApi.listContracts.mockResolvedValue([])
  })

  it('shows actions only from active_task and can_act, including shared and designated tasks', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.vm.canApprove({ active_task: { mode: 'shared_position' }, can_act: true })).toBe(true)
    expect(wrapper.vm.canApprove({ active_task: { mode: 'designated_user', designated_user: { full_name: '指定领导' } }, can_act: false })).toBe(false)
    expect(wrapper.vm.canApprove({ active_task: { mode: 'designated_user', designated_user: { full_name: '指定领导' } }, can_act: true })).toBe(true)
    expect(wrapper.vm.canApprove({ active_task: null, can_act: true })).toBe(false)
  })

  it('closes and refreshes after a completed-task conflict', async () => {
    contractApi.approveContract.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'task_already_completed', actor: '王审批' } } } })
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openAction({ id: 7, active_task: { id: 71 }, can_act: true }, 'approve')
    wrapper.vm.actionFormRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.confirmAction()
    expect(wrapper.vm.actionVisible).toBe(false)
    expect(contractApi.listContracts).toHaveBeenCalledTimes(2)
    expect(messages.warning).toHaveBeenCalledWith('该节点已由 王审批 办理')
  })

  it('sends one action request when validation is still pending', async () => {
    const validation = deferred()
    contractApi.approveContract.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openAction({ id: 8, active_task: { id: 81 }, can_act: true }, 'approve')
    const validate = vi.fn(() => validation.promise)
    wrapper.vm.actionFormRef = { validate }

    const first = wrapper.vm.confirmAction()
    const second = wrapper.vm.confirmAction()
    validation.resolve(true)
    await Promise.all([first, second])

    expect(validate).toHaveBeenCalledTimes(1)
    expect(contractApi.approveContract).toHaveBeenCalledTimes(1)
  })
})
