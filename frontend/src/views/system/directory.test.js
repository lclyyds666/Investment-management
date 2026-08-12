import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import DirectoryView from './directory.vue'

const tree = ref([{ code: 'supply', name: '供管公司', children: [{ code: 'procurement', name: '采购部', positions: [{ name: '采购经理', personnel: [{ id: 1, full_name: '王晓' }] }] }], positions: [] }])
vi.mock('@/store/organization', () => ({ useOrganizationStore: () => ({ tree: tree.value, loadTree: vi.fn() }) }))
const TreeStub = { props: ['data'], template: '<div><slot name="default" :data="data[0]" /><slot name="default" :data="data[0].children[0]" /></div>' }

describe('DirectoryView privacy', () => {
  it('renders nested personnel names and positions without account or governance fields', () => {
    const wrapper = mount(DirectoryView, { global: { stubs: { ElTree: TreeStub, ElTag: { template: '<span><slot /></span>' } } } })
    expect(wrapper.text()).toContain('供管公司')
    expect(wrapper.text()).toContain('采购部')
    expect(wrapper.text()).toContain('王晓 / 采购经理')
    expect(wrapper.html()).not.toContain('username')
    expect(wrapper.text()).not.toContain('有效期')
    expect(wrapper.text()).not.toContain('权限')
    expect(wrapper.text()).not.toContain('审计')
  })
})
