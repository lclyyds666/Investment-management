import { ROLES } from '@/constants/business'

export const LEGAL_CAPABILITIES = Object.freeze({
  VIEW_CASE: 'view_case',
  EDIT_CASE: 'edit_case',
  ACTIVATE_CASE: 'activate_case',
  MANAGE_DETAIL: 'manage_detail',
  ADD_COUNSEL_CONTENT: 'add_counsel_content',
  UPLOAD_ATTACHMENT: 'upload_attachment',
  DELETE_ATTACHMENT: 'delete_attachment',
  MANAGE_ALERT: 'manage_alert',
  ARCHIVE_CASE: 'archive_case',
  VIEW_STATISTICS: 'view_statistics',
  IMPORT_EXPORT: 'import_export',
  EXPORT_MANAGEMENT: 'export_management',
  ADMIN: 'admin'
})

const ALL_CAPABILITIES = Object.freeze(Object.values(LEGAL_CAPABILITIES))
const GENERAL_ROLES = new Set([
  ROLES.BUSINESS_HANDLER,
  ROLES.BUSINESS_REVIEWER,
  ROLES.RISK_AUDITOR,
  ROLES.FINANCE_HANDLER,
  ROLES.FINANCE_REVIEWER,
  ROLES.SCM_DIRECTOR
])
const BUSINESS_CAPABILITIES = new Set(
  ALL_CAPABILITIES.filter((capability) => capability !== LEGAL_CAPABILITIES.ADMIN)
)
const MANAGEMENT_CAPABILITIES = new Set([
  LEGAL_CAPABILITIES.VIEW_CASE,
  LEGAL_CAPABILITIES.VIEW_STATISTICS,
  LEGAL_CAPABILITIES.EXPORT_MANAGEMENT
])
const COUNSEL_CAPABILITIES = new Set([
  LEGAL_CAPABILITIES.VIEW_CASE,
  LEGAL_CAPABILITIES.ADD_COUNSEL_CONTENT,
  LEGAL_CAPABILITIES.UPLOAD_ATTACHMENT,
  LEGAL_CAPABILITIES.DELETE_ATTACHMENT,
  LEGAL_CAPABILITIES.MANAGE_ALERT
])
const BUSINESS_POSITION_CODES = new Set([
  'investment.department.director',
  'investment.department.deputy_director',
  'investment.department.senior_manager',
  'investment.department.middle_manager',
  'investment.department.junior_manager',
  'supply.business_handler',
  'supply.business_reviewer',
  'supply.finance_handler',
  'supply.company_leader',
  'investment.duty.supply_risk_review',
  'investment.duty.supply_finance_review'
])
const MANAGEMENT_POSITION_CODES = new Set([
  'investment.executive.chairman',
  'investment.executive.general_manager',
  'investment.executive.deputy_general_manager',
  'governance.supply_leader'
])
const COUNSEL_POSITION_CODES = new Set(['external.legal_counsel'])

export function legalCapabilities(role, isSuperuser = false) {
  if (isSuperuser) return new Set(ALL_CAPABILITIES)
  if (GENERAL_ROLES.has(role)) return new Set(BUSINESS_CAPABILITIES)
  if (role === ROLES.INVEST_DIRECTOR) return new Set(MANAGEMENT_CAPABILITIES)
  if (role === ROLES.LEGAL_COUNSEL) return new Set(COUNSEL_CAPABILITIES)
  return new Set()
}

export function legalCapabilitiesForAssignments(assignments = [], isSuperuser = false) {
  if (isSuperuser) return new Set(ALL_CAPABILITIES)
  const positionCodes = new Set(assignments.map((item) => item?.position_code).filter(Boolean))
  const capabilities = new Set()
  if ([...positionCodes].some((code) => BUSINESS_POSITION_CODES.has(code))) {
    BUSINESS_CAPABILITIES.forEach((capability) => capabilities.add(capability))
  }
  if ([...positionCodes].some((code) => MANAGEMENT_POSITION_CODES.has(code))) {
    MANAGEMENT_CAPABILITIES.forEach((capability) => capabilities.add(capability))
  }
  if ([...positionCodes].some((code) => COUNSEL_POSITION_CODES.has(code))) {
    COUNSEL_CAPABILITIES.forEach((capability) => capabilities.add(capability))
  }
  return capabilities
}

export function hasLegalCapability(role, capability, isSuperuser = false, assignments = []) {
  const capabilities = assignments.length
    ? legalCapabilitiesForAssignments(assignments, isSuperuser)
    : legalCapabilities(role, isSuperuser)
  return capabilities.has(capability)
}

export function canDeleteLegalAttachment({
  role,
  isSuperuser = false,
  currentUserId,
  archivedAt,
  assignments = []
}, attachment) {
  if (archivedAt) return false
  const capabilities = assignments.length
    ? legalCapabilitiesForAssignments(assignments, isSuperuser)
    : legalCapabilities(role, isSuperuser)
  if (capabilities.has(LEGAL_CAPABILITIES.MANAGE_DETAIL)) return true
  return capabilities.has(LEGAL_CAPABILITIES.DELETE_ATTACHMENT)
    && Number(attachment?.uploaded_by) === Number(currentUserId)
}
