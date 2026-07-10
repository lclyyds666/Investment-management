import request from './request'

export function listChannels() {
  return request.get('/channels')
}
export function getChannelData(id) {
  return request.get(`/channels/${id}/data`)
}
/** 回传/导入渠道表格数据（覆盖式）；mapping 配置后按映射汇入经营看板 */
export function importChannelData(id, columns, rows, mapping = null) {
  return request.put(`/channels/${id}/data`, { columns, rows, mapping })
}
