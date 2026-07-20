import request from './request'

// 文旅业务·门票平台核销业务台账 API —— 均以 scenicId 作用域，后端按 scenic_id 隔离。

/** 批量上传对账明细并解析（算服务商到账+周期，不落库），返回每文件汇总 */
export function parseTicketFiles(scenicId, files) {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  return request.post(
    `/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger/parse`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }
  )
}

/** 查询某景区门票平台业务台账（含合计） */
export function getTicketLedger(scenicId) {
  return request.get(`/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger`)
}

/** 保存台账（确认后落库；mode: 'replace' 覆盖 / 'append' 追加） */
export function saveTicketLedger(scenicId, rows, mode = 'replace') {
  return request.post(
    `/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger`,
    { rows, mode }
  )
}

/** 编辑台账单行（回款/付款日期/平台/B 等） */
export function updateTicketRow(scenicId, rowId, payload) {
  return request.put(
    `/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger/${rowId}`,
    payload
  )
}

/** 删除台账单行 */
export function deleteTicketRow(scenicId, rowId) {
  return request.delete(
    `/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger/${rowId}`
  )
}

/** 清空某景区门票平台业务台账 */
export function clearTicketLedger(scenicId) {
  return request.delete(`/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger`)
}

/** 导出标准格式业务台账 xlsx（带 token 取 Blob） */
export async function fetchTicketLedgerExportBlob(scenicId) {
  const resp = await fetch(
    `/api/v1/scenic-spots/${encodeURIComponent(scenicId)}/ticket-ledger/export`,
    { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
  )
  if (!resp.ok) throw new Error('台账导出失败')
  return await resp.blob()
}
