import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const contractApi = vi.hoisted(() => ({
  getContract: vi.fn(), listApprovals: vi.fn(), fetchContractAttachmentBlob: vi.fn(), fetchLegalDocBlob: vi.fn()
}))
const workflowApi = vi.hoisted(() => ({ getWorkflowTimeline: vi.fn() }))
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/api/workflow', () => workflowApi)
vi.mock('@/utils/rmb', () => ({ digitToRMB: () => '' }))
vi.mock('@/utils/file', () => ({ previewBlob: vi.fn(), downloadBlob: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), error: vi.fn() } }))

import ContractDetailDrawer from './ContractDetailDrawer.vue'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mountDrawer(contractId) {
  return shallowMount(ContractDetailDrawer, {
    props: { modelValue: true, contractId },
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } }
  })
}

describe('ContractDetailDrawer timeline error', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps contract details visible and offers timeline retry', async () => {
    contractApi.getContract.mockResolvedValue({ id: 7, workflow_instance_id: 70, workflow_version: 2, status: 'pending', amount: 0 })
    workflowApi.getWorkflowTimeline.mockRejectedValueOnce(new Error('denied')).mockResolvedValueOnce([])
    const wrapper = shallowMount(ContractDetailDrawer, {
      props: { modelValue: true, contractId: 7 },
      global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } }
    })
    await flushPromises()
    expect(wrapper.vm.contract.id).toBe(7)
    expect(wrapper.vm.detailLoading).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(false)
    expect(wrapper.vm.timelineError).toBe(true)
    expect(wrapper.findComponent({ name: 'ElAlert' }).attributes('title')).toBe('流程记录加载失败，可重试')
    expect(wrapper.findComponent({ name: 'WorkflowTimeline' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'ElEmpty' }).exists()).toBe(false)
    await wrapper.vm.loadTimeline()
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.timelineError).toBe(false)
  })

  it('clears stale timeline rows while retrying independently', async () => {
    let rejectTimeline
    contractApi.getContract.mockResolvedValue({ id: 8, workflow_instance_id: 80, workflow_version: 2, status: 'pending', amount: 0 })
    workflowApi.getWorkflowTimeline.mockResolvedValueOnce([{ id: 1 }])
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectTimeline = reject }))
    const wrapper = shallowMount(ContractDetailDrawer, {
      props: { modelValue: true, contractId: 8 },
      global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } }
    })
    await flushPromises()

    const retry = wrapper.vm.loadTimeline()
    expect(wrapper.vm.detailLoading).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(true)
    expect(wrapper.vm.workflowTasks).toEqual([])
    rejectTimeline(new Error('denied'))
    await retry
    expect(wrapper.vm.timelineLoading).toBe(false)
    expect(wrapper.vm.timelineError).toBe(true)
  })

  it('ignores a late basic response after switching contracts', async () => {
    const detailA = deferred()
    const detailB = deferred()
    contractApi.getContract.mockImplementation((id) => (id === 21 ? detailA.promise : detailB.promise))
    workflowApi.getWorkflowTimeline.mockResolvedValue([{ id: 'timeline-b' }])
    const wrapper = mountDrawer(21)

    await wrapper.setProps({ contractId: 22 })
    detailB.resolve({ id: 22, workflow_instance_id: 220, workflow_version: 2, status: 'pending', amount: 0 })
    await flushPromises()
    detailA.resolve({ id: 21, workflow_instance_id: 210, workflow_version: 2, status: 'pending', amount: 0 })
    await flushPromises()

    expect(wrapper.vm.contract.id).toBe(22)
    expect(wrapper.vm.workflowTasks).toEqual([{ id: 'timeline-b' }])
    expect(wrapper.vm.timelineError).toBe(false)
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledTimes(1)
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledWith(220)
  })

  it('ignores a stale timeline retry after switching contracts', async () => {
    const staleRetry = deferred()
    contractApi.getContract.mockImplementation((id) => Promise.resolve({
      id,
      workflow_instance_id: id * 10,
      workflow_version: 2,
      status: 'pending',
      amount: 0
    }))
    workflowApi.getWorkflowTimeline
      .mockResolvedValueOnce([{ id: 'timeline-a' }])
      .mockImplementationOnce(() => staleRetry.promise)
      .mockResolvedValueOnce([{ id: 'timeline-b' }])
    const wrapper = mountDrawer(31)
    await flushPromises()

    const retryA = wrapper.vm.loadTimeline()
    await wrapper.setProps({ contractId: 32 })
    await flushPromises()
    staleRetry.reject(new Error('stale denied'))
    await retryA

    expect(wrapper.vm.contract.id).toBe(32)
    expect(wrapper.vm.workflowTasks).toEqual([{ id: 'timeline-b' }])
    expect(wrapper.vm.timelineError).toBe(false)
    expect(wrapper.vm.detailLoading).toBe(false)
    expect(wrapper.vm.timelineLoading).toBe(false)
  })

  it('accepts string contract ids without dropping the current timeline', async () => {
    contractApi.getContract.mockResolvedValue({ id: 41, workflow_instance_id: 410, workflow_version: 2, status: 'pending', amount: 0 })
    workflowApi.getWorkflowTimeline.mockResolvedValue([{ id: 'timeline-41' }])
    const wrapper = mountDrawer('41')
    await flushPromises()

    expect(wrapper.vm.contract.id).toBe(41)
    expect(wrapper.vm.workflowTasks).toEqual([{ id: 'timeline-41' }])
  })

  it('invalidates pending detail work before unmount', async () => {
    const pendingDetail = deferred()
    contractApi.getContract.mockReturnValue(pendingDetail.promise)
    const wrapper = mountDrawer(51)

    wrapper.unmount()
    pendingDetail.resolve({ id: 51, workflow_instance_id: 510, workflow_version: 2, status: 'pending', amount: 0 })
    await flushPromises()

    expect(workflowApi.getWorkflowTimeline).not.toHaveBeenCalled()
  })
})
