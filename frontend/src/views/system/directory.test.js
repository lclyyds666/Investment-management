import { describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import DirectoryView from './directory.vue'

vi.mock('@/store/organization', () => ({ useOrganizationStore: () => ({ tree: [], loadTree: vi.fn() }) }))

describe('DirectoryView privacy', () => {
  it('does not render account, term, permission, or audit fields', () => {
    const wrapper = shallowMount(DirectoryView, { global: { stubs: { ElTree: true, ElTag: true } } })
    expect(wrapper.text()).toContain('组织通讯录')
    expect(wrapper.html()).not.toContain('username')
    expect(wrapper.text()).not.toContain('有效期')
    expect(wrapper.text()).not.toContain('权限')
    expect(wrapper.text()).not.toContain('审计')
  })
})
