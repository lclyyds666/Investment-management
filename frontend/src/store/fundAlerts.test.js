import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFundAlertStore } from './fundAlerts'
import * as fundApi from '@/api/fund'

vi.mock('@/api/fund')

describe('fund alert store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('deduplicates simultaneous loads and opens only for returned items', async () => {
    fundApi.getTodayFundAlerts.mockResolvedValue({
      alert_date: '2026-10-10',
      items: [{ id: 7, stage: 'due_soon', amount: 100000, maturity_date: '2026-11-09' }]
    })
    const store = useFundAlertStore()

    await Promise.all([store.loadForLogin(), store.loadForLogin()])

    expect(fundApi.getTodayFundAlerts).toHaveBeenCalledTimes(1)
    expect(store.visible).toBe(true)
    expect(store.items).toHaveLength(1)
  })

  it('keeps login usable when alert loading fails', async () => {
    fundApi.getTodayFundAlerts.mockRejectedValue(new Error('offline'))
    const store = useFundAlertStore()

    await expect(store.loadForLogin()).resolves.toBeUndefined()

    expect(store.visible).toBe(false)
    expect(store.loading).toBe(false)
  })

  it('does not open for an empty result and resets session state', async () => {
    fundApi.getTodayFundAlerts.mockResolvedValue({ alert_date: '2026-10-10', items: [] })
    const store = useFundAlertStore()
    await store.loadForLogin()
    expect(store.visible).toBe(false)
    store.reset()
    await store.loadForLogin()
    expect(fundApi.getTodayFundAlerts).toHaveBeenCalledTimes(2)
  })

  it('acknowledges exactly the displayed fund and stage pairs', async () => {
    fundApi.acknowledgeTodayFundAlerts.mockResolvedValue({ acknowledged: 2 })
    const store = useFundAlertStore()
    store.items = [{ id: 7, stage: 'overdue' }, { id: 8, stage: 'due_soon' }]

    await store.acknowledgeShown()

    expect(fundApi.acknowledgeTodayFundAlerts).toHaveBeenCalledWith([
      { fund_id: 7, stage: 'overdue' },
      { fund_id: 8, stage: 'due_soon' }
    ])
  })
})
