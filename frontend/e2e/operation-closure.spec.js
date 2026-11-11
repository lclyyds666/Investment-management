import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from '@playwright/test'

let vite
const summary = { settlement_amount: 120000, writeoff_amount: 90000, order_count: 30, capital_occupation: 40000, capital_occupation_days: 12 }
const analysis = { summary, comparisons: {}, trends: [{ day: '2024-02-01', ...summary }], rankings: [{ dimension: 'platform', value: '携程', summary, settlement_share: 100 }], contributions: [{ dimension: 'platform', value: '携程', settlement_change: 10000, contribution_rate: 100 }], anomalies: [], quality_issues: [{ business_type: 'ticket', row_id: 1, code: 'missing_date' }] }

test.beforeAll(async () => {
  vite = spawn(process.execPath, [resolve('node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '4175', '--strictPort'], { stdio: 'ignore', windowsHide: true })
  for (let i = 0; i < 150; i++) {
    try { if ((await fetch('http://127.0.0.1:4175/')).ok) return } catch { /* starting */ }
    await new Promise(r => setTimeout(r, 100))
  }
  throw new Error('Vite did not start')
})
test.afterAll(async () => {
  if (!vite || vite.exitCode !== null) return
  await new Promise(resolveStop => { vite.once('exit', resolveStop); vite.kill(); setTimeout(resolveStop, 2000).unref() })
})

async function setup(page, { permissions = ['supply.operation.view', 'supply.operation.create', 'supply.operation.export', 'supply.finance.view'], handlers = {} } = {}) {
  const requests = [], errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.addInitScript(() => localStorage.setItem('token', 'local-browser-fixture'))
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.replace('/api/v1', '')
    requests.push({ path, query: Object.fromEntries(url.searchParams), body: req.postData() ? req.postDataJSON() : null })
    if (handlers[path]) return handlers[path](route, requests.at(-1))
    let data = []
    if (path === '/auth/me') data = { id: 7, username: 'browser-fixture', role: 'viewer', is_superuser: false }
    if (path === '/portal/applications') data = [{ code: 'supplymanagement', accessible: true, status: 'online', route: '/supplymanagement' }]
    if (path === '/portal/me/permissions') data = { is_superuser: false, resources: ['supply.dashboard', 'supply.operation', 'supply.finance', 'supply.scenic.analytics'], permissions: permissions.map(code => ({ code })), company_roles: { supplymanagement: 'viewer' } }
    if (path === '/operation/analysis') data = analysis
    if (path === '/operation/financial') data = { available_years: [2024, 2025], ledger_profit: [], scenic_ids: ['zunyi-zoo'] }
    if (path === '/funds/summary') data = {}
    if (path === '/funds') data = { items: [], total: 0 }
    if (path === '/funds/alerts/today') data = { items: [] }
    return route.fulfill({ json: { code: 0, data } })
  })
  return { requests, errors }
}

test('analysis renders charts and quality; independent filters and observed platforms', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/supplymanagement/operation/analysis')
  await expect(page.getByRole('heading', { name: '分析预测' })).toBeVisible()
  await expect(page.getByText('结算排名与占比', { exact: true })).toBeVisible()
  await expect(page.getByText('missing_date', { exact: false })).toBeVisible()
  await expect(page.locator('canvas').first()).toBeVisible()
  await page.locator('.filters .el-select').last().click()
  await page.getByRole('option', { name: '携程', exact: true }).click()
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: '数据 AI 预测' }).click()
  await expect(page.locator('.filters .el-select').last()).not.toContainText('携程')
  await page.getByRole('combobox', { name: '平台', exact: true }).fill('unknown-platform')
  await expect(page.getByRole('option', { name: 'unknown-platform' })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: '经营情况分析' }).click()
  await expect(page.locator('.filters .el-select').last()).toContainText('携程')
  await page.screenshot({ path: '../.playwright-results/operation-analysis-desktop.png', fullPage: true })
  expect(state.errors).toEqual([])
})

