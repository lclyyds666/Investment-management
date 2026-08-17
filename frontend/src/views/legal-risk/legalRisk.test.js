import { describe, expect, it } from 'vitest'
import {
  ALERT_TYPE_OPTIONS, CASE_STATUS_OPTIONS, JUDGMENT_TYPE_OPTIONS
} from '@/constants/legalRisk'
import { CASE_DETAIL_TABS } from './caseDetailTabs'

describe('legal risk fixed business dictionaries', () => {
  it('uses exactly the six approved formal case statuses', () => {
    expect(CASE_STATUS_OPTIONS.map((item) => item.label)).toEqual([
      '审查立案', '审理中', '已判决', '执行中', '终本', '已结案'
    ])
  })

  it('includes settlement in the five judgment/result types', () => {
    expect(JUDGMENT_TYPE_OPTIONS.map((item) => item.label)).toEqual([
      '一审', '二审', '再审', '调解', '和解'
    ])
  })

  it('defines the five deadline alert rules and eight detail tabs', () => {
    expect(ALERT_TYPE_OPTIONS).toHaveLength(5)
    expect(CASE_DETAIL_TABS.map((item) => item.label)).toEqual([
      '基本信息', '裁判结果', '查扣冻资产', '清回止损',
      '进展风险', '期限事件', '案件材料', '操作记录'
    ])
  })
})
