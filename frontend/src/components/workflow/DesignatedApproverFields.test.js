import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ listWorkflowCandidates: vi.fn() }))
vi.mock('@/api/workflow', () => api)

import DesignatedApproverFields from './DesignatedApproverFields.vue'

const candidateFixture = {
  company_leader: [
    { user_id: 11, full_name: '张明', organization_name: '山东出版供应链管理有限公司', position_name: '公司负责人', valid_from: '2026-01-01', valid_until: null },
    { user_id: 12, full_name: '李宁', organization_name: '山东出版供应链管理有限公司', position_name: '公司负责人', valid_from: '2026-02-01', valid_until: '2026-12-31' }
  ],
  legal_counsel: [
    { user_id: 21, full_name: '王律师', organization_name: '齐鲁律师事务所', position_name: '外聘法律顾问', valid_from: '2026-05-01', valid_until: '2027-04-30' }
  ],
  supply_governance_leader: [
    { user_id: 31, full_name: '赵蕾', organization_name: '山东出版集团', position_name: '供管公司分管领导' }
  ]
}

const SelectStub = {
  props: ['modelValue', 'disabled', 'placeholder'],
  emits: ['update:modelValue'],
  template: '<div class="select-stub" :data-disabled="disabled"><slot /></div>'
}
const OptionStub = { props: ['value', 'label', 'disabled'], template: '<div class="option-stub" :data-value="value" :data-disabled="disabled">{{ label }}<slot /></div>' }
const global = { stubs: { ElSelect: SelectStub, ElOption: OptionStub, ElSkeleton: { template: '<div class="skeleton" />' }, ElAlert: { props: ['title', 'description'], template: '<div>{{ title }} {{ description }}<slot /></div>' }, ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' } } }

let candidates

function mountFields(props = {}) {
  return mount(DesignatedApproverFields, {
    props: { workflowCode: 'supply.contract.v2', modelValue: {}, ...props },
    global
  })
}

describe('DesignatedApproverFields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    candidates = structuredClone(candidateFixture)
    api.listWorkflowCandidates.mockImplementation((_workflowCode, nodeCode) => Promise.resolve(candidates[nodeCode] || []))
  })

  it('renders the three contract designated nodes in workflow order', async () => {
    const wrapper = mountFields()
    await flushPromises()

    expect(wrapper.findAll('[data-testid="approver-node"]').map((node) => node.attributes('data-node-code'))).toEqual([
      'company_leader', 'legal_counsel', 'supply_governance_leader'
    ])
    expect(wrapper.text()).toContain('公司负责人')
    expect(wrapper.text()).toContain('外聘法律顾问')
    expect(wrapper.text()).toContain('供管公司分管领导')
  })

  it('emits a node-to-user map and prevents one person crossing nodes', async () => {
    candidates.legal_counsel = [...candidates.legal_counsel, { ...candidates.company_leader[0], position_name: '外聘法律顾问' }]
    const wrapper = mountFields()
    await flushPromises()

    await wrapper.vm.selectUser('company_leader', 11)
    await flushPromises()
    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toEqual({ company_leader: 11 })
    expect(wrapper.vm.isCandidateDisabled('legal_counsel', 11)).toBe(true)
  })

  it('shows candidate details and validates every required node', async () => {
    const wrapper = mountFields()
    await flushPromises()

    await wrapper.vm.selectUser('company_leader', 11)
    expect(wrapper.text()).toContain('山东出版供应链管理有限公司')
    expect(wrapper.text()).toContain('2026-01-01 起 · 长期有效')
    expect(await wrapper.vm.validate()).toBe(false)
    expect(wrapper.text()).toContain('请选择全部指定审批人')
  })

  it('reloads failed candidates and retains only still-valid unique selections', async () => {
    api.listWorkflowCandidates.mockImplementationOnce(() => Promise.reject(new Error('offline')))
    const wrapper = mountFields({ modelValue: { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 } })
    await flushPromises()
    expect(wrapper.text()).toContain('候选人加载失败')

    candidates.company_leader = [candidates.company_leader[1]]
    await wrapper.vm.reloadCandidates({ preserve: true })
    await flushPromises()

    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toEqual({ legal_counsel: 21, supply_governance_leader: 31 })
  })

  it('retains cached candidates and valid selections when one refresh request fails', async () => {
    const wrapper = mountFields({ modelValue: { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 } })
    await flushPromises()

    candidates.company_leader = [candidateFixture.company_leader[1]]
    api.listWorkflowCandidates.mockImplementation((_, nodeCode) => (
      nodeCode === 'legal_counsel'
        ? Promise.reject(new Error('offline'))
        : Promise.resolve(candidates[nodeCode] || [])
    ))
    await wrapper.vm.reloadCandidates({ preserve: true })
    await flushPromises()

    expect(wrapper.vm.selectedCandidate('legal_counsel')?.user_id).toBe(21)
    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toEqual({ legal_counsel: 21, supply_governance_leader: 31 })
  })

  it('uses two designated nodes for payment and business workflows', async () => {
    for (const workflowCode of ['supply.payment.v2', 'supply.business.v2']) {
      const wrapper = mountFields({ workflowCode })
      await flushPromises()
      expect(wrapper.findAll('[data-testid="approver-node"]')).toHaveLength(2)
      expect(wrapper.find('[data-node-code="legal_counsel"]').exists()).toBe(false)
      await flushPromises()
      wrapper.unmount()
    }
  })

  it('defensively excludes the submitting user even if the API returns them', async () => {
    candidates.company_leader.push({ user_id: 99, full_name: '提交人', organization_name: '供应链公司', position_name: '公司负责人', valid_from: '2026-01-01', valid_until: null })
    const wrapper = mountFields({ excludeUserId: 99 })
    await flushPromises()

    expect(wrapper.text()).not.toContain('提交人')
    expect(wrapper.vm.isCandidateDisabled('company_leader', 99)).toBe(false)
  })
})
