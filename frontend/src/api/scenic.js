import request from './request'

// 文旅业务·景区核销台账 API —— 所有请求都以 scenicId 作用域，后端按 scenic_id 隔离。

/** 查询某景区台账（仅返回该景区数据） */
export function getScenicLedger(scenicId) {
  return request.get(`/scenic-spots/${encodeURIComponent(scenicId)}/ledger`)
}

/** 上传 Excel 核销台账（数据强制归属该景区） */
export function uploadScenicLedger(scenicId, file) {
  const form = new FormData()
  form.append('file', file)
  return request.post(`/scenic-spots/${encodeURIComponent(scenicId)}/ledger`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/** 清空某景区台账（仅清该景区） */
export function clearScenicLedger(scenicId) {
  return request.delete(`/scenic-spots/${encodeURIComponent(scenicId)}/ledger`)
}

/** 景区经营数据卡片：销售额/核销数/核销率（门票+酒店台账聚合，每景区独立） */
export function getScenicMetrics(scenicId) {
  return request.get(`/scenic-spots/${encodeURIComponent(scenicId)}/metrics`)
}
