import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

vi.mock('@/api/user', () => ({ listUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), resetUserPassword: vi.fn() }))
vi.mock('@/api/organization', () => ({ getOrganizationTree: vi.fn().mockResolvedValue([]), listPositions: vi.fn().mockResolvedValue([]) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

describe('UsersView', () => {
  it('shows assignment summaries and no company role selector', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/system/users.vue'), 'utf8')
    expect(source).toContain('item.organization_name }} / {{ item.position_name')
    expect(source).toContain('assignment-trail')
    expect(source).not.toContain('company-role-select')
    expect(source).not.toContain('company_roles')
  })
})
