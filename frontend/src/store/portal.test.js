import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePortalStore } from './portal'
import { useUserStore } from './user'
import * as portalApi from '@/api/portal'

vi.mock('@/api/portal')

const applications = [{ code: 'supplymanagement', accessible: true }]
const permissions = {
  is_superuser: false,
  company_roles: [{ company_code: 'supplymanagement', role: 'business_handler' }],
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

  it('loads applications and resolves the supply company role', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue(permissions)

    const store = usePortalStore()
    await store.loadPortalContext()

    expect(store.companyRole('supplymanagement')).toBe('business_handler')
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
    const userStore = useUserStore()
    userStore.setUserInfo({ is_superuser: false, role: 'business_handler' })
    userStore.logout()

    expect(portalStore.applications).toEqual([])
    expect(portalStore.permissions).toEqual({
      is_superuser: false,
      company_roles: {},
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
        company_roles: { investment: 'invest_director' },
        resources: []
      })

    const portalStore = usePortalStore()
    const oldLoad = portalStore.loadPortalContext()
    useUserStore().logout()
    await portalStore.loadPortalContext()

    oldApplications.resolve(applications)
    oldPermissions.resolve(permissions)
    await oldLoad

    expect(portalStore.applications).toEqual([{ code: 'investment', accessible: true }])
    expect(portalStore.companyRole('investment')).toBe('invest_director')
  })

  it('reads the backend company-role map payload', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue({
      is_superuser: false,
      company_roles: { supplymanagement: 'business_reviewer' },
      resources: []
    })

    const store = usePortalStore()
    await store.loadPortalContext()

    expect(store.companyRole('supplymanagement')).toBe('business_reviewer')
    expect(store.hasCompany('supplymanagement')).toBe(true)
  })

  it('preserves superuser company and resource bypasses', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue({
      is_superuser: true,
      company_roles: {},
      resources: []
    })

    const store = usePortalStore()
    await store.loadPortalContext()

    expect(store.hasCompany('fundmanagement')).toBe(true)
    expect(store.hasResource('supply.scenic.analytics')).toBe(true)
  })

  it('uses the authoritative supply role and preserves the user superuser bypass', async () => {
    portalApi.getPortalApplications.mockResolvedValue(applications)
    portalApi.getMyPortalPermissions.mockResolvedValue({
      ...permissions,
      company_roles: { supplymanagement: 'business_handler' }
    })

    const portalStore = usePortalStore()
    await portalStore.loadPortalContext()
    const userStore = useUserStore()
    userStore.setUserInfo({ is_superuser: false, role: 'finance_handler' })

    expect(userStore.hasRole(['business_handler'])).toBe(true)
    expect(userStore.hasRole(['finance_handler'])).toBe(false)

    userStore.setUserInfo({ is_superuser: true, role: 'info_maintainer' })
    expect(userStore.hasRole(['finance_handler'])).toBe(true)
  })
})
