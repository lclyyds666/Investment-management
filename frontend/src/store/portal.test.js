import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePortalStore } from './portal'
import * as portalApi from '@/api/portal'

vi.mock('@/api/portal')

describe('portal store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads applications and resolves the supply company role', async () => {
    portalApi.getPortalApplications.mockResolvedValue([{ code: 'supplymanagement', accessible: true }])
    portalApi.getMyPortalPermissions.mockResolvedValue({
      is_superuser: false,
      company_roles: [{ company_code: 'supplymanagement', role: 'business_handler' }],
      resources: ['supply.scenic.analytics']
    })
    const store = usePortalStore()
    await store.loadPortalContext()
    expect(store.companyRole('supplymanagement')).toBe('business_handler')
    expect(store.hasResource('supply.scenic.analytics')).toBe(true)
  })
})
