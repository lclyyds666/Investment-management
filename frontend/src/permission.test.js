import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessage } from 'element-plus'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import { portalGuard } from './permission'
import { LEGAL_CAPABILITIES } from '@/utils/legalCapabilities'

vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn() } }))

const PLATFORM_TITLE = '山东出版投资有限公司工作平台'

function authenticatedContext({
  isSuperuser = false,
  applications = [],
  permissions = [],
  resources = [],
  companyRoles = {}
} = {}) {
  const userStore = useUserStore()
  userStore.token = 'test-token'
  userStore.userInfo = { id: 1, is_superuser: isSuperuser }
  const portalStore = usePortalStore()
  portalStore.applications = applications
  portalStore.permissions = {
    is_superuser: isSuperuser,
    assignments: [],
    permissions,
    resources,
    company_roles: companyRoles
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

  it('uses the unified platform name in browser titles', async () => {
    authenticatedContext()
    await portalGuard(route('/', { title: 'AI 助手' }))
    expect(document.title).toBe(`AI 助手 - ${PLATFORM_TITLE}`)
  })

  it.each(['development', 'production'])('ships the unified title in the %s Vite environment', (mode) => {
    expect(readFileSync(resolve(process.cwd(), `.env.${mode}`), 'utf8')).toContain(`VITE_APP_TITLE=${PLATFORM_TITLE}`)
  })

  it('checks superuser requirements before permission, application, and resource metadata', async () => {
    const { portalStore } = authenticatedContext({
      permissions: [{ code: 'organization.directory.view' }],
      applications: [{ code: 'supplymanagement', accessible: true }],
      resources: ['supply.dashboard']
    })
    const hasPermission = vi.spyOn(portalStore, 'hasPermission')
    const hasCompany = vi.spyOn(portalStore, 'hasCompany')

    await expect(portalGuard(route('/system/users', {
      requiresSuperuser: true,
      permission: 'organization.directory.view',
      company: 'supplymanagement'
    }))).resolves.toEqual({ path: '/supplymanagement/dashboard' })
    expect(hasPermission).not.toHaveBeenCalled()
    expect(hasCompany).not.toHaveBeenCalled()
  })

  it.each(['/system/audit', '/system/ai-conversations'])('denies non-superuser navigation to %s', async (path) => {
    authenticatedContext()
    await expect(portalGuard(route(path, { requiresSuperuser: true }))).resolves.toEqual({ path: '/supplymanagement/dashboard' })
  })

  it('enforces metadata permissions before application access', async () => {
    const { portalStore } = authenticatedContext({
      applications: [{ code: 'supplymanagement', accessible: true }]
    })
    const hasPermission = vi.spyOn(portalStore, 'hasPermission')
    const hasCompany = vi.spyOn(portalStore, 'hasCompany')

    await expect(portalGuard(route('/system/directory', {
      permission: 'organization.directory.view', company: 'supplymanagement'
    }))).resolves.toEqual({ path: '/' })
    expect(hasPermission).toHaveBeenCalledWith('organization.directory.view')
    expect(hasCompany).not.toHaveBeenCalled()
  })

  it('allows directory direct navigation only with its detailed permission grant', async () => {
    authenticatedContext({ permissions: [{ code: 'organization.directory.view' }] })

    await expect(portalGuard(route('/system/directory', {
      permission: 'organization.directory.view'
    }))).resolves.toBe(true)
  })

  it('grants supply business routes to a superuser without ordinary application access', async () => {
    authenticatedContext({ isSuperuser: true, resources: ['supply.dashboard'] })

    await expect(portalGuard(route('/supplymanagement/dashboard', {
      company: 'supplymanagement', resource: 'supply.dashboard'
    }))).resolves.toBe(true)
  })

  it('checks application access before a business resource', async () => {
    const { portalStore } = authenticatedContext()
    const hasCompany = vi.spyOn(portalStore, 'hasCompany')
    const hasResource = vi.spyOn(portalStore, 'hasResource')

    await expect(portalGuard(route('/supplymanagement/dashboard', {
      company: 'supplymanagement', resource: 'supply.dashboard'
    }))).resolves.toEqual({ path: '/' })
    expect(hasCompany).toHaveBeenCalledWith('supplymanagement')
    expect(hasResource).not.toHaveBeenCalled()
  })

  it('keeps investment management users out of legal edit routes', async () => {
    authenticatedContext({
      applications: [{ code: 'investment', accessible: true }],
      resources: ['invest.legal.cases'],
      companyRoles: { investment: 'invest_director' }
    })

    await expect(portalGuard(route('/investment/legal-risk/cases/8/edit', {
      company: 'investment',
      resource: 'invest.legal.cases',
      legalCapability: LEGAL_CAPABILITIES.EDIT_CASE
    }))).resolves.toEqual({ path: '/investment/legal-risk/cases' })
    expect(ElMessage.error).toHaveBeenCalledWith('权限不足，无法执行该法务操作')
  })

  it('allows a subsidiary user with the legal contract resource', async () => {
    authenticatedContext({
      applications: [{ code: 'supplymanagement', accessible: true }],
      resources: ['invest.legal.contracts']
    })

    await expect(portalGuard(route('/investment/legal-risk/contracts', {
      company: 'investment',
      resource: 'invest.legal.contracts',
      allowCrossCompanyResource: true
    }))).resolves.toBe(true)
  })
})
