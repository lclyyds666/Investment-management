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
})
