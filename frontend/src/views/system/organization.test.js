import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('OrganizationView', () => {
  it('keeps company ownership inherited instead of editable', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/system/organization.vue'), 'utf8')
    expect(source).toContain('label="所属公司"')
    expect(source).toContain(':model-value="inheritedCompany" disabled')
    expect(source).toContain(':disabled="form.organization_type === \'company\'"')
  })
})
