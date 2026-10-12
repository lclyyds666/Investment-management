import request from './request'

export function listFunds(params = {}) {
  return request.get('/funds', { params })
}

export function getFundSummary() {
  return request.get('/funds/summary')
}

export function getTodayFundAlerts() {
  return request.get('/funds/alerts/today')
}

export function acknowledgeTodayFundAlerts(items) {
  return request.post('/funds/alerts/today/acknowledge', { items })
}

export function createFund(payload) {
  return request.post('/funds', payload)
}

export function updateFund(id, payload) {
  return request.put(`/funds/${id}`, payload)
}

export function deleteFund(id) {
  return request.delete(`/funds/${id}`)
}

export function settleFund(id, settledOn) {
  return request.post(`/funds/${id}/settle`, { settled_on: settledOn || null })
}

export function listCashExecutionTasks(params = {}) {
  return request.get('/funds/execution-tasks', { params })
}

export function executeCashTask(id, payload) {
  return request.post(`/funds/execution-tasks/${id}/execute`, payload)
}
