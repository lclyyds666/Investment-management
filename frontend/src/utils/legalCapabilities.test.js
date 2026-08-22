import { describe, expect, it } from 'vitest'
import {
  LEGAL_CAPABILITIES,
  canDeleteLegalAttachment,
  legalCapabilities
} from './legalCapabilities'

describe('legal risk capability matrix', () => {
  it('derives create update import and export independently from permission snapshots', () => {
    const capabilities = legalCapabilities([
      { code: 'investment.legal.cases.view' },
      { code: 'investment.legal.cases.create' },
      { code: 'investment.legal.cases.export' }
    ])
    expect(capabilities).toContain(LEGAL_CAPABILITIES.VIEW_CASE)
    expect(capabilities).toContain(LEGAL_CAPABILITIES.CREATE_CASE)
    expect(capabilities).toContain(LEGAL_CAPABILITIES.EXPORT_MANAGEMENT)
    expect(capabilities).not.toContain(LEGAL_CAPABILITIES.EDIT_CASE)
    expect(capabilities).not.toContain(LEGAL_CAPABILITIES.IMPORT_EXPORT)
  })

  it('gives the superuser every legal capability', () => {
    expect(legalCapabilities([], true).size).toBe(Object.keys(LEGAL_CAPABILITIES).length)
  })

  it('does not grant a capability from a position name alone', () => {
    expect(legalCapabilities([], false, [
      { position_code: 'xinhuaproperty.department.employee' },
      { position_code: 'zhanwei.junior_manager' }
    ])).toEqual(new Set())
  })

  it('only allows counsel to delete their own attachment on a writable case', () => {
    const context = {
      isSuperuser: false,
      currentUserId: 7,
      archivedAt: null,
      permissions: [{ code: 'investment.legal.cases.review' }]
    }
    expect(canDeleteLegalAttachment(context, { uploaded_by: 7 })).toBe(true)
    expect(canDeleteLegalAttachment(context, { uploaded_by: 8 })).toBe(false)
    expect(canDeleteLegalAttachment({ ...context, archivedAt: '2026-08-14' }, { uploaded_by: 7 })).toBe(false)
  })
})
