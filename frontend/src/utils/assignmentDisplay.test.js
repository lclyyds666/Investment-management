import { describe, expect, it } from 'vitest'
import { currentAssignmentLabel } from './assignmentDisplay'

const assignment = (overrides = {}) => ({
  organization_name: '法务风控部',
  position_name: '部门副总监',
  status: 'active',
  valid_from: '2026-08-01',
  valid_until: '2036-08-01',
  ...overrides
})

describe('currentAssignmentLabel', () => {
  it('formats the loaded portal assignment snapshot', () => {
    expect(currentAssignmentLabel({
      portalLoaded: true,
      portalAssignments: [assignment({ status: undefined })],
      today: '2026-08-17'
    })).toBe('法务风控部 / 部门副总监')
  })

  it('shows every unique effective assignment', () => {
    expect(currentAssignmentLabel({
      portalLoaded: true,
      portalAssignments: [
        assignment({ status: undefined }),
        assignment({ organization_name: '资产财务部', position_name: '财务复核', status: undefined }),
        assignment({ status: undefined })
      ],
      today: '2026-08-17'
    })).toBe('法务风控部 / 部门副总监、资产财务部 / 财务复核')
  })

  it('filters inactive, future and expired fallback summaries', () => {
    expect(currentAssignmentLabel({
      userAssignments: [
        assignment(),
        assignment({ position_name: '停用岗位', status: 'inactive' }),
        assignment({ position_name: '未来岗位', valid_from: '2026-09-01' }),
        assignment({ position_name: '过期岗位', valid_until: '2026-08-16' })
      ],
      today: '2026-08-17'
    })).toBe('法务风控部 / 部门副总监')
  })

  it('does not reuse fallback summaries after an empty portal snapshot loads', () => {
    expect(currentAssignmentLabel({
      portalLoaded: true,
      portalAssignments: [],
      userAssignments: [assignment()],
      today: '2026-08-17'
    })).toBe('未配置岗位')
  })

  it('keeps the information-maintainer label for superuser', () => {
    expect(currentAssignmentLabel({
      isSuperuser: true,
      superuserLabel: '信息维护',
      portalLoaded: true,
      portalAssignments: []
    })).toBe('信息维护')
  })
})
