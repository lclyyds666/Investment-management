const dateKey = (value = new Date()) => {
  if (typeof value === 'string') return value.slice(0, 10)
  const pad = (part) => String(part).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

const isEffective = (assignment, today) => {
  if (assignment?.status && assignment.status !== 'active') return false
  if (assignment?.valid_from && dateKey(assignment.valid_from) > today) return false
  if (assignment?.valid_until && dateKey(assignment.valid_until) < today) return false
  return true
}

const assignmentLabel = (assignment) => {
  const organization = assignment?.organization_name?.trim()
  const position = assignment?.position_name?.trim()
  return organization && position ? `${organization} / ${position}` : ''
}

export function currentAssignmentLabel({
  portalAssignments = [],
  portalLoaded = false,
  userAssignments = [],
  isSuperuser = false,
  superuserLabel = '信息维护',
  today = dateKey()
} = {}) {
  if (isSuperuser) return superuserLabel || '信息维护'

  const source = portalLoaded ? portalAssignments : userAssignments
  const normalizedToday = dateKey(today)
  const labels = [...new Set(
    source
      .filter((item) => isEffective(item, normalizedToday))
      .map(assignmentLabel)
      .filter(Boolean)
  )]

  return labels.length ? labels.join('、') : '未配置岗位'
}
