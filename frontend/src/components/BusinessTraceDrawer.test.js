import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BusinessTraceDrawer from './BusinessTraceDrawer.vue'

const stubs = {
  ElDrawer: { template: '<aside><slot /></aside>' },
  ElSelect: { template: '<div><slot /></div>' },
  ElOption: true
}
const trace = {
  scenic_id: 'a', source_kind: 'hotel', period_key: 'source.xlsx', restricted_count: 2,
  ledger_rows: [{ id: 1, platform: '携程', confirmed: true }],
  invoices: [{ id: 2, direction: 'output', status: 'pending', amount: '50.00' }],
  allocations: [{ id: 3, invoice_id: 2, fund_transaction_id: 4, amount: '20.00' }],
  funds: [{ id: 4, direction: 'increase', amount: '20.00' }],
  execution_tasks: [{ id: 5, status: 'partial', planned_amount: '50.00', executed_amount: '20.00' }],
  approvals: [{ id: 6, form_type: 'invoice', status: 'approved' }],
  contracts: [{ id: 7, contract_no: 'C-7', status: 'approved' }]
}
function render(props = {}) {
  return mount(BusinessTraceDrawer, { props: { modelValue: true, trace,
    periods: [{ scenic_id: 'a', source_kind: 'hotel', period_key: 'source.xlsx' }], ...props }, global: { stubs } })
}
describe('BusinessTraceDrawer', () => {
  it('renders linked stages and transparent restricted count', () => {
    const wrapper = render()
    expect(wrapper.findAll('section')).toHaveLength(7)
    expect(wrapper.get('[data-testid="restricted-count"]').text()).toContain('2 个关联节点')
    expect(wrapper.get('[data-testid="trace-execution_tasks"]').text()).toContain('20.00 / 50.00 元')
  })
  it('opens actual original module deep links for every permitted stage', async () => {
    const wrapper = render()
    for (const button of wrapper.findAll('.node-link')) await button.trigger('click')
    expect(wrapper.emitted('open-node').map(([target]) => target)).toEqual([
      { path: '/supplymanagement/cultural-tourism/a', query: { source_kind: 'hotel', period_key: 'source.xlsx' } },
      { path: '/supplymanagement/finance/invoice', query: { invoice_id: '2' } },
      { path: '/supplymanagement/finance/fund', query: { fund_id: '4' } },
      { path: '/supplymanagement/finance/fund', query: { fund_id: '4' } },
      { path: '/supplymanagement/finance/fund', query: { tab: 'execution', task_id: '5' } },
      { path: '/supplymanagement/approval', query: { form_id: '6' } },
      { path: '/investment/legal-risk/contracts', query: { contract_id: '7' } }
    ])
  })
  it('has explicit selection, missing date, loading and error states', () => {
    expect(render({ trace: null }).text()).toContain('请选择期次')
    expect(render({ trace: null, periods: [] }).text()).toContain('无日期期次仅在全部年份下显示')
    expect(render({ loading: true }).text()).toContain('正在加载')
    const failed = render({ error: '加载失败' })
    expect(failed.get('[role="alert"]').text()).toBe('加载失败')
    expect(failed.findAll('.node-link')).toHaveLength(0)
  })
  it('does not fabricate links for hidden or absent nodes', () => {
    const wrapper = render({ trace: { ...trace, invoices: [], allocations: [], contracts: [] } })
    expect(wrapper.get('[data-testid="trace-invoices"]').text()).toContain('暂无可见关联记录')
    expect(wrapper.findAll('.node-link')).toHaveLength(4)
  })
})
