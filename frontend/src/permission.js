import { ElMessage } from 'element-plus'
import router from './router'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import { COMPANY_CODES } from '@/constants/business'
import { hasLegalCapability } from '@/utils/legalCapabilities'

const TITLE = import.meta.env.VITE_APP_TITLE || '山东出版投资有限公司工作平台'
const SUPPLY_DASHBOARD_PATH = '/supplymanagement/dashboard'
const SUPPLY_CONTRACT_PATH = '/supplymanagement/contract'
const INVESTMENT_CASES_PATH = '/investment/legal-risk/cases'

const companyFallback = (company) => company === COMPANY_CODES.INVESTMENT
  ? INVESTMENT_CASES_PATH
  : SUPPLY_DASHBOARD_PATH

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

  if (to.meta?.requiresSuperuser && !portalStore.isSuperuser) {
    ElMessage.error('该页面仅超级管理员可访问')
    return { path: SUPPLY_DASHBOARD_PATH }
  }

  if (to.meta?.permission && !portalStore.hasPermission(to.meta.permission)) {
    ElMessage.error('权限不足，无法访问该页面')
    return { path: '/' }
  }

  if (to.meta?.company && !portalStore.hasCompany(to.meta.company)) {
    ElMessage.error('无权访问该公司应用')
    return { path: '/' }
  }

  if (to.meta?.resource && !portalStore.hasResource(to.meta.resource)) {
    ElMessage.error('权限不足，无法访问该页面')
    return { path: companyFallback(to.meta?.company) }
  }

  if (to.meta?.legalCapability && !hasLegalCapability(
    portalStore.companyRole(COMPANY_CODES.INVESTMENT),
    to.meta.legalCapability,
    portalStore.isSuperuser,
    portalStore.assignments
  )) {
    ElMessage.error('权限不足，无法执行该法务操作')
    return { path: INVESTMENT_CASES_PATH }
  }

  return true
}

router.beforeEach(portalGuard)
