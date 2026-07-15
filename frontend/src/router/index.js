import { createRouter, createWebHistory } from 'vue-router'
import { ROLES, APPROVER_ROLES, DIRECTOR_ROLES, FINANCE_ROLES } from '@/constants/business'

// 兼容旧引用：从常量集中转出
export { ROLES } from '@/constants/business'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/screen',
    name: 'Screen',
    component: () => import('@/views/screen/index.vue'),
    meta: { title: '数据投放大屏' }
  },
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '战略总览', icon: 'HomeFilled' }
      },
      {
        path: 'operation',
        name: 'Operation',
        component: () => import('@/views/operation/index.vue'),
        // 经营数据中心：风控/财务/负责人可查看
        meta: {
          title: '经营数据中心',
          icon: 'TrendCharts',
          roles: [ROLES.RISK_AUDITOR, ...FINANCE_ROLES, ...DIRECTOR_ROLES]
        }
      },
      {
        path: 'channel',
        name: 'Channel',
        component: () => import('@/views/channel/index.vue'),
        meta: { title: '渠道业务管理', icon: 'Connection' }
      },
      {
        path: 'finance/fund',
        name: 'FinanceFund',
        component: () => import('@/views/finance/fund.vue'),
        // 资金管理：归入「智慧财务管理」菜单组；当前为存根页
        meta: {
          title: '资金管理',
          icon: 'Coin',
          roles: [...FINANCE_ROLES, ...DIRECTOR_ROLES],
          group: '智慧财务管理',
          groupIcon: 'Wallet'
        }
      },
      {
        path: 'finance/invoice',
        name: 'Invoice',
        component: () => import('@/views/invoice/index.vue'),
        // 发票管理：归入「智慧财务管理」菜单组；财务 + 负责人
        meta: {
          title: '发票管理',
          icon: 'Tickets',
          roles: [...FINANCE_ROLES, ...DIRECTOR_ROLES],
          group: '智慧财务管理',
          groupIcon: 'Wallet'
        }
      },
      {
        path: 'contract',
        name: 'Contract',
        component: () => import('@/views/contract/index.vue'),
        // 合同管理：归入「经营合规管理」一级菜单；全部角色可进入，页面内按角色控制操作
        meta: { title: '合同管理', icon: 'Document', group: '经营合规管理', groupIcon: 'DocumentChecked' }
      },
      {
        path: 'approval',
        name: 'Approval',
        component: () => import('@/views/approval/index.vue'),
        // 业务审批(原审批中心)：日常业务类审批，当前为存根页（功能建设中）；
        // 合同(法律)类审批已内嵌到「合同管理」页，两条审批路径互不干扰。
        meta: { title: '业务审批', icon: 'Stamp', roles: APPROVER_ROLES, group: '经营合规管理', groupIcon: 'DocumentChecked' }
      },
      {
        path: 'customer',
        name: 'Customer',
        component: () => import('@/views/customer/index.vue'),
        meta: { title: '客户档案库', icon: 'Postcard' }
      },
      {
        // 兼容旧地址 /invoice → 新地址 /finance/invoice
        path: 'invoice',
        redirect: '/finance/invoice'
      },
      {
        path: 'org',
        name: 'Org',
        component: () => import('@/views/system/users.vue'),
        // 用户管理：仅超级管理员可见 / 可访问（菜单隐藏 + 路由守卫双保险）
        meta: { title: '用户管理', icon: 'OfficeBuilding', requiresSuperuser: true }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/index.vue'),
        // 个人设置：不进侧边菜单（无 title），经顶部下拉进入
        meta: { icon: 'User' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在', public: true }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router
