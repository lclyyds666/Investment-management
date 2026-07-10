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
  return request.get('/operation/ai-diagnose', { params: { year } })
}
