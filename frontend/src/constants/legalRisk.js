export const CASE_STATUS_OPTIONS = Object.freeze([
  { value: 'review_filing', label: '审查立案' },
  { value: 'in_trial', label: '审理中' },
  { value: 'judged', label: '已判决' },
  { value: 'enforcement', label: '执行中' },
  { value: 'terminal', label: '终本' },
  { value: 'closed', label: '已结案' }
])

export const JUDGMENT_TYPE_OPTIONS = Object.freeze([
  { value: 'first_instance', label: '一审' },
  { value: 'second_instance', label: '二审' },
  { value: 'retrial', label: '再审' },
  { value: 'mediation', label: '调解' },
  { value: 'settlement', label: '和解' }
])

export const PARTY_TYPE_OPTIONS = Object.freeze([
  { value: 'plaintiff', label: '原告/申请人' },
  { value: 'defendant', label: '被告/被申请人' },
  { value: 'third_party', label: '第三人' }
])

export const RECOVERY_TYPE_OPTIONS = Object.freeze([
  { value: 'recovery', label: '清收回款' },
  { value: 'avoided_loss', label: '止损金额' }
])

export const PROGRESS_TYPE_OPTIONS = Object.freeze([
  { value: 'progress', label: '案件进展' },
  { value: 'legal_opinion', label: '法律意见' }
])

export const DEADLINE_TYPE_OPTIONS = Object.freeze([
  { value: 'hearing', label: '开庭' },
  { value: 'payment_material', label: '缴费/材料提交' },
  { value: 'custom', label: '其他期限' }
])

export const ALERT_TYPE_OPTIONS = Object.freeze([
  { value: 'asset_expiry', label: '查扣冻资产到期' },
  { value: 'enforcement_application', label: '申请执行期限' },
  { value: 'hearing', label: '开庭期限' },
  { value: 'payment_material', label: '缴费/材料期限' },
  { value: 'terminal_monitoring', label: '终本案件跟踪' }
])

export const ALERT_STATUS_OPTIONS = Object.freeze([
  { value: 'pending', label: '待处理' },
  { value: 'processing', label: '处理中' },
  { value: 'completed', label: '已完成' },
  { value: 'closed', label: '已关闭' }
])

const lookup = (items, value) => items.find((item) => item.value === value)?.label || value || '-'

export const caseStatusLabel = (value) => lookup(CASE_STATUS_OPTIONS, value)
export const judgmentTypeLabel = (value) => lookup(JUDGMENT_TYPE_OPTIONS, value)
export const partyTypeLabel = (value) => lookup(PARTY_TYPE_OPTIONS, value)
export const recoveryTypeLabel = (value) => lookup(RECOVERY_TYPE_OPTIONS, value)
export const progressTypeLabel = (value) => lookup(PROGRESS_TYPE_OPTIONS, value)
export const deadlineTypeLabel = (value) => lookup(DEADLINE_TYPE_OPTIONS, value)
export const alertTypeLabel = (value) => lookup(ALERT_TYPE_OPTIONS, value)
export const alertStatusLabel = (value) => lookup(ALERT_STATUS_OPTIONS, value)

export const money = (value) => Number(value || 0).toLocaleString('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})

export const cleanParams = (params = {}) => Object.fromEntries(
  Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined)
)
