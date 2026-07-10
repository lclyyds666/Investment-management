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

/** 财务经营指标看板（真实对账单回款） */
export function getFinancial() {
  return request.get('/operation/financial')
}

/** 批量上传平台对账单 xlsx */
export function uploadFinancial(file) {
  const form = new FormData()
  form.append('file', file)
  return request.post('/operation/financial/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/** 设置投入成本(对账单模块) */
export function setInvestedCost(totalInvestedCost) {
  return request.put('/operation/financial/cost', { total_invested_cost: totalInvestedCost })
}

/** 录入可用资金 */
export function setAvailableFunds(availableFunds) {
  return request.put('/operation/financial/available', { available_funds: availableFunds })
}

/** 上传供管公司项目统计表(含 Sheet2) */
export function uploadProjects(file) {
  const form = new FormData()
  form.append('file', file)
  return request.post('/operation/projects/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}
