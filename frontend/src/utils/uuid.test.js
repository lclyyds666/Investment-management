import { afterEach, describe, expect, it, vi } from 'vitest'
import { createUuid } from './uuid'

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

describe('createUuid', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('uses crypto.randomUUID when available', () => {
    const randomUUID = vi.fn(() => '11111111-1111-4111-8111-111111111111')
    vi.stubGlobal('crypto', { randomUUID })

    expect(createUuid()).toBe('11111111-1111-4111-8111-111111111111')
    expect(randomUUID).toHaveBeenCalledTimes(1)
  })

  it('formats getRandomValues bytes as UUID v4', () => {
    const getRandomValues = vi.fn((bytes) => {
      bytes.set(Array.from({ length: 16 }, (_, index) => index))
      return bytes
    })
    vi.stubGlobal('crypto', { getRandomValues })

    expect(createUuid()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
  })

  it('returns UUID v4 without Web Crypto', () => {
    vi.stubGlobal('crypto', undefined)
    vi.spyOn(Date, 'now').mockReturnValue(1723250000000)
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

    expect(createUuid()).toMatch(UUID_V4_PATTERN)
  })
})
