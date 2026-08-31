export const YUAN_PER_WAN = 10000

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

export function yuanToWan(value) {
  return finiteNumber(value) / YUAN_PER_WAN
}

export function wanToYuan(value) {
  return Math.round(finiteNumber(value) * YUAN_PER_WAN * 100) / 100
}

function format(value, { prefix = '¥', suffix = ' 万元' } = {}) {
  const amount = finiteNumber(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
  return prefix + amount + suffix
}

export function formatWanFromYuan(value, options) {
  return format(yuanToWan(value), options)
}

export function formatWanValue(value, options) {
  return format(value, options)
}
