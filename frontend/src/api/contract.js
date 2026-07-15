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

/** 上传合同附件（真实落盘，覆盖式单附件） */
export function uploadContractAttachment(id, file) {
  const form = new FormData()
  form.append('file', file)
  return request.post(`/contracts/${id}/attachment`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/** 合同附件下载接口路径（供带 token 拉取） */
export function contractAttachmentUrl(id) {
  return `/api/v1/contracts/${id}/attachment`
}

/** 以带 token 的请求拉取合同附件为 Blob（预览/下载） */
export async function fetchContractAttachmentBlob(id) {
  const resp = await fetch(contractAttachmentUrl(id), {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!resp.ok) throw new Error('附件获取失败')
  return await resp.blob()
}

/** 生成并下载「法律文件审批表」.docx（后端 python-docx 生成，3cm 行高 + 指定字体） */
export async function fetchLegalDocBlob(id) {
  const resp = await fetch(`/api/v1/contracts/${id}/legal-doc`, {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!resp.ok) throw new Error('审批表生成失败')
  return await resp.blob()
}
