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
        meta: { title: '首页', icon: 'HomeFilled' }
      },
      {
        path: 'operation',
        name: 'Operation',
        component: () => import('@/views/operation/index.vue'),
        // 经营数据：风控/财务/负责人可查看
        meta: {
          title: '经营数据',
          icon: 'TrendCharts',
          roles: [ROLES.RISK_AUDITOR, ...FINANCE_ROLES, ...DIRECTOR_ROLES]
        }
      },
      {
        path: 'contract',
        name: 'Contract',
        component: () => import('@/views/contract/index.vue'),
        // 合同管理：全部角色可进入，页面内按角色控制操作
        meta: { title: '合同管理', icon: 'Document' }
      },
      {
        path: 'approval',
        name: 'Approval',
        component: () => import('@/views/approval/index.vue'),
        // 审批中心：6 级审批人角色
        meta: { title: '审批中心', icon: 'Stamp', roles: APPROVER_ROLES }
      },
      {
        path: 'customer',
        name: 'Customer',
        component: () => import('@/views/customer/index.vue'),
        meta: { title: '客户档案', icon: 'Postcard' }
      },
      {
        path: 'channel',
        name: 'Channel',
        component: () => import('@/views/channel/index.vue'),
        meta: { title: '渠道集成', icon: 'Connection' }
      },
      {
        path: 'invoice',
        name: 'Invoice',
        component: () => import('@/views/invoice/index.vue'),
        // 发票管理：财务 + 负责人
        meta: { title: '发票管理', icon: 'Tickets', roles: [...FINANCE_ROLES, ...DIRECTOR_ROLES] }
      },
      {
        path: 'org',
        name: 'Org',
        component: () => import('@/views/system/users.vue'),
        // 用户管理 / 组织架构：负责人可查看，增删改由页面内按超管控制
        meta: { title: '用户管理', icon: 'OfficeBuilding', roles: DIRECTOR_ROLES }
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
