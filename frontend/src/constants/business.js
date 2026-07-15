// 业务常量：7 级角色、审批链、合同类型、状态 —— 与后端 app/core/enums.py 对齐

export const ROLES = {
  BUSINESS_HANDLER: 'business_handler',   // 业务经办
  BUSINESS_REVIEWER: 'business_reviewer', // 业务复核
  RISK_AUDITOR: 'risk_auditor',           // 投资公司法务风控（原风控审核，值不变）
  FINANCE_HANDLER: 'finance_handler',     // 财务经办
  FINANCE_REVIEWER: 'finance_reviewer',   // 投资公司财务复核（原财务复核，值不变）
  SCM_DIRECTOR: 'scm_director',           // 供管公司负责人
  INVEST_DIRECTOR: 'invest_director',     // 投资公司分管领导（原投资公司负责人，值不变）
  LEGAL_COUNSEL: 'legal_counsel'          // 法律顾问：仅看合同管理 + 审批中心给意见
}

export const ROLE_LABELS = {
  business_handler: '业务经办',
  business_reviewer: '业务复核',
  risk_auditor: '投资公司法务风控',
  finance_handler: '财务经办',
  finance_reviewer: '投资公司财务复核',
  scm_director: '供管公司负责人',
  invest_director: '投资公司分管领导',
  legal_counsel: '法律顾问'
}

export const roleLabel = (v) => ROLE_LABELS[v] || v || '—'

// 合同审批链，顺序即流转顺序（index === step）
//   业务经办 → 供管公司负责人 → 法律顾问 → 投资公司法务风控 → 投资公司分管领导
export const APPROVAL_CHAIN = [
  ROLES.BUSINESS_HANDLER,
  ROLES.SCM_DIRECTOR,
  ROLES.LEGAL_COUNSEL,
  ROLES.RISK_AUDITOR,
  ROLES.INVEST_DIRECTOR
]

// 审批中心的审批人角色（除业务经办外的节点；业务经办在提交时自动完成第 0 级）
export const APPROVER_ROLES = APPROVAL_CHAIN.slice(1)
export const DIRECTOR_ROLES = [ROLES.SCM_DIRECTOR, ROLES.INVEST_DIRECTOR]
export const FINANCE_ROLES = [ROLES.FINANCE_HANDLER, ROLES.FINANCE_REVIEWER]

// 法律顾问：仅可访问「合同管理」+「审批中心」两个页面（其余菜单/路由全部隐藏拦截）
export const LEGAL_COUNSEL_PATHS = ['/contract', '/approval', '/profile']

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
  rejected: { text: '已驳回', type: 'danger' }
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
