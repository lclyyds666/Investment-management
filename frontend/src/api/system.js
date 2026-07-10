import request from './request'

/** 健康检查 */
export function getHealth() {
  return request.get('/health')
}
