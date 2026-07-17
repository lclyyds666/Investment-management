import request from './request'

// 审批中心：两套独立审批单工作流（业务付款审批单 / 业务审批单）

export function listForms() {
  return request.get('/approval-forms')
}

/** 待我审批：仅当前环节轮到我的单据 */
export function listTodo() {
  return request.get('/approval-forms/todo')
}

export function getForm(id) {
  return request.get(`/approval-forms/${id}`)
}

export function createForm(data) {
  return request.post('/approval-forms', data)
}

export function updateForm(id, data) {
  return request.put(`/approval-forms/${id}`, data)
}

export function deleteForm(id) {
  return request.delete(`/approval-forms/${id}`)
}

/** 业务经办提交审批（自动完成第 0 级并附签名） */
export function submitForm(id) {
  return request.post(`/approval-forms/${id}/submit`)
}

/** 当前环节角色：逐级通过（自动附加电子签章） */
export function approveForm(id, comment = '') {
  return request.post(`/approval-forms/${id}/approve`, { comment })
}

/** 当前环节角色：驳回（原因必填） */
export function rejectForm(id, comment) {
  return request.post(`/approval-forms/${id}/reject`, { comment })
}

/** 审批流转记录（审计日志 / 时间轴 / 打印签章来源） */
export function listActions(id) {
  return request.get(`/approval-forms/${id}/actions`)
}

/** 上传合同附件（PDF，覆盖式单附件） */
export function uploadFormAttachment(id, file) {
  const form = new FormData()
  form.append('file', file)
  return request.post(`/approval-forms/${id}/attachment`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/** AI 合同校对：审批单附件 ⇄ 合同管理原件文本比对 */
export function proofreadForm(id) {
  return request.post(`/approval-forms/${id}/proofread`, {}, { timeout: 120000 })
}

/** 以带 token 的请求拉取审批单合同附件为 Blob（预览 / 下载） */
export async function fetchFormAttachmentBlob(id) {
  const resp = await fetch(`/api/v1/approval-forms/${id}/attachment`, {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!resp.ok) throw new Error('附件获取失败')
  return await resp.blob()
}

/** 以带 token 的请求下载打印导出的 xlsx（服务端填充原始模板） */
export async function downloadFormPrint(id) {
  const resp = await fetch(`/api/v1/approval-forms/${id}/print`, {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!resp.ok) throw new Error('打印导出失败')
  return await resp.blob()
}
