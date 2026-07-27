export const TICKET_RATE_FIELDS = ['rate_hexiao', 'rate_settle', 'commission_rate']

function requireRate(value, field) {
  if (value === null || value === undefined || value === '') {
    throw new Error(`景区配置 ${field} 缺失`)
  }
  const rate = Number(value)
  if (!Number.isFinite(rate) || rate < 0 || rate > 1) {
    throw new Error(`景区配置 ${field} 非法`)
  }
  return rate
}

export function normalizeTicketRates(config) {
  return Object.fromEntries(
    TICKET_RATE_FIELDS.map((field) => [field, requireRate(config?.[field], field)])
  )
}

export function ticketRatesToPercent(rates) {
  return Object.fromEntries(
    TICKET_RATE_FIELDS.map((field) => [field, requireRate(rates?.[field], field) * 100])
  )
}

export function ticketRatesFromPercent(ratePercent) {
  return Object.fromEntries(
    TICKET_RATE_FIELDS.map((field) => {
      const rawPercent = ratePercent?.[field]
      if (rawPercent === null || rawPercent === undefined || rawPercent === '') {
        throw new Error(`${field} 百分比缺失`)
      }
      const percent = Number(rawPercent)
      if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
        throw new Error(`${field} 百分比非法`)
      }
      return [field, Math.round((percent / 100) * 10000) / 10000]
    })
  )
}

export function buildTicketRateOverrides(ratePercent, modified) {
  const rates = ticketRatesFromPercent(ratePercent)
  return Object.fromEntries(
    TICKET_RATE_FIELDS
      .filter((field) => modified?.[field] === true)
      .map((field) => [field, rates[field]])
  )
}
