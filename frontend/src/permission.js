import { ElMessage } from 'element-plus'
import router from './router'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import { COMPANY_CODES, LEGAL_COUNSEL_PATHS, ROLES } from '@/constants/business'

const TITLE = import.meta.env.VITE_APP_TITLE || '山东出版投资有限公司工作平台'
const SUPPLY_DASHBOARD_PATH = '/supplymanagement/dashboard'
const SUPPLY_CONTRACT_PATH = '/supplymanagement/contract'

export const portalGuard = async (to) => {
  document.title = to.meta?.title ? `${to.meta.title} - ${TITLE}` : TITLE

  const userStore = useUserStore()
  const portalStore = usePortalStore()

  if (to.meta?.public) {
    if (to.path === '/login' && userStore.isLogin) return { path: '/' }
    return true
  }

  if (!userStore.isLogin) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (!userStore.userInfo) {
    try {
      await userStore.fetchUser()
    } catch (error) {
      userStore.logout()
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  try {
    await portalStore.loadPortalContext()
  } catch (error) {
    userStore.logout()
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (to.meta?.company && !portalStore.hasCompany(to.meta.company)) {
    ElMessage.error('无权访问该公司应用')
    return { path: '/' }
  }

  const isSupplyRoute = to.meta?.company === COMPANY_CODES.SUPPLY_MANAGEMENT
  if (
    isSupplyRoute &&
    !portalStore.isSuperuser &&
    portalStore.companyRole(COMPANY_CODES.SUPPLY_MANAGEMENT) === ROLES.LEGAL_COUNSEL &&
    !LEGAL_COUNSEL_PATHS.includes(to.path)
  ) {
    return { path: SUPPLY_CONTRACT_PATH }
  }

  if (to.meta?.resource && !portalStore.hasResource(to.meta.resource)) {
    ElMessage.error('权限不足，无法访问该页面')
    return { path: SUPPLY_DASHBOARD_PATH }
  }

  const roles = to.meta?.roles
  const companyRole = to.meta?.company ? portalStore.companyRole(to.meta.company) : ''
  if (roles?.length && !portalStore.isSuperuser && !roles.includes(companyRole)) {
    ElMessage.error('权限不足，无法访问该页面')
    return { path: SUPPLY_DASHBOARD_PATH }
  }

  if (to.meta?.requiresSuperuser && !portalStore.isSuperuser) {
    ElMessage.error('该页面仅超级管理员可访问')
    return { path: SUPPLY_DASHBOARD_PATH }
  }

  return true
}

router.beforeEach(portalGuard)
