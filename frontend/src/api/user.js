import request from './request'

/** 当前用户资料（含签名） */
export function getMe() {
  return request.get('/users/me')
}

/** 上传/更新本人纸质签名（Mock：传 data-URI 或路径） */
export function updateSignature(signature) {
  return request.put('/users/me/signature', { signature })
}

/** 组织架构 / 人员列表 */
export function listUsers() {
  return request.get('/users')
}
