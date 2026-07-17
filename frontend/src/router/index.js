import { createRouter, createWebHistory } from 'vue-router'
import { ROLES, APPROVER_ROLES, DIRECTOR_ROLES, FINANCE_ROLES, APPROVAL_CENTER_ROLES } from '@/constants/business'

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
        // 渠道业务 · 文旅业务：入口页（MainView，景区卡片 Grid）。保留原菜单分组与位置。
        path: 'cultural-tourism',
        name: 'CulturalTourism',
        component: () => import('@/views/cultural-tourism/MainView.vue'),
        meta: { title: '文旅业务', icon: 'Sunny', group: '渠道业务', groupIcon: 'Connection' }
      },
      {
        // 景区详情页（DetailView，动态路由）：与 MainView 共用全局外壳，不进侧边菜单(无 title)
        path: 'cultural-tourism/:scenicId',
        name: 'CulturalTourismDetail',
        component: () => import('@/views/cultural-tourism/DetailView.vue'),
        meta: { icon: 'Place' }
      },
      {
        // 兼容旧地址 /channel、/channel/tourism、/channel/other → 新文旅业务入口
        path: 'channel',
        redirect: '/cultural-tourism'
      },
      {
        path: 'channel/tourism',
        redirect: '/cultural-tourism'
      },
      {
        path: 'channel/other',
        redirect: '/cultural-tourism'
      },
      {
        path: 'finance/fund',
        name: 'FinanceFund',
        component: () => import('@/views/finance/fund.vue'),
        // 资金管理：归入「智慧财务」菜单组；当前为存根页
        meta: {
          title: '资金管理',
          icon: 'Coin',
          roles: [...FINANCE_ROLES, ...DIRECTOR_ROLES],
          group: '智慧财务',
          groupIcon: 'Wallet'
        }
      },
      {
        path: 'finance/invoice',
        name: 'Invoice',
        component: () => import('@/views/invoice/index.vue'),
        // 发票管理：归入「智慧财务」菜单组；财务 + 负责人
        meta: {
          title: '发票管理',
          icon: 'Tickets',
          roles: [...FINANCE_ROLES, ...DIRECTOR_ROLES],
          group: '智慧财务',
          groupIcon: 'Wallet'
        }
      },
      {
        path: 'contract',
        name: 'Contract',
        component: () => import('@/views/contract/index.vue'),
        // 合同管理：归入「经营合规」一级菜单；全部角色可进入，页面内按角色控制操作
        meta: { title: '合同管理', icon: 'Document', group: '经营合规', groupIcon: 'DocumentChecked' }
      },
      {
        path: 'approval',
        name: 'Approval',
        component: () => import('@/views/approval/index.vue'),
        // 审批中心：两套独立审批单工作流（业务付款审批单 / 业务审批单）。
        // 业务经办创建并提交，其余链上角色逐级审批；与合同(法律)审批互不干扰。
        meta: { title: '业务审批', icon: 'Stamp', roles: APPROVAL_CENTER_ROLES, group: '经营合规', groupIcon: 'DocumentChecked' }
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