test('leap month, custom dates, factors, failure recovery, three metrics and export', async ({ page }) => {
  let attempts = 0
  const state = await setup(page, { handlers: {
    '/operation/forecast': (route, request) => {
      if (++attempts === 1) return route.fulfill({ status: 503, json: { detail: 'fixture temporary failure' } })
      const lines = ['settlement_amount', 'writeoff_amount', 'order_count'].map((metric, i) => ({ metric, scenic_id: 'zunyi-zoo', business_type: 'ticket', platform: '携程', forecast: i === 2 ? null : 120000, interval_low: 100000, interval_high: 140000, confidence: 'low', reasons: ['历史不足'], components: {}, factor_contributions: [{ factor_index: 0, name: '活动贡献', contribution: 12000 }] }))
      return route.fulfill({ json: { code: 0, data: { ...request.body, lines, insights: { engine: 'rule', summary: 'fixture forecast', recommendations: [] }, quality_issues: [] } } })
    },
    '/operation/forecast/export': route => route.fulfill({ contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', body: 'fixture export bytes' })
  } })
  await page.goto('/supplymanagement/operation/analysis')
  await page.getByRole('tab', { name: '数据 AI 预测' }).click()
  await page.getByText('按月', { exact: true }).click()
  const month = page.getByPlaceholder('选择预测月份')
  await month.fill('2024-02'); await month.press('Enter')
  await page.getByTestId('add-factor').click()
  await page.getByTestId('factor-name-0').fill('春节活动')
  await page.getByRole('button', { name: '生成预测', exact: true }).click()
  await expect(page.locator('.operation-analysis > .el-alert')).toContainText('fixture temporary failure')
  await page.getByRole('button', { name: '生成预测', exact: true }).click()
  await expect(page.getByText('fixture forecast', { exact: true })).toBeVisible()
  const submitted = state.requests.filter(r => r.path === '/operation/forecast').at(-1).body
  expect(submitted).toMatchObject({ start_date: '2024-02-01', end_date: '2024-02-29', factors: [{ name: '春节活动' }] })
  await expect(page.locator('.forecast-metrics .el-card')).toHaveCount(3)
  await expect(page.locator('.forecast-metrics')).toContainText('数据不足')
  await expect(page.getByText('活动贡献：', { exact: false }).first()).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出预测 Excel' }).click()
  expect((await download).suggestedFilename()).toBe('经营数据预测.xlsx')
  await page.screenshot({ path: '../.playwright-results/operation-forecast-desktop.png', fullPage: true })
  await page.getByText('自定义', { exact: true }).click()
  await page.getByPlaceholder('开始日期').fill('2024-03-01')
  await page.getByPlaceholder('结束日期').fill('2024-03-05')
  await page.getByPlaceholder('结束日期').press('Enter')
  await page.getByRole('button', { name: '生成预测', exact: true }).click()
  await expect.poll(() => state.requests.filter(r => r.path === '/operation/forecast').at(-1)?.body.end_date).toBe('2024-03-05')
  expect(state.errors).toEqual([])
})

test('view only hides factor/import/generate and independently gates export', async ({ page }) => {
  const state = await setup(page, { permissions: ['supply.operation.view', 'supply.operation.export'] })
  await page.goto('/supplymanagement/operation/analysis')
  await page.getByRole('tab', { name: '数据 AI 预测' }).click()
  await expect(page.getByTestId('add-factor')).toHaveCount(0)
  await expect(page.getByTestId('factor-file')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '生成预测', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '导出预测 Excel' })).toBeVisible()
  expect(state.errors).toEqual([])
})

test('data center retains year and trace uses canonical period with redaction', async ({ page }) => {
  const state = await setup(page, { handlers: {
    '/operation/trace-periods': route => route.fulfill({ json: { code: 0, data: [{ source_kind: 'hotel', period_key: '2024-02-original' }] } }),
    '/operation/trace': route => route.fulfill({ json: { code: 0, data: { scenic_id: 'zunyi-zoo', source_kind: 'hotel', period_key: '2024-02-original', restricted_count: 2, ledger_rows: [{ id: 12, platform: '携程', confirmed: true }] } } })
  } })
  await page.goto('/supplymanagement/operation')
  await expect(page.getByRole('heading', { name: '数据中心' })).toBeVisible()
  await page.locator('.chart-filters .el-select').first().click()
  await page.getByRole('option', { name: '2024年' }).click()
  await page.getByRole('button', { name: '查看业务链路', exact: true }).first().click()
  const drawer = page.locator('.el-drawer')
  await drawer.locator('.el-select').click()
  await page.getByRole('option', { name: '酒店 · 2024-02-original' }).click()
  await expect(page.getByTestId('restricted-count')).toContainText('2 个关联节点')
  expect(state.requests.find(r => r.path === '/operation/trace').query).toMatchObject({ source_kind: 'hotel', period_key: '2024-02-original' })
  await page.screenshot({ path: '../.playwright-results/operation-trace-desktop.png', fullPage: true })
  await drawer.getByRole('button', { name: '#12 · 携程 · 已确认' }).click()
  await expect(page).toHaveURL(/source_kind=hotel.*period_key=2024-02-original/)
  expect(state.errors).toEqual([])
})

