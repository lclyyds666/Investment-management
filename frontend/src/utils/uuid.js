function formatUuid(bytes) {
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'))
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join('')
  ].join('-')
}

function fillFallbackBytes(bytes) {
  let timestamp = Date.now()
  let highResolution = Math.floor((globalThis.performance?.now?.() || 0) * 1000)
  for (let index = 0; index < bytes.length; index += 1) {
    const source = index < 8 ? timestamp : highResolution
    bytes[index] = Math.floor(Math.random() * 256) ^ (source & 0xff)
    if (index < 8) timestamp = Math.floor(timestamp / 256)
    else highResolution = Math.floor(highResolution / 256)
  }
}

export function createUuid() {
  const cryptoObject = globalThis.crypto
  if (typeof cryptoObject?.randomUUID === 'function') {
    return cryptoObject.randomUUID()
  }

  const bytes = new Uint8Array(16)
  if (typeof cryptoObject?.getRandomValues === 'function') {
    cryptoObject.getRandomValues(bytes)
  } else {
    fillFallbackBytes(bytes)
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  return formatUuid(bytes)
}
