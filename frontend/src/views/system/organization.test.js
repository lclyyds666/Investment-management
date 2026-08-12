import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import OrganizationView from './organization.vue'
import { buildOrganizationTree } from '@/utils/organizationTree'

const saveOrganization = vi.fn()
const loadTree = vi.fn()
const tree = ref([])
vi.mock('@/store/organization', () => ({
  useOrganizationStore: () => ({ tree: tree.value, saveOrganization, loadTree })
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(),
  ElMessage: { success: vi.fn(), error: vi.fn() }
}))

const TreeStub = { props: ['data'], template: '<div data-testid="tree">{{ JSON.stringify(data) }}</div>' }
const stubs = { ElTree: TreeStub, ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElForm: true, ElFormItem: true, ElInput: { props: ['modelValue', 'disabled'], emits: ['update:modelValue'], template: '<input :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />' }, ElSelect: { props: ['modelValue', 'disabled'], emits: ['update:modelValue'], template: '<select :value="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>' }, ElOption: true, ElInputNumber: true, ElSwitch: true }

describe('organization hierarchy and form rules', () => {
  beforeEach(() => { tree.value = []; saveOrganization.mockReset(); loadTree.mockReset() })
  it('nests flat departments under their company with stable roots', () => {
    const result = buildOrganizationTree([
      { code: 'external', name: '外部', organization_type: 'company', sort_order: 2 },
      { code: 'supply-dept', name: '采购部', organization_type: 'department', parent_code: 'supply', sort_order: 1 },
      { code: 'supply', name: '供管', organization_type: 'company', sort_order: 1 }
    ])
    expect(result.map(item => item.code)).toEqual(['supply', 'external'])
    expect(result[0].children.map(item => item.code)).toEqual(['supply-dept'])
  })
  it('clears a stale parent when switching to company and submits inherited company detail with reason', async () => {
    tree.value = buildOrganizationTree([{ code: 'supply', name: '供管', organization_type: 'company', sort_order: 1 }])
    saveOrganization.mockResolvedValue({ id: 1 })
    const wrapper = mount(OrganizationView, { global: { stubs } })
    await flushPromises()
    Object.assign(wrapper.vm.form, { code: 'new-company', name: '新公司', organization_type: 'department', parent_code: 'supply' })
    wrapper.vm.form.organization_type = 'company'
    await nextTick()
    wrapper.vm.reason = '治理调整'
    await wrapper.vm.save()
    expect(saveOrganization).toHaveBeenCalledWith(expect.objectContaining({ organization_type: 'company', parent_code: null, company_code: 'new-company' }), '治理调整', undefined)
  })
  it('rejects a department save without a parent instead of submitting manipulated state', async () => {
    const wrapper = mount(OrganizationView, { global: { stubs } })
    Object.assign(wrapper.vm.form, { code: 'orphan', name: '孤立部门', organization_type: 'department', parent_code: null })
    wrapper.vm.reason = '治理调整'
    await wrapper.vm.save()
    expect(saveOrganization).not.toHaveBeenCalled()
  })
})
