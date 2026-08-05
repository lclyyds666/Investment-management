import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessage } from 'element-plus'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import { portalGuard } from './permission'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn() }
}))

const SUPPLY_COMPANY = 'supplymanagement'
const SUPPLY_DASHBOARD = '/supplymanagement/dashboard'

function authenticatedContext({
  isSuperuser = false,
  companyRoles = {},
  resources = []
} = {}) {
  const userStore = useUserStore()
  userStore.token = 'test-token'
  userStore.userInfo = { id: 1, is_superuser: isSuperuser }

  const portalStore = usePortalStore()
  portalStore.permissions = {
    is_superuser: isSuperuser,
    company_roles: companyRoles,
    resources
  }
  portalStore.isLoaded = true

  return { portalStore, userStore }
}

function route(path, meta = {}) {
  return { path, fullPath: path, meta }
}

describe('portal permission guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('allows legal counsel to remain on the authenticated portal home', async () => {
    const { portalStore } = authenticatedContext({
      companyRoles: { [SUPPLY_COMPANY]: 'legal_counsel' },
      resources: ['supply.contract']
    })
    const loadPortalContext = vi.spyOn(portalStore, 'loadPortalContext')

    await expect(portalGuard(route('/'))).resolves.toBe(true)
    expect(loadPortalContext).toHaveBeenCalledOnce()
  })

  it('does not hijack legal counsel navigation to another accessible company', async () => {
    authenticatedContext({
      companyRoles: {
        [SUPPLY_COMPANY]: 'legal_counsel',
        investment: 'invest_director'
      },
      resources: ['supply.contract']
    })

    await expect(
      portalGuard(route('/investment', { company: 'investment' }))
    ).resolves.toBe(true)
  })

  it('continues allowed legal counsel routes through resource denial', async () => {
    const { portalStore } = authenticatedContext({
      companyRoles: { [SUPPLY_COMPANY]: 'legal_counsel' }
    })
    const hasResource = vi.spyOn(portalStore, 'hasResource')

    await expect(portalGuard(route('/supplymanagement/contract', {
      company: SUPPLY_COMPANY,
      resource: 'supply.contract',
      roles: ['legal_counsel']
    }))).resolves.toEqual({ path: SUPPLY_DASHBOARD })
    expect(hasResource).toHaveBeenCalledWith('supply.contract')
  })

  it('rejects an inaccessible company before resource and role checks', async () => {
    const { portalStore } = authenticatedContext({
      companyRoles: { [SUPPLY_COMPANY]: 'business_handler' },
      resources: ['supply.operation']
    })
    const hasResource = vi.spyOn(portalStore, 'hasResource')

    await expect(portalGuard(route('/investment', {
      company: 'investment',
      resource: 'investment.dashboard',
      roles: ['invest_director']
    }))).resolves.toEqual({ path: '/' })
    expect(hasResource).not.toHaveBeenCalled()
  })

  it('checks an allowed resource before rejecting a disallowed role', async () => {
    const { portalStore } = authenticatedContext({
      companyRoles: { [SUPPLY_COMPANY]: 'business_handler' },
      resources: ['supply.operation']
    })
    const hasResource = vi.spyOn(portalStore, 'hasResource')

    await expect(portalGuard(route('/supplymanagement/operation', {
      company: SUPPLY_COMPANY,
      resource: 'supply.operation',
      roles: ['finance_handler']
    }))).resolves.toEqual({ path: SUPPLY_DASHBOARD })
    expect(hasResource).toHaveBeenCalledWith('supply.operation')
  })

  it('enforces superuser after company, resource, and role checks pass', async () => {
    const { portalStore } = authenticatedContext({
      companyRoles: { [SUPPLY_COMPANY]: 'business_handler' },
      resources: ['supply.admin']
    })
    const hasCompany = vi.spyOn(portalStore, 'hasCompany')
    const hasResource = vi.spyOn(portalStore, 'hasResource')
    const companyRole = vi.spyOn(portalStore, 'companyRole')

    await expect(portalGuard(route('/supplymanagement/org', {
      company: SUPPLY_COMPANY,
      resource: 'supply.admin',
      roles: ['business_handler'],
      requiresSuperuser: true
    }))).resolves.toEqual({ path: SUPPLY_DASHBOARD })
    expect(hasCompany).toHaveBeenCalledWith(SUPPLY_COMPANY)
    expect(hasResource).toHaveBeenCalledWith('supply.admin')
    expect(companyRole).toHaveBeenCalledWith(SUPPLY_COMPANY)
    expect(ElMessage.error).toHaveBeenCalledOnce()
  })
})
