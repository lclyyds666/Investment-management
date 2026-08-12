import { describe, expect, it } from 'vitest'

import { createHotelDraftRows, createHotelSaveRows } from './hotelLedgerDraft'

const parsed = {
  source_file: '福州欧乐堡8.1-8.1.xlsx',
  detail_stored: 'stored.xlsx',
  detail_name: '福州欧乐堡8.1-8.1.xlsx',
  platforms: [{
    platform: '抖音',
    room_nights: 1,
    base_received: 91,
    suggested_commission: 3,
    commission_rate: 0.08,
    rate_hexiao: 0.91,
    rate_settle: 0.95,
    def_hexiao: 80.08,
    def_service_fee: 44,
    def_jinying: 124.08,
    daily_json: '[]',
    order_count: 1,
    positive_count: 1
  }]
}

describe('hotel ledger scenic config snapshot', () => {
  it('preserves parsed rates through draft and save mapping', () => {
    const drafts = createHotelDraftRows(parsed, '郑和海洋酒店')

    expect(drafts[0]).toMatchObject({
      commission_rate: 0.08,
      rate_hexiao: 0.91,
      rate_settle: 0.95
    })

    expect(createHotelSaveRows(drafts)[0]).toMatchObject({
      commission_rate: 0.08,
      rate_hexiao: 0.91,
      rate_settle: 0.95
    })
  })

  it('preserves literal zero rates and rejects missing snapshots', () => {
    const zeroRateResult = {
      ...parsed,
      platforms: [{
        ...parsed.platforms[0],
        commission_rate: 0,
        rate_hexiao: 0,
        rate_settle: 0
      }]
    }

    expect(createHotelDraftRows(zeroRateResult, '测试酒店')[0]).toMatchObject({
      commission_rate: 0,
      rate_hexiao: 0,
      rate_settle: 0
    })
    expect(() => createHotelDraftRows({
      ...parsed,
      platforms: [{ ...parsed.platforms[0], rate_hexiao: null }]
    }, '测试酒店')).toThrow(TypeError)
  })
})
