import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const approvalApi = vi.hoisted(() => ({
  listForms: vi.fn(), createForm: vi.fn(), updateForm: vi.fn(), deleteForm: vi.fn(), submitForm: vi.fn(), uploadFormAttachment: vi.fn(),
  approveForm: vi.fn(), rejectForm: vi.fn(), listActions: vi.fn(), proofreadForm: vi.fn(), downloadFormPrint: vi.fn(), getForm: vi.fn(), fetchFormAttachmentBlob: vi.fn()
}))
const workflowApi = vi.hoisted(() => ({ listWorkflowCandidates: vi.fn(() => Promise.resolve([])), getWorkflowTimeline: vi.fn() }))
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
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: () => true }))
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: messages, ElMessageBox: { confirm: vi.fn() } }))

import ApprovalView from './index.vue'

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

describe('approval active-task actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    workflowApi.getWorkflowTimeline.mockReset()
    approvalApi.listForms.mockResolvedValue([])
  })

  it('does not infer action visibility from role, step, or superuser state', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.vm.canApprove({ active_task: { id: 1 }, can_act: true, current_step: 99 })).toBe(true)
    expect(wrapper.vm.canApprove({ active_task: { id: 2 }, can_act: false, current_step: 0 })).toBe(false)
    expect(wrapper.vm.canApprove({ active_task: null, can_act: true })).toBe(false)
  })

  it('closes and refreshes after another actor completes the task', async () => {
    approvalApi.rejectForm.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'task_already_completed', actor: '李复核' } } } })
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openAction({ id: 9, active_task: { id: 91 }, can_act: true }, 'reject')
    wrapper.vm.actionForm.comment = '退回补充'
    wrapper.vm.actionFormRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.confirmAction()
    expect(wrapper.vm.actionVisible).toBe(false)
    expect(approvalApi.listForms).toHaveBeenCalledTimes(2)
    expect(messages.warning).toHaveBeenCalledWith('该节点已由 李复核 办理')
  })

  it('keeps form details visible and exposes retry when timeline fails', async () => {
    approvalApi.getForm.mockResolvedValue({ id: 10, workflow_instance_id: 100, workflow_version: 2 })
    workflowApi.getWorkflowTimeline.mockRejectedValueOnce(new Error('denied')).mockResolvedValueOnce([])
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.openDetail({ id: 10 })
    expect(wrapper.vm.detail.id).toBe(10)
    expect(wrapper.vm.detailLoading).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(false)
    expect(wrapper.vm.timelineError).toBe(true)
    const timelinePanel = wrapper.find('.timeline-panel')
    expect(timelinePanel.findComponent({ name: 'WorkflowTimeline' }).exists()).toBe(false)
    expect(timelinePanel.findComponent({ name: 'ElEmpty' }).exists()).toBe(false)
    await wrapper.vm.loadDetailTimeline()
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.timelineError).toBe(false)
  })

  it('clears stale workflow rows while timeline retry remains local', async () => {
    let rejectTimeline
    approvalApi.getForm.mockResolvedValue({ id: 11, workflow_instance_id: 110, workflow_version: 2 })
    workflowApi.getWorkflowTimeline.mockResolvedValueOnce([{ id: 1 }])
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectTimeline = reject }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.openDetail({ id: 11 })

    const retry = wrapper.vm.loadDetailTimeline()
    expect(wrapper.vm.detailLoading).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(true)
    expect(wrapper.vm.workflowTasks).toEqual([])
    rejectTimeline(new Error('denied'))
    await retry
    expect(wrapper.vm.timelineLoading).toBe(false)
    expect(wrapper.vm.timelineError).toBe(true)
  })

  it('ignores a late basic response after switching approval details', async () => {
    const detailA = deferred()
    const detailB = deferred()
    approvalApi.getForm.mockImplementation((id) => (id === 21 ? detailA.promise : detailB.promise))
    workflowApi.getWorkflowTimeline.mockResolvedValue([{ id: 'timeline-b' }])
    const wrapper = mountView()
    await flushPromises()

    const openA = wrapper.vm.openDetail({ id: 21 })
    const openB = wrapper.vm.openDetail({ id: 22 })
    detailB.resolve({ id: 22, workflow_instance_id: 220, workflow_version: 2 })
    await openB
    detailA.resolve({ id: 21, workflow_instance_id: 210, workflow_version: 2 })
    await openA

    expect(wrapper.vm.detail.id).toBe(22)
    expect(wrapper.vm.workflowTasks).toEqual([{ id: 'timeline-b' }])
    expect(wrapper.vm.timelineError).toBe(false)
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledTimes(1)
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledWith(220)
  })

  it('ignores a stale timeline retry after switching approval details', async () => {
    const staleRetry = deferred()
    approvalApi.getForm.mockImplementation((id) => Promise.resolve({ id, workflow_instance_id: id * 10, workflow_version: 2 }))
    workflowApi.getWorkflowTimeline
      .mockResolvedValueOnce([{ id: 'timeline-a' }])
      .mockImplementationOnce(() => staleRetry.promise)
      .mockResolvedValueOnce([{ id: 'timeline-b' }])
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.openDetail({ id: 31 })

    const retryA = wrapper.vm.loadDetailTimeline()
    await wrapper.vm.openDetail({ id: 32 })
    staleRetry.reject(new Error('stale denied'))
    await retryA

    expect(wrapper.vm.detail.id).toBe(32)
    expect(wrapper.vm.workflowTasks).toEqual([{ id: 'timeline-b' }])
    expect(wrapper.vm.timelineError).toBe(false)
    expect(wrapper.vm.detailLoading).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(false)
  })

  it('loads a numeric detail timeline for a string row id', async () => {
    const loadedDetail = deferred()
    approvalApi.getForm.mockReturnValue(loadedDetail.promise)
    workflowApi.getWorkflowTimeline.mockResolvedValue([{ id: 'timeline-42' }])
    const wrapper = mountView()
    await flushPromises()

    const opening = wrapper.vm.openDetail({ id: '42' })
    loadedDetail.resolve({ id: 42, workflow_instance_id: 420, workflow_version: 2 })
    await opening

    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledWith(420)
    expect(wrapper.vm.workflowTasks).toEqual([{ id: 'timeline-42' }])
    expect(wrapper.vm.timelineError).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(false)
  })

  it('invalidates pending detail work before unmount', async () => {
    const pendingDetail = deferred()
    approvalApi.getForm.mockReturnValue(pendingDetail.promise)
    const wrapper = mountView()
    await flushPromises()

    const opening = wrapper.vm.openDetail({ id: 41 })
    wrapper.unmount()
    pendingDetail.resolve({ id: 41, workflow_instance_id: 410, workflow_version: 2 })
    await opening

    expect(workflowApi.getWorkflowTimeline).not.toHaveBeenCalled()
  })
})
