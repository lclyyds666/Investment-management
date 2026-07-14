import { ElMessage } from 'element-plus'
import router from './router'
import { useUserStore } from '@/store/user'

const TITLE = import.meta.env.VITE_APP_TITLE || '业务平台'

router.beforeEach(async (to) => {
  document.title = to.meta?.title ? `${to.meta.title} - ${TITLE}` : TITLE

  const userStore = useUserStore()

  // 公共页面（登录、404）直接放行
  if (to.meta?.public) {
    // 已登录用户访问登录页则回首页
    if (to.path === '/login' && userStore.isLogin) return { path: '/' }
    return true
  }

  // 未登录 → 跳登录页并带上回跳地址
  if (!userStore.isLogin) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 已登录但还没有用户信息（如刷新页面）→ 拉取一次
  if (!userStore.userInfo) {
    try {
      await userStore.fetchUser()
    } catch (e) {
      userStore.logout()
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  // 仅超级管理员页面：非超管即便直访 URL 也拦回首页
  if (to.meta?.requiresSuperuser && !userStore.isSuperuser) {
    ElMessage.error('该页面仅超级管理员可访问')
    return { path: '/dashboard' }
  }

  // 角色拦截
  const roles = to.meta?.roles
  if (roles && roles.length && !userStore.hasRole(roles)) {
    ElMessage.error('权限不足，无法访问该页面')
    return { path: '/dashboard' }
  }

  return true
})
