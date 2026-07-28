import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildScenicConfigPayload,
  createDefaultScenicForm,
  SCENIC_ID_PATTERN
} from '../src/utils/scenicConfigForm.js'

test('新增景区默认配置与当前系统默认值一致', () => {
  const payload = buildScenicConfigPayload({
    ...createDefaultScenicForm(),
    scenic_id: 'test-scenic-001',
    scenic_name: '测试景区'
  })

  assert.equal(payload.rate_hexiao, 0.9)
  assert.equal(payload.rate_settle, 0.94)
  assert.equal(payload.commission_rate, 0.06)
  assert.equal(payload.hotel_fee_algo, 1)
  assert.equal(payload.fee_per_night, 44)
  assert.equal(payload.ticket_enabled, true)
  assert.equal(payload.hotel_enabled, true)
})

test('新增景区表单完整生成后端配置参数', () => {
  const payload = buildScenicConfigPayload({
    ...createDefaultScenicForm(),
    scenic_name: ' 新景区 ',
    image_url: ' https://example.com/scenic.jpg ',
    rate_hexiao: 88,
    rate_settle: 91,
    commission_rate: 5,
    hotel_fee_algo: 2,
    fee_per_night: 30,
    ticket_enabled: false,
    hotel_enabled: true,
    sort_order: 20
  })

  assert.deepEqual(payload, {
    scenic_name: '新景区',
    image_url: 'https://example.com/scenic.jpg',
    ticket_enabled: false,
    hotel_enabled: true,
    sort_order: 20,
    default_ticket_product: '',
    default_hotel_name: '',
    rate_hexiao: 0.88,
    rate_settle: 0.91,
    commission_rate: 0.05,
    hotel_fee_algo: 2,
    fee_per_night: 30,
    enabled: true
  })
})

test('景区标识只接受小写字母、数字和中划线', () => {
  assert.equal(SCENIC_ID_PATTERN.test('qingdao-scenic-01'), true)
  assert.equal(SCENIC_ID_PATTERN.test('Qingdao Scenic'), false)
  assert.equal(SCENIC_ID_PATTERN.test('-qingdao'), false)
})
