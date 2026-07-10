import request from './request'

export function listContracts() {
  return request.get('/contracts')
}

/** 待我审批（审批中心）：仅当前环节轮到我的合同 */
export function listTodo() {
  return request.get('/contracts/todo')
}

export function getContract(id) {
  return request.get(`/contracts/${id}`)
}

export function createContract(data) {
  return request.post('/contracts', data)
}

export function updateContract(id, data) {
  return request.put(`/contracts/${id}`, data)
}

export function deleteContract(id) {
  return request.delete(`/contracts/${id}`)
}

/** 业务经办提交审批（自动完成第 0 级并附签名，流入审批中心） */
export function submitContract(id) {
  return request.post(`/contracts/${id}/submit`)
}

/** 当前环节角色：逐级通过（自动附加电子签章） */
export function approveContract(id, comment = '') {
  return request.post(`/contracts/${id}/approve`, { comment })
}

/** 当前环节角色：驳回（原因必填） */
export function rejectContract(id, comment) {
  return request.post(`/contracts/${id}/reject`, { comment })
}

/** 合同审批流转记录（审计日志 / 时间轴 / 打印签章来源） */
export function listApprovals(id) {
  return request.get(`/contracts/${id}/approvals`)
}
