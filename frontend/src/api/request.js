import axios from 'axios'
import { ElMessage } from 'element-plus'

const service = axios.create({
  baseURL: '/api/v1',
  // 全局默认超时 30s（原 15s 过短，冷启动/复杂聚合易被中断）；
  // 上传/解析/导出/AI 等耗时接口在各自 api 里单独放大到 60s~120s。
  timeout: 30000
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

    // 友好错误提示：不向用户暴露原始 Axios 报错（如 "timeout of 15000ms exceeded"）
    let msg
    const detail = error.response?.data?.detail || error.response?.data?.message
    if (detail) {
      msg = detail
    } else if (error.code === 'ECONNABORTED' || /timeout/i.test(error.message || '')) {
      // 超时：多见于大文件上传 / 台账计算 / 后端冷启动
      msg = '请求超时，请稍后重试；上传大文件或复杂计算可能耗时较长，请耐心等待。'
    } else if (!error.response) {
      // 无响应：网络断开 / 跨域 / 服务未启动
      msg = '网络连接异常，请检查网络后重试。'
    } else if (status >= 500) {
      msg = '服务器繁忙，请稍后重试。'
    } else {
      msg = error.message || '请求失败，请稍后重试。'
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

export default service
