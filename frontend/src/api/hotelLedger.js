import request from './request'

// 文旅业务·景区酒店平台核销业务台账 API（按 scenicId 作用域，后端按 scenic_id 隔离）

/** 上传单个对账明细并解析（单文件=一期，内含多平台），返回按平台聚合结果 */
export function parseHotelFile(scenicId, file) {
  const form = new FormData()
  form.append('files', file)
  return request.post(
    `/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger/parse`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }
  )
}

/** 查询某景区酒店平台业务台账（含合计） */
export function getHotelLedger(scenicId) {
  return request.get(`/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger`)
}

/** 保存台账（确认后落库；mode: 'append' 追加 / 'replace' 覆盖） */
export function saveHotelLedger(scenicId, rows, mode = 'append') {
  return request.post(`/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger`, { rows, mode })
}

/** 编辑台账单行（佣金/核销率/每间夜服务费/间夜/付款金额/回款） */
export function updateHotelRow(scenicId, rowId, payload) {
  return request.put(`/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger/${rowId}`, payload)
}

/** 删除台账单行 */
export function deleteHotelRow(scenicId, rowId) {
  return request.delete(`/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger/${rowId}`)
}

/** 导出台账 xlsx（带 token 取 Blob） */
export async function fetchHotelLedgerExportBlob(scenicId) {
  const resp = await fetch(
    `/api/v1/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger/export`,
    { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
  )
  if (!resp.ok) throw new Error('台账导出失败')
  return await resp.blob()
}

/** 拉取对账明细源文件为 Blob（预览/下载） */
export async function fetchHotelDetailBlob(scenicId, stored, name = '') {
  const q = new URLSearchParams({ stored, name }).toString()
  const resp = await fetch(
    `/api/v1/scenic-spots/${encodeURIComponent(scenicId)}/hotel-ledger/detail?${q}`,
    { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
  )
  if (!resp.ok) throw new Error('明细源文件获取失败')
  return await resp.blob()
}
