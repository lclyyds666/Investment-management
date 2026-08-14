import { describe, expect, it, vi } from 'vitest'
import { canActOnWorkflow, canUsePermission } from './businessAuthorization'

function portalSnapshot({ permissions = [], positions = [], isSuperuser = false } = {}) {
  return {
    isSuperuser,
    hasPermission: vi.fn(code => permissions.includes(code)),
    hasPosition: vi.fn(code => positions.includes(code))
  }
}

describe('business UI authorization predicates', () => {
  it('allows an unassigned legacy account through its permission snapshot and confirmed position', () => {
    const legacyRole = 'unassigned'
    const portalStore = portalSnapshot({
      permissions: ['supply.contract.create', 'supply.contract.approve'],
      positions: ['external.legal_counsel']
    })

    expect(legacyRole).toBe('unassigned')
    expect(canUsePermission(portalStore, 'supply.contract.create')).toBe(true)
    expect(canActOnWorkflow(portalStore, {
      status: 'pending',
      current_role: 'legal_counsel'
    }, 'supply.contract.approve')).toBe(true)
  })

  it('grants all business permissions and pending workflow actions to a superuser', () => {
    const portalStore = portalSnapshot({ isSuperuser: true })

    expect(canUsePermission(portalStore, 'supply.customer.create')).toBe(true)
    expect(canActOnWorkflow(portalStore, {
      status: 'pending',
      current_role: 'scm_director'
    }, 'supply.approval.approve')).toBe(true)
    expect(canActOnWorkflow(portalStore, {
      status: 'approved',
      current_role: 'scm_director'
    }, 'supply.approval.approve')).toBe(false)
  })
})
