import { describe, expect, it } from 'vitest'
import { ROLES } from '@/constants/business'
import {
  LEGAL_CAPABILITIES,
  canDeleteLegalAttachment,
  legalCapabilities,
  legalCapabilitiesForAssignments
} from './legalCapabilities'

describe('legal risk capability matrix', () => {
  it('gives business and legal-risk roles identical write permissions', () => {
    expect(legalCapabilities(ROLES.BUSINESS_HANDLER)).toEqual(
      legalCapabilities(ROLES.RISK_AUDITOR)
    )
    expect(legalCapabilities(ROLES.RISK_AUDITOR)).toContain(
      LEGAL_CAPABILITIES.MANAGE_DETAIL
    )
  })

  it('keeps management read-only while allowing report export', () => {
    const capabilities = legalCapabilities(ROLES.INVEST_DIRECTOR)
    expect(capabilities).toContain(LEGAL_CAPABILITIES.VIEW_CASE)
    expect(capabilities).toContain(LEGAL_CAPABILITIES.EXPORT_MANAGEMENT)
    expect(capabilities).not.toContain(LEGAL_CAPABILITIES.EDIT_CASE)
    expect(capabilities).not.toContain(LEGAL_CAPABILITIES.MANAGE_ALERT)
  })

  it('gives the superuser every legal capability', () => {
    expect(legalCapabilities('', true).size).toBe(Object.keys(LEGAL_CAPABILITIES).length)
  })

  it('unions legal capabilities across multiple assignments', () => {
    const capabilities = legalCapabilitiesForAssignments([
      { position_code: 'investment.executive.general_manager' },
      { position_code: 'investment.department.junior_manager' }
    ])

    expect(capabilities).toContain(LEGAL_CAPABILITIES.EDIT_CASE)
    expect(capabilities).toContain(LEGAL_CAPABILITIES.EXPORT_MANAGEMENT)
  })

  it('only allows counsel to delete their own attachment on a writable case', () => {
    const context = {
      role: ROLES.LEGAL_COUNSEL,
      isSuperuser: false,
      currentUserId: 7,
      archivedAt: null
    }
    expect(canDeleteLegalAttachment(context, { uploaded_by: 7 })).toBe(true)
    expect(canDeleteLegalAttachment(context, { uploaded_by: 8 })).toBe(false)
    expect(canDeleteLegalAttachment({ ...context, archivedAt: '2026-08-14' }, { uploaded_by: 7 })).toBe(false)
  })
})
