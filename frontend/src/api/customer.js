import request from './request'

export function listCustomers() {
  return request.get('/customers')
}
export function getCustomer(id) {
  return request.get(`/customers/${id}`)
}
export function createCustomer(data) {
  return request.post('/customers', data)
}
export function updateCustomer(id, data) {
  return request.put(`/customers/${id}`, data)
}
export function deleteCustomer(id) {
  return request.delete(`/customers/${id}`)
}

/* ---------------- AI 尽职调查 ---------------- */

/** 客户准入资料列表 */
export function listMaterials(cid) {
  return request.get(`/customers/${cid}/materials`)
}

/** 上传并解析准入资料（pdf/docx） */
export function uploadMaterial(cid, file) {
  const form = new FormData()
  form.append('file', file)
  return request.post(`/customers/${cid}/materials`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/** 删除准入资料 */
export function deleteMaterial(cid, mid) {
  return request.delete(`/customers/${cid}/materials/${mid}`)
}

/** 资料原件的下载接口路径 */
export function materialDownloadUrl(cid, mid) {
  return `/api/v1/customers/${cid}/materials/${mid}/download`
}

/** 以带 token 的请求拉取资料原件为 Blob（用于预览/下载，规避静态直链无鉴权问题） */
export async function fetchMaterialBlob(cid, mid) {
  const resp = await fetch(materialDownloadUrl(cid, mid), {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!resp.ok) throw new Error('文件获取失败')
  return await resp.blob()
}

/** 生成 AI 尽职调查报告（耗时 20-60s） */
export function generateResearch(cid) {
  return request.post(`/customers/${cid}/research`, {}, { timeout: 120000 })
}

/** 获取最近一次尽调报告 */
export function getResearch(cid) {
  return request.get(`/customers/${cid}/research`)
}
