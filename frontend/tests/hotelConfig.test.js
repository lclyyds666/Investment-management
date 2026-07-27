import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildHotelConfigOverrides,
  hotelConfigToForm,
  normalizeHotelConfig
} from '../src/utils/hotelConfig.js'

const unchanged = {
  rate_hexiao: false,
  rate_settle: false,
  commission_rate: false,
  fee_algo: false,
  fee_per_night: false
}

function effectiveValue(payload, config, field) {
  return payload[field] ?? config[field]
}

test('欧乐堡未修改参数时不发送字段并保持原逻辑', () => {
  const config = normalizeHotelConfig({
    rate_hexiao: 0.90,
    rate_settle: 0.94,
    commission_rate: 0.06,
    hotel_fee_algo: 1,
    fee_per_night: 44
  })
  const payload = buildHotelConfigOverrides(hotelConfigToForm(config), unchanged)

  assert.deepEqual(payload, {})
  assert.equal(effectiveValue(payload, config, 'rate_hexiao'), 0.90)
  assert.equal(effectiveValue(payload, config, 'rate_settle'), 0.94)
  assert.equal(effectiveValue(payload, config, 'commission_rate'), 0.06)
  assert.equal(effectiveValue(payload, config, 'fee_algo'), 1)
  assert.equal(effectiveValue(payload, config, 'fee_per_night'), 44)
})

test('测试景区未修改参数时由后端采用算法1、30元和0.91', () => {
  const config = normalizeHotelConfig({
    rate_hexiao: 0.90,
    rate_settle: 0.91,
    commission_rate: 0.06,
    hotel_fee_algo: 1,
    fee_per_night: 30
  })
  const payload = buildHotelConfigOverrides(hotelConfigToForm(config), unchanged)

  assert.deepEqual(payload, {})
  assert.equal(effectiveValue(payload, config, 'fee_algo'), 1)
  assert.equal(effectiveValue(payload, config, 'fee_per_night'), 30)
  assert.equal(effectiveValue(payload, config, 'rate_settle'), 0.91)
})

test('用户将每间夜服务费改为35时仅发送fee_per_night', () => {
  const config = normalizeHotelConfig({
    rate_hexiao: 0.90,
    rate_settle: 0.91,
    commission_rate: 0.06,
    hotel_fee_algo: 1,
    fee_per_night: 30
  })
  const form = hotelConfigToForm(config)
  form.fee_per_night = 35
  const payload = buildHotelConfigOverrides(form, {
    ...unchanged,
    fee_per_night: true
  })

  assert.deepEqual(payload, { fee_per_night: 35 })
  assert.equal(effectiveValue(payload, config, 'fee_per_night'), 35)
})
