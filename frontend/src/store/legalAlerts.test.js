import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLegalAlertsStore } from './legalAlerts'
import * as legalApi from '@/api/legalRisk'

vi.mock('@/api/legalRisk')

describe('legal alert polling store', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    localStorage.setItem('token', 'test-token')
    setActivePinia(createPinia())
    legalApi.getAlertCounts.mockResolvedValue({ total: 3, critical: 1, warning: 2 })
    legalApi.listAlerts.mockResolvedValue({ items: [{ id: 8 }], total: 1 })
  })

  it('keeps exactly one polling timer and refreshes important alerts', async () => {
    const store = useLegalAlertsStore()
    store.startPolling()
    store.startPolling()

    expect(vi.getTimerCount()).toBe(1)
    await vi.waitFor(() => expect(store.count).toBe(3))
    expect(store.importantAlerts).toEqual([{ id: 8 }])
    store.stopPolling()
    expect(vi.getTimerCount()).toBe(0)
  })
})
