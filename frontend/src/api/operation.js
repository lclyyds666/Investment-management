import request from './request'

/** 经营数据看板聚合 */
export function getDashboard(year = 2026) {
  return request.get('/operation/dashboard', { params: { year } })
}

/** 经营数据明细 */
export function listOperation(year = 2026) {
  return request.get('/operation', { params: { year } })
}

/** AI 智能大脑：风险诊断与资金投资建议 */
export function aiDiagnose(year = 2026) {
  return request.get('/operation/ai-diagnose', { params: { year }, timeout: 60000 })
}

/** 经营指标看板（文旅门票/酒店台账实时汇总） */
export function getFinancial() {
  return request.get('/operation/financial')
}

/** 大屏地图点位（项目→城市，数据驱动） */
export function getProjectsGeo(hub = '山东省') {
  return request.get('/operation/projects/geo', { params: { hub } })
}