test('work items refresh badge by polling and consume fund navigation query', async ({ page }) => {
  let rows = [{ item_type: 'fund_unallocated', scenic_id: 'zunyi-zoo', amount: 120, status: '待核销', target_path: '/supplymanagement/finance/fund', target_query: { fund_id: '81', unallocated_only: 'true' } }]
  await page.clock.install()
  const state = await setup(page, { handlers: { '/work-items': route => route.fulfill({ json: { code: 0, data: rows } }) } })
  await page.goto('/supplymanagement/work-items')
  await expect(page.getByRole('button', { name: '去处理' })).toHaveCount(1)
  rows = [...rows, { ...rows[0], amount: 240 }]
  await page.clock.fastForward(30001)
  await expect(page.getByRole('button', { name: '去处理' })).toHaveCount(2)
  await page.clock.resume()
  await page.getByRole('button', { name: '去处理' }).first().click()
  await expect(page).toHaveURL(/fund_id=81.*unallocated_only=true/)
  await expect.poll(() => state.requests.find(r => r.path === '/funds')?.query.fund_id).toBe('81')
  await expect(page.getByRole('button', { name: '新增流水' })).toHaveCount(0)
  expect(state.errors).toEqual([])
})

test('daily fund alert acknowledges shown stage and navigates maturity filter', async ({ page }) => {
  const state = await setup(page, { handlers: {
    '/funds/alerts/today': route => route.fulfill({ json: { code: 0, data: { items: [{ id: 91, stage: 'overdue', category: 'bank_credit', counterparty: '验收银行', amount: 10000, maturity_date: '2024-02-01', days_remaining: -2 }] } } }),
    '/funds/alerts/today/acknowledge': route => route.fulfill({ json: { code: 0, data: { acknowledged: 1 } } })
  } })
  await page.goto('/supplymanagement/operation/analysis')
  await expect(page.getByRole('heading', { name: '资金到期提醒' })).toBeVisible()
  await expect.poll(() => state.requests.find(r => r.path.endsWith('/acknowledge'))?.body).toEqual({ items: [{ fund_id: 91, stage: 'overdue' }] })
  await page.getByRole('button', { name: '查看逾期事项' }).click()
  await expect(page).toHaveURL(/maturity_status=overdue/)
  await expect.poll(() => state.requests.find(r => r.path === '/funds')?.query.maturity_status).toBe('overdue')
  expect(state.errors).toEqual([])
})

test('strategic map real click distinguishes ticket hotel and refreshes completion', async ({ page }) => {
  let completion = 70
  await page.clock.install()
  const state = await setup(page, { handlers: {
    '/operation/financial': route => route.fulfill({ json: { code: 0, data: { ledger_profit: [], scenic_completion: [
      { scenic_id: 'quanzhou-ouleb', business_type: 'ticket', completion_rate: completion },
      { scenic_id: 'quanzhou-ouleb', business_type: 'hotel', completion_rate: null },
      { scenic_id: 'fuzhou-ouleb', business_type: 'ticket', completion_rate: 80 }
    ] } } })
  } })
  await page.goto('/supplymanagement/dashboard')
  await page.clock.resume()
  await expect(page.locator('.map-el canvas').first()).toBeVisible()
  // Convert a real geographic point to canvas pixels; interaction remains a real mouse click.
  const point = await page.evaluate(async () => {
    const componentSource = await (await fetch('/src/components/screen/ScreenMap.vue')).text()
    const moduleUrl = componentSource.match(/import \* as echarts from ["']([^"']+)["']/)[1]
    const echarts = await import(moduleUrl)
    const element = document.querySelector('.map-el')
    const chart = echarts.getInstanceByDom(element)
    const position = chart.convertToPixel({ geoIndex: 0 }, [119.30, 26.08])
    const rect = element.getBoundingClientRect()
    return { x: rect.left + position[0], y: rect.top + position[1] }
  })
  await page.mouse.click(point.x, point.y)
  const rows = page.locator('[data-test="completion-row"]')
  await expect(rows).toHaveCount(3)
  await expect(rows.filter({ hasText: '酒店' })).toContainText('—')
  await expect(rows.filter({ hasText: '泉州欧乐堡' }).filter({ hasText: '门票' })).toContainText('70.00%')
  completion = 92
  await page.clock.fastForward(20001)
  await expect(rows.filter({ hasText: '泉州欧乐堡' }).filter({ hasText: '门票' })).toContainText('92.00%')
  await page.screenshot({ path: '../.playwright-results/operation-strategic-desktop.png', fullPage: true })
  expect(state.errors).toEqual([])
})
