import request from './request'

/**
 * 登录。后端使用 OAuth2PasswordRequestForm，
 * 需以 application/x-www-form-urlencoded 提交 username/password。
 */
export function login(username, password) {
  const params = new URLSearchParams()
  params.append('username', username)
  params.append('password', password)
  return request.post('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  })
}

/** 获取当前登录用户 */
export function getMe() {
  return request.get('/auth/me')
}
