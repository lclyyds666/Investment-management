import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import Analysis from './analysis.vue'
import {
  getOperationAnalysis,
  createOperationForecast,
  exportOperationForecast,
} from '@/api/operation'
const permission = vi.hoisted(() => ({ create: true, export: true }))
vi.mock('@/store/portal', () => ({
  usePortalStore: () => ({
    hasPermission: (key) => permission[key.split('.').at(-1)],
  }),
}))
vi.mock('@/api/operation', () => ({
  getOperationAnalysis: vi.fn(),
  createOperationForecast: vi.fn(),
  exportOperationForecast: vi.fn(),
}))
const summary = {
  settlement_amount: 20000,
  writeoff_amount: 10000,
  order_count: 20,
  capital_occupation: 10000,
}
const sample = () => ({
  summary,
  trends: [{ day: '2026-01-01', ...summary }],
  comparisons: {
    settlement: { mom_rate: 10, yoy_rate: null },
    writeoff: {},
    orders: {},
    capital_occupation: {},
  },
  rankings: [
    { dimension: 'platform', value: '携程', summary, settlement_share: 100 },
  ],
  contributions: [],
  anomalies: [],
  quality_issues: [],
})
describe('operation analysis and forecast workspace', () => {
  let wrapper
  beforeEach(() => {
    vi.clearAllMocks()
    permission.create = true
    permission.export = true
    getOperationAnalysis.mockResolvedValue(sample())
    createOperationForecast.mockResolvedValue({
      start_date: '2026-02-01',
      end_date: '2026-02-02',
      insights: { engine: 'rules', summary: '规则说明', recommendations: [] },
      quality_issues: [],
      lines: [
        {
          metric: 'settlement_amount',
          forecast: '30000',
          interval_low: '20000',
          interval_high: '40000',
          confidence: 'low',
          reasons: [],
          components: {},
        },
        {
          metric: 'order_count',
          forecast: null,
          interval_low: null,
          interval_high: null,
          confidence: 'low',
          reasons: ['数据不足'],
          components: {},
        },
      ],
    })
  })
  afterEach(() => wrapper?.unmount())
  it('preserves independent tab filters, selects full months and accumulates only observed platforms', async () => {
    await mount()
    wrapper.vm.dateRange = ['2026-01-01', '2026-01-07']
    wrapper.vm.scenicIds = ['analysis-scenic']
    wrapper.vm.activeTab = 'forecast'
    wrapper.vm.scenicIds = ['forecast-scenic']
    wrapper.vm.forecastPeriodMode = 'month'
    wrapper.vm.selectForecastMonth('2028-02')
    expect(wrapper.vm.dateRange).toEqual(['2028-02-01', '2028-02-29'])
    wrapper.vm.activeTab = 'analysis'
    expect(wrapper.vm.dateRange).toEqual(['2026-01-01', '2026-01-07'])
    expect(wrapper.vm.scenicIds).toEqual(['analysis-scenic'])
    getOperationAnalysis.mockResolvedValueOnce({ ...sample(), rankings: [] })
    await wrapper.vm.loadAnalysis()
    expect(wrapper.vm.platformOptions).toEqual(['携程'])
    wrapper.vm.activeTab = 'forecast'
    expect(wrapper.vm.scenicIds).toEqual(['forecast-scenic'])
    expect(wrapper.vm.dateRange).toEqual(['2028-02-01', '2028-02-29'])
  })
  async function mount() {
    wrapper = shallowMount(Analysis, {
      global: {
        directives: { loading: () => {} },
        stubs: {
          ElCard: {
            template: '<section><slot name="header"/><slot/></section>',
          },
          ElTabs: true,
          ElTabPane: true,
          ElButton: {
            template: `<button @click="$emit('click')"><slot/></button>`,
          },
          BaseChart: {
            name: 'BaseChart',
            props: ['option'],
            template: '<div />',
          },
        },
      },
    })
    await flushPromises()
  }
  it('queries real repeated filter keys and converts only chart/card display to wan', async () => {
    await mount()
    expect(wrapper.text()).toContain('2.00 万元')
    expect(wrapper.text()).toContain('同比 —')
    expect(wrapper.vm.analysisChart.series[0].data).toEqual([2])
    expect(wrapper.vm.analysisChart.series[2].data).toEqual([20])
    wrapper.vm.scenicIds = ['s1']
    wrapper.vm.businessTypes = ['hotel']
    wrapper.vm.platforms = ['携程']
    await wrapper.vm.loadAnalysis()
    expect(getOperationAnalysis).toHaveBeenLastCalledWith(
      expect.objectContaining({
        scenic_id: ['s1'],
        business_type: ['hotel'],
        platform: ['携程'],
      }),
    )
    expect(wrapper.vm.analysis.summary.settlement_amount).toBe(20000)
  })
  it('uses horizon totals and explicit uncertainty, retains factors and three KPI metrics', async () => {
    await mount()
    wrapper.vm.activeTab = 'forecast'
    wrapper.vm.dateRange = ['2026-02-01', '2026-02-02']
    wrapper.vm.factors = [{ name: '活动', impact_rate: 0.1 }]
    await wrapper.vm.generateForecast()
    expect(createOperationForecast).toHaveBeenCalledWith(
      expect.objectContaining({
        start_date: '2026-02-01',
        end_date: '2026-02-02',
        factors: [{ name: '活动', impact_rate: 0.1 }],
      }),
    )
    expect(wrapper.vm.forecastMetrics).toHaveLength(3)
    expect(wrapper.vm.forecastMetrics[0]).toMatchObject({
      value: 30000,
      low: 20000,
      high: 40000,
    })
    expect(wrapper.vm.forecastMetrics[2]).toMatchObject({
      value: null,
      missing: 1,
    })
    expect(wrapper.vm.forecastChart.series[1].data.at(-1)).toBe(3)
    expect(wrapper.vm.forecastChart.series[2].data).toEqual([[4, 2, 4]])
    expect(getOperationAnalysis).toHaveBeenLastCalledWith(
      expect.objectContaining({
        start_date: '2026-01-24',
        end_date: '2026-01-31',
      }),
    )
  })
  it('guards generation and export separately, including direct handlers', async () => {
    permission.create = false
    permission.export = false
    await mount()
    wrapper.vm.activeTab = 'forecast'
    await flushPromises()
    expect(wrapper.findAll('button').map((b) => b.text())).not.toContain(
      '生成预测',
    )
    expect(wrapper.findAll('button').map((b) => b.text())).not.toContain(
      '导出预测 Excel',
    )
    await wrapper.vm.generateForecast()
    await wrapper.vm.exportForecast()
    expect(createOperationForecast).not.toHaveBeenCalled()
    expect(exportOperationForecast).not.toHaveBeenCalled()
  })
  it('rejects invalid periods and recovers after API errors', async () => {
    await mount()
    wrapper.vm.activeTab = 'forecast'
    wrapper.vm.dateRange = ['2026-01-01', '2026-05-01']
    await wrapper.vm.generateForecast()
    expect(wrapper.vm.error).toContain('90')
    expect(createOperationForecast).not.toHaveBeenCalled()
    getOperationAnalysis.mockRejectedValueOnce(new Error('服务暂不可用'))
    await wrapper.vm.loadAnalysis()
    expect(wrapper.vm.error).toBe('服务暂不可用')
    expect(wrapper.vm.loading).toBe(false)
    await wrapper.vm.loadAnalysis()
    expect(wrapper.vm.error).toBe('')
  })
  it('exports the displayed forecast snapshot and releases the download URL', async () => {
    await mount()
    wrapper.vm.activeTab = 'forecast'
    wrapper.vm.dateRange = ['2026-02-01', '2026-02-02']
    await wrapper.vm.generateForecast()
    wrapper.vm.dateRange = ['2026-03-01', '2026-03-02']
    exportOperationForecast.mockResolvedValue(new Blob(['xlsx']))
    const create = vi.fn(() => 'blob:test'),
      revoke = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: create,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revoke,
    })
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    await wrapper.vm.exportForecast()
    expect(exportOperationForecast).toHaveBeenCalledWith(
      expect.objectContaining({
        start_date: '2026-02-01',
        end_date: '2026-02-02',
      }),
    )
    expect(click).toHaveBeenCalled()
    expect(revoke).toHaveBeenCalledWith('blob:test')
    click.mockRestore()
  })
})
