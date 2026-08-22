import { beforeEach, describe, expect, it, vi } from 'vitest'

const request = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./request', () => ({ default: request }))

import { exportContracts } from './contract'

describe('contract api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('requests the contract export as a blob', () => {
    exportContracts()

    expect(request.get).toHaveBeenCalledWith('/contracts/export', {
      responseType: 'blob',
      timeout: 60000
    })
  })
})
