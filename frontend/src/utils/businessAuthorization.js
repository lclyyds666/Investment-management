export const WORKFLOW_ROLE_POSITIONS = Object.freeze({
  business_handler: 'supply.business_handler',
  business_reviewer: 'supply.business_reviewer',
  finance_handler: 'supply.finance_handler',
  scm_director: 'supply.company_leader',
  invest_director: 'governance.supply_leader',
  risk_auditor: 'investment.duty.supply_risk_review',
  finance_reviewer: 'investment.duty.supply_finance_review',
  legal_counsel: 'external.legal_counsel'
})

export function canUsePermission(portalStore, permissionCode) {
  return portalStore.isSuperuser || portalStore.hasPermission(permissionCode)
}

export function canActOnWorkflow(portalStore, row, permissionCode) {
  if (row?.status !== 'pending') return false
  if (portalStore.isSuperuser) return true
  const positionCode = WORKFLOW_ROLE_POSITIONS[row?.current_role]
  return Boolean(positionCode)
    && portalStore.hasPermission(permissionCode)
    && portalStore.hasPosition(positionCode)
}
