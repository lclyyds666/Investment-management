import { beforeEach, describe, expect, it, vi } from 'vitest'

const request = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./request', () => ({ default: request }))

import { getScenicOptions } from './scenic'

describe('scenic api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('requests the safe scenic option endpoint', () => {
    getScenicOptions()

    expect(request.get).toHaveBeenCalledWith('/scenic-spots/options')
  })
})
