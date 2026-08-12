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
    expect(wrapper.vm.timelineError).toBe(true)
    expect(wrapper.findComponent({ name: 'ElAlert' }).attributes('title')).toBe('流程记录加载失败，可重试')
    await wrapper.vm.loadTimeline()
    expect(workflowApi.getWorkflowTimeline).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.timelineError).toBe(false)
  })
})
