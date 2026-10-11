import { beforeEach, describe, expect, it, vi } from 'vitest'

const request = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./request', () => ({ default: request }))

import { exportContracts, listEligibleContracts } from './contract'

describe('contract api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('requests the contract export as a blob', () => {
    exportContracts()

    expect(request.get).toHaveBeenCalledWith('/contracts/export', {
      responseType: 'blob',
      timeout: 60000
    })
  })

  it('requests eligible contracts for one scenic and source kind', () => {
    listEligibleContracts('guanquelou', 'ticket')

    expect(request.get).toHaveBeenCalledWith('/contracts/eligible', {
      params: { scenic_id: 'guanquelou', source_kind: 'ticket' }
    })
  })
})
