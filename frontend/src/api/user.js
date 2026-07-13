import request from './request'

/** 当前用户资料（含签名） */
export function getMe() {
  return request.get('/users/me')
}

/** 上传/更新本人纸质签名（Mock：传 data-URI 或路径） */
export function updateSignature(signature) {
  return request.put('/users/me/signature', { signature })
}

/** 修改本人密码 */
export function changeMyPassword(oldPassword, newPassword) {
  return request.put('/users/me/password', { old_password: oldPassword, new_password: newPassword })
}

/** 用户列表 / 组织架构（支持 keyword / role / is_active 筛选） */
export function listUsers(params = {}) {
  return request.get('/users', { params })
}

/** 创建用户（超管） */
export function createUser(data) {
  return request.post('/users', data)
}

/** 编辑用户（超管） */
export function updateUser(id, data) {
  return request.put(`/users/${id}`, data)
}

/** 启用/停用用户（超管） */
export function setUserActive(id, isActive) {
  return request.put(`/users/${id}/active`, { is_active: isActive })
}

/** 重置用户密码（超管；不传则重置为系统默认密码） */
export function resetUserPassword(id, newPassword) {
  return request.post(`/users/${id}/reset-password`, newPassword ? { new_password: newPassword } : {})
}

/** 删除用户（超管） */
export function deleteUser(id) {
  return request.delete(`/users/${id}`)
}
