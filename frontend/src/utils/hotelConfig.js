export const HOTEL_CONFIG_FIELDS = [
  'rate_hexiao',
  'rate_settle',
  'commission_rate',
  'fee_algo',
  'fee_per_night'
]

const RATE_FIELDS = new Set(['rate_hexiao', 'rate_settle', 'commission_rate'])

function requireNumber(value, field) {
  if (value === null || value === undefined || value === '') {
    throw new Error(`景区配置 ${field} 缺失`)
  }
  const number = Number(value)
  if (!Number.isFinite(number)) throw new Error(`景区配置 ${field} 非法`)
  return number
}

export function normalizeHotelConfig(config) {
  const normalized = {}
  for (const field of HOTEL_CONFIG_FIELDS) {
    const rawValue = field === 'fee_algo'
      ? (config?.hotel_fee_algo ?? config?.fee_algo)
      : config?.[field]
    const value = requireNumber(rawValue, field)
    if (RATE_FIELDS.has(field) && (value < 0 || value > 1)) {
      throw new Error(`景区配置 ${field} 非法`)
    }
    if (field === 'fee_algo' && ![1, 2].includes(value)) {
      throw new Error('景区配置 fee_algo 非法')
    }
    if (field === 'fee_per_night' && value < 0) {
      throw new Error('景区配置 fee_per_night 非法')
    }
    normalized[field] = value
  }
  return normalized
}

export function hotelConfigToForm(config) {
  const normalized = normalizeHotelConfig(config)
  return Object.fromEntries(
    HOTEL_CONFIG_FIELDS.map((field) => [
      field,
      RATE_FIELDS.has(field) ? normalized[field] * 100 : normalized[field]
    ])
  )
}

export function hotelConfigFromForm(form) {
  const config = {}
  for (const field of HOTEL_CONFIG_FIELDS) {
    const value = requireNumber(form?.[field], field)
    if (RATE_FIELDS.has(field)) {
      if (value < 0 || value > 100) throw new Error(`${field} 百分比非法`)
      config[field] = Math.round((value / 100) * 10000) / 10000
    } else if (field === 'fee_algo') {
      if (![1, 2].includes(value)) throw new Error('fee_algo 非法')
      config[field] = value
    } else {
      if (value < 0) throw new Error('fee_per_night 非法')
      config[field] = Math.round(value * 100) / 100
    }
  }
  return config
}

export function buildHotelConfigOverrides(form, modified) {
  const config = hotelConfigFromForm(form)
  return Object.fromEntries(
    HOTEL_CONFIG_FIELDS
      .filter((field) => modified?.[field] === true)
      .map((field) => [field, config[field]])
  )
}
