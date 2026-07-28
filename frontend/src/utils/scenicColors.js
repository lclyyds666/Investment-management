/**
 * 景区业务系列的稳定颜色映射。
 * key 固定为 scenicId:businessType，筛选、排序或数据增减不会改变已有系列颜色。
 */
export const scenicColorMap = Object.freeze({
  'quancheng-ouleb:ticket': '#2563eb',
  'quancheng-ouleb:hotel': '#f59e0b',
  'quanzhou-ouleb:ticket': '#0f766e',
  'quanzhou-ouleb:hotel': '#dc2626',
  'fuzhou-ouleb:ticket': '#7c3aed',
  'fuzhou-ouleb:hotel': '#16a34a',
  'zunyi-zoo:ticket': '#ea580c',
  'zunyi-zoo:hotel': '#0891b2',
  'nanyang-wildlife:ticket': '#be123c',
  'nanyang-wildlife:hotel': '#4f46e5',
  'guanquelou:ticket': '#65a30d',
  'guanquelou:hotel': '#9333ea'
})

const fallbackColors = [
  '#0369a1', '#b45309', '#047857', '#b91c1c', '#6d28d9', '#0e7490',
  '#c2410c', '#3f6212', '#9f1239', '#4338ca', '#0f766e', '#a21caf'
]

function stableHash(value) {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function getScenicColor(scenicId, businessType) {
  const key = `${scenicId}:${businessType}`
  return scenicColorMap[key] || fallbackColors[stableHash(key) % fallbackColors.length]
}
