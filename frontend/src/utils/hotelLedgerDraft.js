function numberOr(value, fallback = 0) {
  if (value === null || value === undefined || value === '') return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function requiredRate(value, field) {
  if (value === null || value === undefined || value === '') {
    throw new TypeError(`酒店解析结果缺少有效费率：${field}`)
  }
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    throw new TypeError(`酒店解析结果缺少有效费率：${field}`)
  }
  return parsed
}

export function hotelPlatformLabel(row) {
  return `${row?.hotel_name || ''}${row?.platform || ''}` || '—'
}

export function compareHotelLedgerRows(left, right) {
  const hotels = ['海洋', '骑士', '长颈鹿']
  const brandedPlatforms = ['携程', '美团', '抖音']
  const legacyPlatforms = ['抖音', '美团', '携程']
  const leftHotel = hotels.indexOf(left?.hotel_name)
  const rightHotel = hotels.indexOf(right?.hotel_name)
  if (leftHotel >= 0 || rightHotel >= 0) {
    if (leftHotel !== rightHotel) {
      return (leftHotel < 0 ? hotels.length : leftHotel) - (rightHotel < 0 ? hotels.length : rightHotel)
    }
    return brandedPlatforms.indexOf(left?.platform) - brandedPlatforms.indexOf(right?.platform)
  }
  return legacyPlatforms.indexOf(left?.platform) - legacyPlatforms.indexOf(right?.platform)
}

export function createHotelDraftRows(parseResult, defaultHotelName, feePerNight = 44) {
  return (parseResult.platforms || []).map((platform) => ({
    platform: platform.platform,
    hotel_name: platform.hotel_name || defaultHotelName,
    check_date_text: platform.check_date_text,
    period_text: platform.period_text,
    period_start: platform.period_start,
    period_end: platform.period_end,
    room_nights: platform.room_nights,
    base_received: platform.base_received,
    supplier_commission: numberOr(platform.suggested_commission),
    commission_rate: requiredRate(platform.commission_rate, 'commission_rate'),
    rate_hexiao: requiredRate(platform.rate_hexiao, 'rate_hexiao'),
    rate_settle: requiredRate(platform.rate_settle, 'rate_settle'),
    fee_algo: 1,
    fee_per_night: feePerNight,
    def_commission: numberOr(platform.suggested_commission),
    def_hexiao: numberOr(platform.def_hexiao),
    def_service_fee: numberOr(platform.def_service_fee),
    def_jinying: numberOr(platform.def_jinying),
    daily_json: platform.daily_json || '',
    jinying_amount: numberOr(platform.def_jinying),
    jinyingEdited: false,
    payment_amount: 0,
    payment_date: null,
    repay_date: null,
    repay_amount: null,
    order_count: platform.order_count,
    positive_count: numberOr(platform.positive_count),
    source_file: parseResult.source_file,
    detail_stored: parseResult.detail_stored,
    detail_name: parseResult.detail_name
  }))
}

export function createHotelSaveRows(draftRows) {
  return draftRows.map((row) => ({
    platform: row.platform,
    hotel_name: row.hotel_name,
    check_date_text: row.check_date_text,
    period_text: row.period_text,
    period_start: row.period_start,
    period_end: row.period_end,
    room_nights: row.room_nights,
    base_received: row.base_received,
    supplier_commission: numberOr(row.supplier_commission),
    commission_rate: requiredRate(row.commission_rate, 'commission_rate'),
    rate_hexiao: requiredRate(row.rate_hexiao, 'rate_hexiao'),
    rate_settle: requiredRate(row.rate_settle, 'rate_settle'),
    fee_algo: row.fee_algo || 1,
    fee_per_night: numberOr(row.fee_per_night, 44),
    daily_json: row.daily_json,
    jinying_amount: row.jinyingEdited ? row.jinying_amount : null,
    def_commission: row.def_commission,
    def_hexiao: row.def_hexiao,
    def_service_fee: row.def_service_fee,
    def_jinying: row.def_jinying,
    payment_amount: numberOr(row.payment_amount),
    payment_date: row.payment_date,
    repay_date: row.repay_date,
    repay_amount: row.repay_amount,
    order_count: row.order_count,
    positive_count: row.positive_count,
    source_file: row.source_file,
    detail_stored: row.detail_stored,
    detail_name: row.detail_name
  }))
}
