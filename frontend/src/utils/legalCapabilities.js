export const LEGAL_CAPABILITIES = Object.freeze({
  VIEW_CASE: 'view_case',
  CREATE_CASE: 'create_case',
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

const CAPABILITY_PERMISSION_CODES = Object.freeze({
  [LEGAL_CAPABILITIES.VIEW_CASE]: ['investment.legal.cases.view'],
  [LEGAL_CAPABILITIES.CREATE_CASE]: ['investment.legal.cases.create'],
  [LEGAL_CAPABILITIES.EDIT_CASE]: ['investment.legal.cases.update'],
  [LEGAL_CAPABILITIES.ACTIVATE_CASE]: ['investment.legal.cases.update'],
  [LEGAL_CAPABILITIES.MANAGE_DETAIL]: ['investment.legal.cases.update'],
  [LEGAL_CAPABILITIES.ADD_COUNSEL_CONTENT]: ['investment.legal.cases.review'],
  [LEGAL_CAPABILITIES.UPLOAD_ATTACHMENT]: [
    'investment.legal.cases.update',
    'investment.legal.cases.review'
  ],
  [LEGAL_CAPABILITIES.DELETE_ATTACHMENT]: [
    'investment.legal.cases.delete',
    'investment.legal.cases.review'
  ],
  [LEGAL_CAPABILITIES.MANAGE_ALERT]: ['investment.legal.alerts.update'],
  [LEGAL_CAPABILITIES.ARCHIVE_CASE]: ['investment.legal.cases.delete'],
  [LEGAL_CAPABILITIES.VIEW_STATISTICS]: ['investment.legal.statistics.view'],
  [LEGAL_CAPABILITIES.IMPORT_EXPORT]: ['investment.legal.cases.import'],
  [LEGAL_CAPABILITIES.EXPORT_MANAGEMENT]: ['investment.legal.cases.export'],
  [LEGAL_CAPABILITIES.ADMIN]: ['investment.legal.admin.view']
})

const ALL_CAPABILITIES = Object.freeze(Object.values(LEGAL_CAPABILITIES))

function permissionCodes(permissions = []) {
  return new Set(permissions.map((item) => typeof item === 'string' ? item : item?.code).filter(Boolean))
}

export function legalCapabilities(permissions = [], isSuperuser = false) {
  if (isSuperuser) return new Set(ALL_CAPABILITIES)
  const codes = permissionCodes(permissions)
  return new Set(Object.entries(CAPABILITY_PERMISSION_CODES)
    .filter(([, requiredCodes]) => requiredCodes.some((code) => codes.has(code)))
    .map(([capability]) => capability))
}

export function hasLegalCapability(permissions, capability, isSuperuser = false) {
  return legalCapabilities(permissions, isSuperuser).has(capability)
}

export function canDeleteLegalAttachment({
  permissions = [],
  isSuperuser = false,
  currentUserId,
  archivedAt
}, attachment) {
  if (archivedAt) return false
  const capabilities = legalCapabilities(permissions, isSuperuser)
  if (capabilities.has(LEGAL_CAPABILITIES.MANAGE_DETAIL)) return true
  return capabilities.has(LEGAL_CAPABILITIES.DELETE_ATTACHMENT)
    && Number(attachment?.uploaded_by) === Number(currentUserId)
}
