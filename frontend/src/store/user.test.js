import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from './user'
import * as authApi from '@/api/auth'

vi.mock('@/api/auth')

describe('user store session persistence', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.resetAllMocks()
  })

  it('removes the legacy role key after successful login and logout', async () => {
    localStorage.setItem('role', 'business_handler')
    authApi.login.mockResolvedValue({
      access_token: 'new-token',
      role: 'business_reviewer',
      user: { id: 1, role: 'business_reviewer', is_superuser: false }
    })
    const store = useUserStore()

    await store.login('worker', 'password')
    expect(localStorage.getItem('role')).toBeNull()
    expect(localStorage.getItem('token')).toBe('new-token')

    store.logout()
    expect(localStorage.getItem('role')).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })
})
