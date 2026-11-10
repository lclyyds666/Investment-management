import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import { useWorkItemsStore } from '@/store/workItems'
import { getWorkItems } from '@/api/workItems'
import WorkItems from './index.vue'

const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/workItems', () => ({ getWorkItems: vi.fn() }))

describe('central work items', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.useFakeTimers(); getWorkItems.mockReset(); push.mockReset() })
  afterEach(() => vi.useRealTimers())
  it('polls every 30 seconds and clears data and pending results on logout', async () => {
    const store = useWorkItemsStore()
    getWorkItems.mockResolvedValueOnce([{ id: 'one' }])
    store.startPolling('session-a')
    await store.load()
    expect(store.count).toBe(1)
    let finish
    getWorkItems.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    vi.advanceTimersByTime(30000)
    store.reset()
    finish([{ id: 'stale' }])
    await Promise.resolve()
    expect(store.items).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })
  it('catches polling failures and retries for a new session', async () => {
    const store = useWorkItemsStore()
    getWorkItems.mockRejectedValueOnce(new Error('network'))
    store.startPolling('one')
    await store.load()
    expect(store.error).toBe(true)
    getWorkItems.mockResolvedValueOnce([{ id: 'new' }])
    store.startPolling('two')
    await store.load()
    expect(store.count).toBe(1)
    expect(store.error).toBe(false)
    store.reset()
  })
  it('preserves original-module destination queries', async () => {
    const wrapper = shallowMount(WorkItems)
    const item = { target_path: '/supplymanagement/finance/fund', target_query: { tab: 'execution', task_id: '8' } }
    await wrapper.vm.handleWorkItem(item)
    expect(push).toHaveBeenCalledWith({ path: item.target_path, query: item.target_query })
    wrapper.unmount()
  })
})
