export function normalizeScenicSpot(item) {
  return {
    id: String(item?.id || '').trim(),
    name: String(item?.name || '').trim(),
    image: String(item?.image || '').trim(),
    ticket_enabled: item?.ticket_enabled === true,
    hotel_enabled: item?.hotel_enabled === true
  }
}

export function normalizeScenicSpots(items) {
  if (!Array.isArray(items)) return []
  return items
    .map(normalizeScenicSpot)
    .filter((item) => item.id && item.name)
}

export function enabledLedgerModules(spot) {
  if (!spot) return []
  return [
    spot.ticket_enabled ? 'ticket' : null,
    spot.hotel_enabled ? 'hotel' : null
  ].filter(Boolean)
}
