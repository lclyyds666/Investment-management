import request from './request'

/** 获取图形验证码，返回 { captcha_id, image(SVG data-uri), ttl } */
export function getCaptcha() {
  return request.get('/auth/captcha')
}

/**
 * 登录。后端使用 OAuth2PasswordRequestForm，
 * 需以 application/x-www-form-urlencoded 提交 username/password，
 * 并附带图形验证码 captcha_id + captcha_code。
 */
export function login(username, password, captchaId, captchaCode) {
  const params = new URLSearchParams()
  params.append('username', username)
  params.append('password', password)
  if (captchaId) params.append('captcha_id', captchaId)
  if (captchaCode) params.append('captcha_code', captchaCode)
  return request.post('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  })
}

/** 获取当前登录用户 */
export function getMe() {
  return request.get('/auth/me')
}
