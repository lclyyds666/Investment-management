import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePortalStore } from './portal'
import * as portalApi from '@/api/portal'

vi.mock('@/api/portal')

const applications = [{ code: 'supplymanagement', accessible: true }]
const permissions = {
  is_superuser: false,
  assignments: [{ position_code: 'supply.business_handler' }],
  permissions: [{ code: 'supply.scenic.analytics.view', data_scope: 'company', scope_ref: 'supplymanagement' }],
  resources: ['supply.scenic.analytics']
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

describe('portal store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    localStorage.clear()
  })

  it('loads applications and exposes permission snapshot helpers', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue(permissions)

    const store = usePortalStore()
    await store.loadPortalContext()

    expect(store.hasPosition('supply.business_handler')).toBe(true)
    expect(store.hasPermission('supply.scenic.analytics.view')).toBe(true)
    expect(store.hasResource('supply.scenic.analytics')).toBe(true)
  })

  it('uses the current-login cache until a force reload', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue(permissions)

    const store = usePortalStore()
    await store.loadPortalContext()
    await store.loadPortalContext()
    expect(portalApi.getPortalApplications).toHaveBeenCalledTimes(1)
    expect(portalApi.getMyPortalPermissions).toHaveBeenCalledTimes(1)

    await store.loadPortalContext(true)
    expect(portalApi.getPortalApplications).toHaveBeenCalledTimes(2)
    expect(portalApi.getMyPortalPermissions).toHaveBeenCalledTimes(2)
  })

  it('deduplicates simultaneous endpoint loads', async () => {
    const applicationsRequest = deferred()
    const permissionsRequest = deferred()
    portalApi.getPortalApplications.mockReturnValue(applicationsRequest.promise)
    portalApi.getMyPortalPermissions.mockReturnValue(permissionsRequest.promise)

    const store = usePortalStore()
    const firstLoad = store.loadPortalContext()
    const secondLoad = store.loadPortalContext()

    expect(portalApi.getPortalApplications).toHaveBeenCalledTimes(1)
    expect(portalApi.getMyPortalPermissions).toHaveBeenCalledTimes(1)

    applicationsRequest.resolve(applications)
    permissionsRequest.resolve(permissions)
    await Promise.all([firstLoad, secondLoad])
  })

  it('retries after a rejected load instead of caching failure', async () => {
    portalApi.getPortalApplications.mockRejectedValueOnce(new Error('offline'))
    portalApi.getMyPortalPermissions.mockResolvedValue(permissions)

    const store = usePortalStore()
    await expect(store.loadPortalContext()).rejects.toThrow('offline')
    expect(store.isLoaded).toBe(false)

    portalApi.getPortalApplications.mockResolvedValueOnce(applications)
    await store.loadPortalContext()
    expect(store.isLoaded).toBe(true)
    expect(portalApi.getPortalApplications).toHaveBeenCalledTimes(2)
    expect(portalApi.getMyPortalPermissions).toHaveBeenCalledTimes(2)
  })

  it('clears the portal context when the user logs out', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue(permissions)

    const portalStore = usePortalStore()
    await portalStore.loadPortalContext()
    portalStore.clearPortalContext()

    expect(portalStore.applications).toEqual([])
    expect(portalStore.permissions).toEqual({
      is_superuser: false,
      assignments: [],
      permissions: [],
      resources: []
    })
    expect(portalStore.isLoaded).toBe(false)
  })

  it('ignores an old-login response that resolves after logout', async () => {
    const oldApplications = deferred()
    const oldPermissions = deferred()
    portalApi.getPortalApplications
      .mockReturnValueOnce(oldApplications.promise)
      .mockResolvedValueOnce([{ code: 'investment', accessible: true }])
    portalApi.getMyPortalPermissions
      .mockReturnValueOnce(oldPermissions.promise)
      .mockResolvedValueOnce({
        is_superuser: false,
        assignments: [{ position_code: 'investment.executive.general_manager' }],
        permissions: [],
        resources: []
      })

    const portalStore = usePortalStore()
    const oldLoad = portalStore.loadPortalContext()
    portalStore.clearPortalContext()
    await portalStore.loadPortalContext()

    oldApplications.resolve(applications)
    oldPermissions.resolve(permissions)
    await oldLoad

    expect(portalStore.applications).toEqual([{ code: 'investment', accessible: true }])
    expect(portalStore.hasPosition('investment.executive.general_manager')).toBe(true)
  })

  it('unions detailed permission grants and exposes active positions', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue({
      is_superuser: false,
      assignments: [
        { position_code: 'investment.executive.general_manager' },
        { position_code: 'governance.supply_leader' }
      ],
      permissions: [{ code: 'supply.contract.view', data_scope: 'company', scope_ref: 'supplymanagement' }],
      resources: []
    })

    const store = usePortalStore()
    await store.loadPortalContext()

    expect(store.hasPosition('governance.supply_leader')).toBe(true)
    expect(store.hasPermission('supply.contract.view')).toBe(true)
    expect(store.hasCompany('supplymanagement')).toBe(true)
  })

  it('does not treat superuser as a business permission bypass', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue({
      is_superuser: true,
      assignments: [],
      permissions: [],
      resources: []
    })

    const store = usePortalStore()
    await store.loadPortalContext()

    expect(store.hasPermission('supply.contract.approve')).toBe(false)
    expect(store.hasResource('supply.scenic.analytics')).toBe(false)
    expect(store.hasCompany('fundmanagement')).toBe(false)
  })
})
