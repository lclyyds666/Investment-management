import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTicketRateOverrides,
  normalizeTicketRates,
  ticketRatesToPercent
} from '../src/utils/ticketRates.js'

const unchanged = {
  rate_hexiao: false,
  rate_settle: false,
  commission_rate: false
}

function effectiveRate(payload, config, field) {
  return payload[field] ?? config[field]
}

test('欧乐堡未修改费率时不发送字段并保持原系统结果', () => {
  const config = normalizeTicketRates({
    rate_hexiao: 0.90,
    rate_settle: 0.94,
    commission_rate: 0.06
  })
  const payload = buildTicketRateOverrides(ticketRatesToPercent(config), unchanged)

  assert.deepEqual(payload, {})
  assert.equal(effectiveRate(payload, config, 'rate_hexiao'), 0.90)
  assert.equal(effectiveRate(payload, config, 'rate_settle'), 0.94)
  assert.equal(effectiveRate(payload, config, 'commission_rate'), 0.06)
})

test('新景区配置0.92且未修改时由后端采用0.92', () => {
  const config = normalizeTicketRates({
    rate_hexiao: 0.92,
    rate_settle: 0.94,
    commission_rate: 0.06
  })
  const payload = buildTicketRateOverrides(ticketRatesToPercent(config), unchanged)

  assert.equal(Object.hasOwn(payload, 'rate_hexiao'), false)
  assert.equal(effectiveRate(payload, config, 'rate_hexiao'), 0.92)
})

test('用户手动改为0.95时明确发送0.95', () => {
  const config = normalizeTicketRates({
    rate_hexiao: 0.92,
    rate_settle: 0.94,
    commission_rate: 0.06
  })
  const percent = ticketRatesToPercent(config)
  percent.rate_hexiao = 95
  const payload = buildTicketRateOverrides(percent, {
    ...unchanged,
    rate_hexiao: true
  })

  assert.deepEqual(payload, { rate_hexiao: 0.95 })
  assert.equal(effectiveRate(payload, config, 'rate_hexiao'), 0.95)
})
