# Operation Profit All-Years Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the operation data center default to all years so its gross profit matches the strategic overview while preserving manual year filtering.

**Architecture:** Keep `/api/v1/operation/financial` and the shared backend aggregation unchanged. Change only the operation page's initial filter state and copy, then verify that the existing computed filtering continues to drive KPIs, charts, and ledger totals for both all-years and selected-year views.

**Tech Stack:** Vue 3 Composition API, Element Plus, Vitest, Vue Test Utils

## Global Constraints

- Default operation gross profit uses all ledger years and must match the strategic overview.
- Default production value is `739.31` 万元 from `7,393,069.92` 元.
- Selecting `2026年` must show `733.37` 万元 from `7,333,677.92` 元.
- The year selector remains available and clearing it restores all-years totals.
- KPI cards, charts, and scenic ledger rows continue sharing the same year filter.
- Do not modify backend aggregation, API response structures, database data, or unrelated filters.
- Preserve all unrelated uncommitted workspace changes.

---

### Task 1: Default Operation Metrics to All Years

**Files:**
- Modify: `frontend/src/views/operation/index.test.js`
- Modify: `frontend/src/views/operation/index.vue:20-22`
- Modify: `frontend/src/views/operation/index.vue:323-331`

**Interfaces:**
- Consumes: `getFinancial(): Promise<FinancialDashboard>` where `available_years` lists selectable years and `ledger_profit` contains `year`, `service_fee`, and related metric fields.
- Produces: `selectedYear: Ref<number | "">` whose empty value means all years; `filteredSummary` remains the single aggregate used by KPI cards and ledger totals.

- [ ] **Step 1: Write the failing default-and-manual-filter test**

Add this test inside the existing `describe('经营数据中心', ...)` block in `frontend/src/views/operation/index.test.js`:

```javascript
it('默认汇总全部年份并保留手工年份筛选', async () => {
  await mountView()

  const yearSelect = wrapper.findAllComponents({ name: 'ElSelect' })[0]
  expect(wrapper.vm.selectedYear).toBe('')
  expect(yearSelect.attributes('placeholder')).toBe('全部年份')
  expect(wrapper.vm.filteredSummary.total_gross_income).toBe(110000)

  yearSelect.vm.$emit('update:modelValue', 2026)
  await flushPromises()
  expect(wrapper.vm.filteredSummary.total_gross_income).toBe(50000)

  yearSelect.vm.$emit('update:modelValue', '')
  await flushPromises()
  expect(wrapper.vm.filteredSummary.total_gross_income).toBe(110000)
})
```

- [ ] **Step 2: Run the focused test and verify the current behavior fails**

Run:

```powershell
cd frontend
npx vitest run src/views/operation/index.test.js
```

Expected: FAIL because `load()` automatically changes `selectedYear` from `''` to `2026`, so the initial gross profit is `50000` instead of `110000`; the selector also still uses the `年份` placeholder.

- [ ] **Step 3: Implement the minimal default-filter change**

In `frontend/src/views/operation/index.vue`, change the year selector copy from:

```vue
<el-select v-model="selectedYear" placeholder="年份" clearable class="filter-control">
```

to:

```vue
<el-select v-model="selectedYear" placeholder="全部年份" clearable class="filter-control">
```

Then reduce `load()` to preserve the empty all-years state:

```javascript
async function load() {
  loading.value = true
  try {
    dash.value = await getFinancial()
  } finally {
    loading.value = false
  }
}
```

Do not change `matchesSharedFilters`, `aggregatePoints`, the backend endpoint, or the response schema.

- [ ] **Step 4: Run the focused component test**

Run:

```powershell
cd frontend
npx vitest run src/views/operation/index.test.js
```

Expected: all tests in `src/views/operation/index.test.js` pass. The new test proves all-years default, manual 2026 filtering, and clearing back to all years.

- [ ] **Step 5: Run related strategic-overview and money-format tests**

Run:

```powershell
cd frontend
npx vitest run src/views/operation/index.test.js src/components/screen/DataScreen.test.js src/utils/money.test.js
```

Expected: all selected tests pass; the strategic overview continues consuming the backend total directly and both pages retain the same yuan-to-ten-thousands formatting.

- [ ] **Step 6: Run formatting and diff checks**

Run:

```powershell
git diff --check -- frontend/src/views/operation/index.vue frontend/src/views/operation/index.test.js
git diff -- frontend/src/views/operation/index.vue frontend/src/views/operation/index.test.js
```

Expected: no whitespace errors; the diff contains only the placeholder change, removal of latest-year auto-selection, and the focused regression test.

- [ ] **Step 7: Commit only the implementation files**

```powershell
git add -- frontend/src/views/operation/index.vue frontend/src/views/operation/index.test.js
git commit -m "fix: default operation metrics to all years"
```

Expected: the commit includes exactly the component and its test; unrelated workspace changes remain unstaged.
