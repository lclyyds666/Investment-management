import { describe, expect, it, vi } from 'vitest'
import router from './index'
import { legacySupplyRedirects } from './legacyRedirects'

vi.mock('@/layout/index.vue', () => ({ default: {} }))
vi.mock('@/layout/SystemLayout.vue', () => ({ default: {} }))
vi.mock('@/views/cultural-tourism/DetailView.vue', () => ({ default: {} }))
vi.mock('@/views/dashboard/index.vue', () => ({ default: {} }))
vi.mock('@/views/invoice/index.vue', () => ({ default: {} }))
vi.mock('@/views/screen/index.vue', () => ({ default: {} }))

const supplyRoutes = [
  ['Dashboard', '/supplymanagement/dashboard', 'supply.dashboard'],
  ['Operation', '/supplymanagement/operation', 'supply.operation'],
  ['CulturalTourism', '/supplymanagement/cultural-tourism', 'supply.scenic.analytics'],
  ['CulturalTourismDetail', '/supplymanagement/cultural-tourism/zunyi-zoo', 'supply.scenic.analytics'],
  ['FinanceFund', '/supplymanagement/finance/fund', 'supply.finance'],
  ['Invoice', '/supplymanagement/finance/invoice', 'supply.finance'],
  ['Contract', '/supplymanagement/contract', 'supply.contract'],
  ['Approval', '/supplymanagement/approval', 'supply.approval'],
  ['Customer', '/supplymanagement/customer', 'supply.customer'],
  ['Screen', '/supplymanagement/screen', 'supply.dashboard']
]

const legacyRoutes = [
  ['/dashboard', 'Dashboard', {}],
  ['/operation', 'Operation', {}],
  ['/cultural-tourism', 'CulturalTourism', {}],
  ['/cultural-tourism/:scenicId', 'CulturalTourismDetail', { scenicId: 'zunyi-zoo' }],
  ['/channel', 'CulturalTourism', {}],
  ['/channel/tourism', 'CulturalTourism', {}],
  ['/channel/other', 'CulturalTourism', {}],
  ['/finance/fund', 'FinanceFund', {}],
  ['/finance/invoice', 'Invoice', {}],
  ['/invoice', 'Invoice', {}],
  ['/contract', 'Contract', {}],
  ['/approval', 'Approval', {}],
  ['/customer', 'Customer', {}],
  ['/org', 'SystemUsers', {}],
  ['/audit', 'SystemAudit', {}],
  ['/profile', 'Profile', {}],
  ['/screen', 'Screen', {}]
]

describe('unified portal routes', () => {
  it('names the portal home at the root URL', () => {
    expect(router.resolve('/').name).toBe('PortalHome')
  })

  it('keeps the portal and supply profile destinations distinct', () => {
    expect(router.resolve({ name: 'PortalHome' }).path).toBe('/')
    expect(router.resolve({ name: 'Profile' }).path).toBe('/supplymanagement/profile')
    expect(router.resolve({ name: 'Screen' }).path).toBe('/supplymanagement/screen')
  })

  it('registers both construction applications under the shared portal shell', () => {
    const investment = router.resolve({ name: 'Investment' })
    const fund = router.resolve({ name: 'FundManagement' })

    expect(investment.path).toBe('/investment')
    expect(investment.meta.company).toBe('investment')
    expect(investment.meta.companyName).toBe('山东出版投资有限公司')
    expect(fund.path).toBe('/fundmanagement')
    expect(fund.meta.company).toBe('fundmanagement')
    expect(fund.meta.companyName).toBe('山东出版股权基金管理有限公司')
  })

  it.each(supplyRoutes)(
    'mounts %s under the supply namespace with authoritative metadata',
    (name, path, resource) => {
      const resolved = router.resolve(path)

      expect(resolved.name).toBe(name)
      expect(resolved.meta.company).toBe('supplymanagement')
      expect(resolved.meta.resource).toBe(resource)
    }
  )

  it('preserves dynamic params and query on the namespaced supply detail', () => {
    const resolved = router.resolve('/supplymanagement/cultural-tourism/zunyi-zoo?tab=ticket')

    expect(resolved.name).toBe('CulturalTourismDetail')
    expect(resolved.params.scenicId).toBe('zunyi-zoo')
    expect(resolved.query.tab).toBe('ticket')
  })

  it('keeps superuser-only metadata on administration routes', () => {
    expect(router.resolve({ name: 'SystemUsers' }).meta.requiresSuperuser).toBe(true)
    expect(router.resolve({ name: 'SystemAudit' }).meta.requiresSuperuser).toBe(true)
    expect(router.resolve({ name: 'SystemAiConversations' }).meta.requiresSuperuser).toBe(true)
    expect(router.resolve({ name: 'SystemAssignments' }).meta.requiresSuperuser).toBe(true)
  })

  it('mounts administration under the global system console', () => {
    expect(router.resolve('/system/users').name).toBe('SystemUsers')
    expect(router.resolve('/system/organization').name).toBe('SystemOrganization')
    expect(router.resolve('/system/positions').name).toBe('SystemPositions')
    expect(router.resolve('/system/assignments').name).toBe('SystemAssignments')
    expect(router.resolve('/system/audit').name).toBe('SystemAudit')
    expect(router.resolve('/system/ai-conversations').name).toBe('SystemAiConversations')
    expect(router.resolve('/system/directory').meta.permission).toBe('organization.directory.view')
  })

  it('redirects former supply admin paths', () => {
    expect(router.getRoutes().find(item => item.path === '/supplymanagement/org').redirect).toBe('/system/users')
    expect(router.getRoutes().find(item => item.path === '/supplymanagement/audit').redirect).toBe('/system/audit')
    expect(router.getRoutes().find(item => item.path === '/supplymanagement/ai-conversations').redirect).toBe('/system/ai-conversations')
  })

  it('does not expose system management in the supply children', () => {
    const supply = router.getRoutes().find(item => item.path === '/supplymanagement')
    expect(supply.children.some(item => ['org', 'audit', 'ai-conversations'].includes(item.path))).toBe(false)
  })

  it('keeps the supply profile company-scoped without inventing a backend resource', () => {
    const resolved = router.resolve({ name: 'Profile' })

    expect(resolved.path).toBe('/supplymanagement/profile')
    expect(resolved.meta.company).toBe('supplymanagement')
    expect(resolved.meta.resource).toBeUndefined()
  })

  it.each(legacyRoutes)(
    'declares an explicit replacement redirect from %s to %s',
    (path, name, params) => {
      const record = legacySupplyRedirects.find((route) => route.path === path)
      const query = { tab: 'ticket' }
      const hash = '#ledger'

      expect(record).toBeDefined()
      expect(record.redirect({ params, query, hash })).toEqual({
        name,
        params,
        query,
        hash,
        replace: true
      })
    }
  )

  it('redirects a legacy dynamic route without losing query or hash', async () => {
    await router.push('/cultural-tourism/zunyi-zoo?tab=hotel#ledger')
    await router.isReady()

    expect(router.currentRoute.value.fullPath).toBe(
      '/supplymanagement/cultural-tourism/zunyi-zoo?tab=hotel#ledger'
    )
  })

  it.each([
    ['/dashboard?year=2026', '/supplymanagement/dashboard?year=2026'],
    ['/finance/invoice?status=pending', '/supplymanagement/finance/invoice?status=pending'],
    ['/screen#map', '/supplymanagement/screen#map']
  ])('preserves legacy location %s', async (legacy, expected) => {
    await router.push(legacy)
    expect(router.currentRoute.value.fullPath).toBe(expected)
  })
})
