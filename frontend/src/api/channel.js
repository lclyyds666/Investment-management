import request from './request'

export function listChannels() {
  return request.get('/channels')
}
export function getChannelData(id) {
  return request.get(`/channels/${id}/data`)
}
/** 回传/导入渠道表格数据（覆盖式） */
export function importChannelData(id, columns, rows) {
  return request.put(`/channels/${id}/data`, { columns, rows })
}
