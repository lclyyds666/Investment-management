import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getMe } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const role = ref(localStorage.getItem('role') || '')
  const userInfo = ref(null)

  const isLogin = computed(() => !!token.value)
  const isSuperuser = computed(() => !!userInfo.value?.is_superuser)
  const signature = computed(() => userInfo.value?.signature || '')
  const roleLabel = computed(() => userInfo.value?.role_label || '')

  function _persist() {
    localStorage.setItem('token', token.value)
    localStorage.setItem('role', role.value)
  }

  /** 登录：拿到 token 与角色并持久化 */
  async function login(username, password, captchaId, captchaCode) {
    const res = await loginApi(username, password, captchaId, captchaCode)
    token.value = res.access_token
    role.value = res.role
    userInfo.value = res.user
    _persist()
    return res
  }

  /** 刷新页面后用 token 拉取当前用户信息 */
  async function fetchUser() {
    const res = await getMe()
    userInfo.value = res
    role.value = res.role
    localStorage.setItem('role', role.value)
    return res
  }

  /** 局部更新当前用户信息（如上传签名后） */
  function setUserInfo(info) {
    userInfo.value = info
    if (info?.role) {
      role.value = info.role
      localStorage.setItem('role', role.value)
    }
  }

  function logout() {
    token.value = ''
    role.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('role')
  }

  /** 判断当前角色是否在允许列表内；超级管理员始终放行 */
  function hasRole(roles) {
    if (!roles || roles.length === 0) return true
    if (isSuperuser.value) return true
    return roles.includes(role.value)
  }

  return {
    token, role, userInfo, isLogin, isSuperuser, signature, roleLabel,
    login, fetchUser, setUserInfo, logout, hasRole
  }
})
