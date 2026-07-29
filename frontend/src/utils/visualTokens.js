/**
 * Canvas / ECharts 无法直接解析 CSS var()，因此集中维护少量绘图色值。
 * DOM 组件颜色统一使用 styles/_tokens.scss 中的 CSS 语义令牌。
 */
export const chartVisualTokens = Object.freeze({
  emptyText: '#819096',
  mapRamp: ['#e7efee', '#a9c8c6', '#5d9692', '#255f73'],
  mapBorder: '#b9c9ca',
  mapEmphasis: '#e8b968',
  screenTooltip: 'rgba(8, 18, 23, 0.94)',
  screenSurface: 'rgba(17, 36, 43, 0.84)',
  screenSurfaceSoft: 'rgba(17, 36, 43, 0.58)',
  screenBorder: 'rgba(120, 189, 209, 0.28)',
  screenBorderSoft: 'rgba(120, 189, 209, 0.18)',
  screenText: '#e9f2f3',
  screenTextMuted: '#8eabb5',
  screenPrimary: '#78bdd1',
  screenPrimarySoft: 'rgba(120, 189, 209, 0.22)',
  screenSecondary: '#63b39c',
  screenSecondarySoft: 'rgba(99, 179, 156, 0.28)',
  screenSecondaryGlow: 'rgba(99, 179, 156, 0.48)',
  screenSecondaryFade: 'rgba(99, 179, 156, 0.02)',
  screenAccent: '#e8b968',
  screenDanger: '#e07b71',
  screenAxis: 'rgba(120, 189, 209, 0.2)',
  screenMapArea: 'rgba(17, 36, 43, 0.76)',
  screenMapAreaSoft: 'rgba(17, 36, 43, 0.42)',
  screenMapAreaEmphasis: 'rgba(120, 189, 209, 0.34)',
  screenMapRamp: ['rgba(17, 36, 43, 0.42)', 'rgba(120, 189, 209, 0.52)', 'rgba(99, 179, 156, 0.78)']
})
