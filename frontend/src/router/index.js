import { createRouter, createWebHistory } from 'vue-router'
import {
  APPROVAL_CENTER_ROLES,
  COMPANY_CODES,
  DIRECTOR_ROLES,
  FINANCE_ROLES,
  RESOURCE_CODES,
  ROLES
} from '@/constants/business'
import { legacySupplyRedirects } from './legacyRedirects'

export { ROLES } from '@/constants/business'

const supplyCompany = COMPANY_CODES.SUPPLY_MANAGEMENT

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/',
    component: () => import('@/layout/PortalLayout.vue'),
    children: [
      {
        path: '',
        name: 'PortalHome',
        component: () => import('@/views/portal/index.vue'),
        meta: { title: 'AI 助手' }
      },
      {
        path: 'investment',
        name: 'Investment',
        component: () => import('@/views/portal/ConstructionView.vue'),
        meta: {
          title: '山东出版投资有限公司',
          company: COMPANY_CODES.INVESTMENT,
          companyName: '山东出版投资有限公司'
        }
      },
      {
        path: 'fundmanagement',
        name: 'FundManagement',
        component: () => import('@/views/portal/ConstructionView.vue'),
        meta: {
          title: '山东出版股权基金管理有限公司',
          company: COMPANY_CODES.FUND_MANAGEMENT,
          companyName: '山东出版股权基金管理有限公司'
        }
      }
    ]
  },
  {
    path: '/supplymanagement/screen',
    name: 'Screen',
    component: () => import('@/views/screen/index.vue'),
    meta: {
      title: '数据投放大屏',
      company: supplyCompany,
      resource: RESOURCE_CODES.SUPPLY_DASHBOARD
    }
  },
  {
    path: '/supplymanagement',
    component: () => import('@/layout/index.vue'),
    redirect: '/supplymanagement/dashboard',
    meta: { company: supplyCompany },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: {
          title: '战略总览',
          icon: 'HomeFilled',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_DASHBOARD
        }
      },
      {
        path: 'operation',
        name: 'Operation',
        component: () => import('@/views/operation/index.vue'),
        meta: {
          title: '经营数据中心',
          icon: 'TrendCharts',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_OPERATION,
          roles: [ROLES.BUSINESS_HANDLER, ROLES.BUSINESS_REVIEWER, ...FINANCE_ROLES, ...DIRECTOR_ROLES]
        }
      },
      {
        path: 'cultural-tourism',
        name: 'CulturalTourism',
        component: () => import('@/views/cultural-tourism/MainView.vue'),
        meta: {
          title: '文旅业务',
          icon: 'Sunny',
          group: '渠道业务',
          groupIcon: 'Connection',
          company: supplyCompany,
          resource: RESOURCE_CODES.SCENIC_ANALYTICS,
          roles: [ROLES.BUSINESS_HANDLER, ROLES.BUSINESS_REVIEWER, ROLES.FINANCE_HANDLER, ...DIRECTOR_ROLES]
        }
      },
      {
        path: 'cultural-tourism/:scenicId',
        name: 'CulturalTourismDetail',
        component: () => import('@/views/cultural-tourism/DetailView.vue'),
        meta: {
          icon: 'Place',
          company: supplyCompany,
          resource: RESOURCE_CODES.SCENIC_ANALYTICS
        }
      },
      {
        path: 'finance/fund',
        name: 'FinanceFund',
        component: () => import('@/views/finance/fund.vue'),
        meta: {
          title: '资金管理',
          icon: 'Coin',
          group: '智慧财务',
          groupIcon: 'Wallet',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_FINANCE,
          roles: [ROLES.BUSINESS_HANDLER, ROLES.BUSINESS_REVIEWER, ...FINANCE_ROLES, ...DIRECTOR_ROLES]
        }
      },
      {
        path: 'finance/invoice',
        name: 'Invoice',
        component: () => import('@/views/invoice/index.vue'),
        meta: {
          title: '发票管理',
          icon: 'Tickets',
          group: '智慧财务',
          groupIcon: 'Wallet',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_FINANCE,
          roles: [ROLES.BUSINESS_HANDLER, ROLES.BUSINESS_REVIEWER, ...FINANCE_ROLES, ...DIRECTOR_ROLES]
        }
      },
      {
        path: 'contract',
        name: 'Contract',
        component: () => import('@/views/contract/index.vue'),
        meta: {
          title: '合同管理',
          icon: 'Document',
          group: '经营合规',
          groupIcon: 'DocumentChecked',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_CONTRACT,
          roles: [ROLES.BUSINESS_HANDLER, ROLES.BUSINESS_REVIEWER, ROLES.RISK_AUDITOR, ...DIRECTOR_ROLES, ROLES.LEGAL_COUNSEL]
        }
      },
      {
        path: 'approval',
        name: 'Approval',
        component: () => import('@/views/approval/index.vue'),
        meta: {
          title: '业务审批',
          icon: 'Stamp',
          group: '经营合规',
          groupIcon: 'DocumentChecked',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_APPROVAL,
          roles: APPROVAL_CENTER_ROLES
        }
      },
      {
        path: 'customer',
        name: 'Customer',
        component: () => import('@/views/customer/index.vue'),
        meta: {
          title: '客户档案库',
          icon: 'Postcard',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_CUSTOMER
        }
      },
      {
        path: 'org',
        name: 'Org',
        component: () => import('@/views/system/users.vue'),
        meta: {
          title: '用户管理',
          icon: 'OfficeBuilding',
          group: '系统管理',
          groupIcon: 'Setting',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_ADMIN,
          requiresSuperuser: true
        }
      },
      {
        path: 'audit',
        name: 'Audit',
        component: () => import('@/views/system/audit.vue'),
        meta: {
          title: '操作日志',
          icon: 'List',
          group: '系统管理',
          groupIcon: 'Setting',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_ADMIN,
          requiresSuperuser: true
        }
      },
      {
        path: 'ai-conversations',
        name: 'AiConversations',
        component: () => import('@/views/system/ai-conversations.vue'),
        meta: {
          title: 'AI 会话审计',
          icon: 'ChatLineSquare',
          group: '系统管理',
          groupIcon: 'Setting',
          company: supplyCompany,
          resource: RESOURCE_CODES.SUPPLY_ADMIN,
          requiresSuperuser: true
        }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/index.vue'),
        meta: { icon: 'User', company: supplyCompany }
      }
    ]
  },
  ...legacySupplyRedirects,
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
