import request from './request'

// 操作审计（仅超级管理员）

/** 分页查询审计日志。params: {keyword,module,action,status,method,start,end,page,size} */
export function listAuditLogs(params) {
  return request.get('/audit/logs', { params })
}

/** 筛选枚举（动作/模块）供下拉 */
export function getAuditMeta() {
  return request.get('/audit/meta')
}

/** 导出 CSV（带 token 取 Blob，按同筛选条件） */
export async function fetchAuditExportBlob(params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString()
  const resp = await fetch(`/api/v1/audit/logs/export?${qs}`, {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!resp.ok) throw new Error('审计导出失败')
  return await resp.blob()
}

/** 退出登录留痕（best-effort，失败不阻断前端登出） */
export function logout() {
  return request.post('/auth/logout').catch(() => {})
}
