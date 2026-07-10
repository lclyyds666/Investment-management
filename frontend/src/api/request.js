import axios from 'axios'
import { ElMessage } from 'element-plus'

const service = axios.create({
  baseURL: '/api/v1',
  timeout: 15000
})

// 请求拦截器：附加 token
service.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一处理后端 { code, message, data } 结构
service.interceptors.response.use(
  (response) => {
    const res = response.data
    // 业务包装结构 { code, message, data }
    if (res && typeof res.code !== 'undefined') {
      if (res.code !== 0) {
        ElMessage.error(res.message || '请求错误')
        return Promise.reject(new Error(res.message || 'Error'))
      }
      return res.data
    }
    // 非包装结构（如登录返回的 Token）直接返回
    return res
  },
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      // 令牌失效：清理并跳转登录
      localStorage.removeItem('token')
      localStorage.removeItem('role')
      if (location.hash !== '#/login' && !location.pathname.endsWith('/login')) {
        location.href = '/login'
      }
    }
    const detail = error.response?.data?.detail || error.response?.data?.message
    ElMessage.error(detail || error.message || '网络异常')
    return Promise.reject(error)
  }
)

export default service
