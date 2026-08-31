import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import OperationView from './index.vue'

vi.mock('@/api/operation', () => ({
  getFinancial: vi.fn().mockResolvedValue({
    existing_scale: 1300000,
    total_realized_scale: 1590000,
    total_gross_income: 110000,
    capital_occupation_days: 99,
    available_years: [2026, 2025],
    scenic_ids: ['quancheng-ouleb', 'api-only-scenic'],
    ledger_profit: [
      {
        scenic_id: 'quancheng-ouleb', business_type: 'ticket', year: 2026, month: 1,
        period_key: '2026-01', period: '2026年1月', existing_scale: 100000,
        realized_amount: 150000, service_fee: 20000,
        occupation_weight: 200000, occupation_amount: 10000
      },
      {
        scenic_id: 'api-only-scenic', business_type: 'hotel', year: 2026, month: 1,
        period_key: '2026-01', period: '2026年1月', existing_scale: 300000,
        realized_amount: 320000, service_fee: 30000,
        occupation_weight: 1200000, occupation_amount: 30000
      },
      {
        scenic_id: 'quancheng-ouleb', business_type: 'ticket', year: 2025, month: 12,
        period_key: '2025-12', period: '2025年12月', existing_scale: 900000,
        realized_amount: 1120000, service_fee: 60000,
        occupation_weight: 2700000, occupation_amount: 90000
      }
    ]
  })
}))

describe('经营数据中心', () => {
  let wrapper

  afterEach(() => wrapper?.unmount())

  async function mountView() {
    wrapper = shallowMount(OperationView, {
      global: {
        stubs: {
          BaseChart: { name: 'BaseChart', props: ['option'], template: '<div class="chart-stub" />' },
          ElRow: { template: '<div><slot /></div>' },
          ElCol: { template: '<div><slot /></div>' },
          ElCard: { template: '<section><slot name="header" /><slot /></section>' },
          ElSelect: true,
          ElOption: true,
          ElTable: true,
          ElTableColumn: true
        }
      }
    })
    await flushPromises()
    return wrapper
  }

  it('保留四张 KPI 和两张原类型图表，并只把图表输入转换为万元', async () => {
    await mountView()

    expect(wrapper.findAll('.kpi-card')).toHaveLength(4)
    const charts = wrapper.findAllComponents({ name: 'BaseChart' })
    expect(charts).toHaveLength(2)

    const barOption = charts[0].props('option')
    expect(barOption.series.every((series) => series.type === 'bar')).toBe(true)
    expect(barOption.series.flatMap((series) => series.data)).toEqual(expect.arrayContaining([2, 3]))
    expect(barOption.yAxis.name).toBe('服务费（万元）')
    expect(barOption.tooltip.valueFormatter(2)).toBe('¥2.00 万元')

    const pieOption = charts[1].props('option')
    expect(pieOption.series[0].type).toBe('pie')
    expect(pieOption.series[0].data.map((item) => item.value)).toEqual([3, 2])
    expect(pieOption.tooltip.formatter({ name: '景区', value: 3, percent: 60 }))
      .toContain('¥3.00 万元')
  })

  it('在页面尾部展示配置景区、未知景区和按权重计算的显式合计行', async () => {
    await mountView()

    const ledger = wrapper.get('[data-testid="scenic-operation-ledger"]')
    expect(wrapper.get('.chart-row').element.compareDocumentPosition(ledger.element) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy()
    expect(ledger.text()).toContain('景区经营数据台账')
    expect(ledger.text()).toContain('合计')

    expect(wrapper.vm.scenicLedgerRows.some((row) => row.scenic_id === 'zunyi-zoo')).toBe(true)
    expect(wrapper.vm.scenicLedgerRows.some((row) => row.scenic_id === 'api-only-scenic')).toBe(true)
    expect(wrapper.vm.scenicLedgerRows.find((row) => row.scenic_id === 'quancheng-ouleb').existing_scale)
      .toBe(100000)
    const table = wrapper.getComponent({ name: 'ElTable' })
    expect(table.props('showSummary')).toBe(false)
    expect(table.props('data').at(-1)).toMatchObject({ scenic_name: '合计', is_total: true })
    expect(table.props('rowClassName')({ row: table.props('data').at(-1) })).toBe('ledger-total-row')
    expect(wrapper.vm.ledgerTotalRow.capital_occupation_days).toBe(35)
    expect(wrapper.vm.ledgerTotalRow.capital_occupation_days).not.toBe(30)
    expect(ledger.text()).toContain('10.00 万元')
  })

  it('让年份和景区筛选同步更新卡片、图表与台账', async () => {
    await mountView()

    expect(wrapper.text()).toContain('¥40.00 万元')
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0].vm.$emit('update:modelValue', 2025)
    await flushPromises()

    expect(wrapper.text()).toContain('¥90.00 万元')
    expect(wrapper.text()).not.toContain('¥40.00 万元')
    expect(wrapper.vm.scenicLedgerRows.find((row) => row.scenic_id === 'quancheng-ouleb').existing_scale)
      .toBe(900000)
    expect(wrapper.findAllComponents({ name: 'BaseChart' })[0].props('option').series[0].data).toEqual([6])

    selects[1].vm.$emit('update:modelValue', ['api-only-scenic'])
    await flushPromises()
    expect(wrapper.vm.scenicLedgerRows.map((row) => row.scenic_id)).toEqual(['api-only-scenic'])
    expect(wrapper.text()).toContain('¥0.00 万元')
    expect(wrapper.vm.ledgerTotalRow.capital_occupation_days).toBeNull()
    expect(wrapper.text()).toContain('—')
    expect(wrapper.findAllComponents({ name: 'BaseChart' })[0].props('option').series).toEqual([])
  })
})
