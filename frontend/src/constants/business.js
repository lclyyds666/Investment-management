// 业务常量：公司、角色标签、合同类型与状态

export const COMPANY_CODES = {
  INVESTMENT: 'investment',
  SUPPLY_MANAGEMENT: 'supplymanagement',
  FUND_MANAGEMENT: 'fundmanagement'
}

export const COMPANY_NAMES = {
  investment: '山东出版投资有限公司',
  supplymanagement: '山东出版供应链管理有限公司',
  fundmanagement: '山东出版股权基金管理有限公司',
  zhanwei: '山东展威科技有限公司'
}

export const RESOURCE_CODES = {
  INVEST_LEGAL_DASHBOARD: 'invest.legal.dashboard',
  INVEST_LEGAL_CASES: 'invest.legal.cases',
  INVEST_LEGAL_ALERTS: 'invest.legal.alerts',
  INVEST_LEGAL_STATISTICS: 'invest.legal.statistics',
  INVEST_LEGAL_ADMIN: 'invest.legal.admin',
  SUPPLY_DASHBOARD: 'supply.dashboard',
  SUPPLY_OPERATION: 'supply.operation',
  SCENIC_ANALYTICS: 'supply.scenic.analytics',
  SUPPLY_FINANCE: 'supply.finance',
  SUPPLY_CONTRACT: 'supply.contract',
  SUPPLY_APPROVAL: 'supply.approval',
  SUPPLY_CUSTOMER: 'supply.customer',
  SUPPLY_ADMIN: 'supply.admin'
}

export const ROLES = {
  BUSINESS_HANDLER: 'business_handler',   // 业务经办
  BUSINESS_REVIEWER: 'business_reviewer', // 业务复核
  RISK_AUDITOR: 'risk_auditor',           // 投资公司法务风控（原风控审核，值不变）
  FINANCE_HANDLER: 'finance_handler',     // 财务经办
  FINANCE_REVIEWER: 'finance_reviewer',   // 投资公司财务复核（原财务复核，值不变）
  SCM_DIRECTOR: 'scm_director',           // 供管公司负责人
  INVEST_DIRECTOR: 'invest_director',     // 投资公司总经理（原投资公司分管领导/负责人，值不变）
  LEGAL_COUNSEL: 'legal_counsel',         // 法律顾问：仅看合同管理 + 审批中心给意见
  INFO_MAINTAINER: 'info_maintainer'      // 信息维护：超管账号身份，不在 7 级审批链，权限来自超管
}

export const ROLE_LABELS = {
  business_handler: '业务经办',
  business_reviewer: '业务复核',
  risk_auditor: '投资公司法务风控',
  finance_handler: '财务经办',
  finance_reviewer: '投资公司财务复核',
  scm_director: '供管公司负责人',
  invest_director: '投资公司总经理',
  legal_counsel: '法律顾问',
  info_maintainer: '信息维护'
}

export const roleLabel = (v) => ROLE_LABELS[v] || v || '—'

// 合同/审批单类型
export const CONTRACT_TYPES = {
  PAYMENT: 'payment',   // 业务付款审批单
  BUSINESS: 'business'  // 业务审批单
}
export const CONTRACT_TYPE_LABELS = {
  payment: '业务付款审批单',
  business: '业务审批单'
}

// 合同状态
export const STATUS_META = {
  draft: { text: '草稿', type: 'info' },
  pending: { text: '审批中', type: 'warning' },
  approved: { text: '已通过', type: 'success' },
  rejected: { text: '已退回', type: 'danger' }
}

// 发票开票状态
export const INVOICE_STATUS_META = {
  pending: { text: '待开票', type: 'warning' },
  issued: { text: '已开票', type: 'success' },
  void: { text: '已作废', type: 'info' }
}

// 渠道平台类别
export const CHANNEL_CATEGORY_LABELS = {
  ticket: '景区门票',
  hotel: '酒店数据',
  ota: '综合 OTA',
  other: '其他平台'
}
