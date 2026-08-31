import request from './request'

export function listFunds(params = {}) {
  return request.get('/funds', { params })
}

export function getFundSummary() {
  return request.get('/funds/summary')
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
