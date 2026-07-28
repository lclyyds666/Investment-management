export const SCENIC_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

export function createDefaultScenicForm() {
  return {
    scenic_id: '',
    scenic_name: '',
    image_url: '',
    sort_order: 100,
    enabled: true,
    ticket_enabled: true,
    hotel_enabled: true,
    default_ticket_product: '',
    default_hotel_name: '',
    rate_hexiao: 90,
    rate_settle: 94,
    commission_rate: 6,
    hotel_fee_algo: 1,
    fee_per_night: 44
  }
}

function percentToRate(value) {
  return Number((Number(value) / 100).toFixed(4))
}

export function buildScenicConfigPayload(form) {
  return {
    scenic_name: String(form.scenic_name || '').trim(),
    image_url: String(form.image_url || '').trim(),
    ticket_enabled: Boolean(form.ticket_enabled),
    hotel_enabled: Boolean(form.hotel_enabled),
    sort_order: Number(form.sort_order),
    default_ticket_product: String(form.default_ticket_product || '').trim(),
    default_hotel_name: String(form.default_hotel_name || '').trim(),
    rate_hexiao: percentToRate(form.rate_hexiao),
    rate_settle: percentToRate(form.rate_settle),
    commission_rate: percentToRate(form.commission_rate),
    hotel_fee_algo: Number(form.hotel_fee_algo),
    fee_per_night: Number(form.fee_per_night),
    enabled: Boolean(form.enabled)
  }
}
