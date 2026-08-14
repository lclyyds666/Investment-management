import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import OrganizationView from './organization.vue'
import { buildOrganizationTree } from '@/utils/organizationTree'

const organizationSource = readFileSync(
  new URL('src/views/system/organization.vue', pathToFileURL(`${process.cwd()}/`)),
  'utf8'
)

const saveOrganization = vi.fn()
const loadTree = vi.fn()
const tree = ref([])
vi.mock('@/store/organization', () => ({ useOrganizationStore: () => ({ tree: tree.value, saveOrganization, loadTree }) }))
vi.mock('element-plus', async importOriginal => ({ ...await importOriginal(), ElMessage: { success: vi.fn(), error: vi.fn() } }))
const TreeStub = { props: ['data'], template: '<div data-testid="tree">{{ JSON.stringify(data) }}</div>' }
const stubs = { ElTree: TreeStub, ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElForm: true, ElFormItem: true, ElInput: true, ElSelect: true, ElOption: true, ElInputNumber: true, ElSwitch: true }

describe('organization hierarchy and form rules', () => {
  beforeEach(() => { tree.value = []; saveOrganization.mockReset(); loadTree.mockReset() })
  it('nests exact API rows under parent_id with stable roots', () => {
    const result = buildOrganizationTree([
      { id: '30', parent_id: null, code: 'external', name: '外部', organization_type: 'company', sort_order: 2 },
      { id: 20, parent_id: '10', code: 'supply-dept', name: '采购部', organization_type: 'department', sort_order: 1 },
      { id: 10, parent_id: null, code: 'supply', name: '供管', organization_type: 'company', sort_order: 1 }
    ])
    expect(result.map(item => item.code)).toEqual(['supply', 'external'])
    expect(result[0].children.map(item => item.code)).toEqual(['supply-dept'])
  })
  it('keeps missing and cyclic parent rows as roots', () => {
    const result = buildOrganizationTree([
      { id: 1, parent_id: 2, code: 'cycle-a', sort_order: 2 },
      { id: 2, parent_id: 1, code: 'cycle-b', sort_order: 1 },
      { id: 3, parent_id: 99, code: 'missing', sort_order: 3 }
    ])
    expect(result.map(item => item.code)).toEqual(['cycle-b', 'cycle-a', 'missing'])
  })
  it('keeps parent_code cycles as unique stable roots', () => {
    const result = buildOrganizationTree([
      { id: 1, code: 'fallback-a', parent_code: 'fallback-b', sort_order: 2 },
      { id: 2, code: 'fallback-b', parent_code: 'fallback-a', sort_order: 1 }
    ])
    expect(result.map(item => item.code)).toEqual(['fallback-b', 'fallback-a'])
    expect(result.flatMap(item => [item.code, ...item.children.map(child => child.code)])).toEqual(['fallback-b', 'fallback-a'])
  })
  it('keeps mixed parent_id and parent_code cycles as unique stable roots', () => {
    const result = buildOrganizationTree([
      { id: 1, code: 'mixed-a', parent_code: 'mixed-b', sort_order: 2 },
      { id: 2, code: 'mixed-b', parent_id: 1, sort_order: 1 }
    ])
    expect(result.map(item => item.code)).toEqual(['mixed-b', 'mixed-a'])
    expect(result.flatMap(item => [item.code, ...item.children.map(child => child.code)])).toEqual(['mixed-b', 'mixed-a'])
  })
  it('normalizes stale company parents and submits the reasoned payload', async () => {
    tree.value = buildOrganizationTree([{ id: 1, parent_id: null, code: 'supply', name: '供管', organization_type: 'company', sort_order: 1 }])
    saveOrganization.mockResolvedValue({ id: 4 })
    const wrapper = mount(OrganizationView, { global: { stubs } })
    await flushPromises()
    Object.assign(wrapper.vm.form, { code: 'new-company', name: '新公司', organization_type: 'department', parent_code: 'supply' })
    wrapper.vm.form.organization_type = 'company'
    await nextTick()
    wrapper.vm.reason = '治理调整'
    await wrapper.vm.save()
    expect(saveOrganization).toHaveBeenCalledWith(expect.objectContaining({ organization_type: 'company', parent_code: null, company_code: 'new-company' }), '治理调整', 1)
  })

  it('uses adaptive multi-line tree node sizing', () => {
    expect(organizationSource).toContain(':deep(.el-tree-node__content)')
    expect(organizationSource).toMatch(/height:\s*auto/)
    expect(organizationSource).toMatch(/min-height:\s*48px/)
    expect(organizationSource).toMatch(/overflow-wrap:\s*anywhere/)
    expect(organizationSource).toMatch(/grid-template-columns:\s*clamp\(/)
    expect(organizationSource).toMatch(/padding-block:\s*6px/)
  })
})
