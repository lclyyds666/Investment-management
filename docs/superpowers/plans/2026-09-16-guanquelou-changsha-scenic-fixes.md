# 鹳雀楼算法、长沙地图与酒店配置修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按确认口径修复鹳雀楼四平台门票计算，接入长沙动趣王国及湖南地图节点，并从酒店配置页移除四个无酒店业务景区。

**Architecture:** 保留现有 Excel 解析器和通用台账计算器的边界，在解析层为鹳雀楼归一化各平台计算基数，在计算层保证鹳雀楼佣金恒为零；长沙景区按现有独立分支的单一功能提交移植到当前主分支；酒店配置和大屏地图分别复用景区能力元数据与显式省份坐标。接口、ORM 和数据库结构不变。

**Tech Stack:** Python 3.13、FastAPI 服务层、`openpyxl`、`Decimal`、pytest/unittest、Vue 3、Element Plus、ECharts、Vitest、Vite。

## Global Constraints

- 鹳雀楼抖音基数必须为订单实收，美团基数必须为应付金额加技术服务费，携程基数必须为结算价金额，同程基数必须为订单金额。
- 鹳雀楼景区核销金额必须等于平台基数乘核销率，结算金额必须等于平台基数乘结算费率；按日四舍五入到分后累加。
- 鹳雀楼服务商佣金固定为零；其他景区现有到账和佣金规则不得改变。
- 长沙景区 ID 固定为 `changsha-dongqu`，名称固定为“长沙动趣王国”，省份固定为“湖南省”，只启用门票业务。
- 酒店配置只展示泉城欧乐堡、泉州欧乐堡、福州欧乐堡；四个无酒店景区仍保留门票配置和门票功能。
- 不新增数据库字段、迁移或 API 字段；不自动改写既有历史台账。
- 不覆盖或提交工作区中与本任务无关的用户改动。

---

### Task 1: Correct Guanquelou platform bases

**Files:**
- Modify: `backend/app/services/ticket_ledger.py:349-603`
- Modify: `backend/app/services/ledger_calculator.py:97-164`
- Test: `backend/tests/test_ticket_ledger_ctrip_parser.py:329-552`
- Test: `backend/tests/test_scenic_ledger_calculator.py`

**Interfaces:**
- Consumes: `parse_reconciliation(..., scenic_id="guanquelou")`, `calculate_ticket_ledger(scenic_id, excel_data, ...)`, and existing `daily_json` shapes.
- Produces: unchanged parser/API dictionaries where `supplier_received` is the confirmed platform base, `supplier_commission` is zero, and `hexiao_amount` / `jinying_amount` follow the configured rates.

- [ ] **Step 1: Update the four-platform regression expectations**

  In `test_guanquelou_filters_mixed_scenics_and_real_douyin_headers`, change the production-shaped fixture assertions to the confirmed formulas:

  ```python
  self.assertEqual(by_platform["抖音"]["supplier_received"], Decimal("100.00"))
  self.assertEqual(by_platform["抖音"]["suggested_commission"], Decimal("0.00"))
  self.assertEqual(by_platform["抖音"]["def_hexiao"], Decimal("90.00"))
  self.assertEqual(by_platform["抖音"]["def_jinying"], Decimal("94.00"))

  self.assertEqual(by_platform["美团"]["supplier_received"], Decimal("43.00"))
  self.assertEqual(by_platform["美团"]["def_hexiao"], Decimal("38.70"))
  self.assertEqual(by_platform["美团"]["def_jinying"], Decimal("40.42"))

  self.assertEqual(by_platform["携程"]["supplier_received"], Decimal("50.00"))
  self.assertEqual(by_platform["携程"]["def_hexiao"], Decimal("45.00"))
  self.assertEqual(by_platform["携程"]["def_jinying"], Decimal("47.00"))

  self.assertEqual(by_platform["同程"]["supplier_received"], Decimal("60.00"))
  self.assertEqual(by_platform["同程"]["def_hexiao"], Decimal("54.00"))
  self.assertEqual(by_platform["同程"]["def_jinying"], Decimal("56.40"))
  ```

  Update the daily JSON assertions so the抖音 daily base is `100` and all commission inputs are zero. Rename and update the three legacy fee-sign tests so both old and new抖音 headers assert `supplier_received == 100.00` and `suggested_commission == 0.00`; the confirmed formula supersedes their former signed-fee fallback expectations. Update the daily recalculation test to assert publisher due `100.00`, commission `0.00`,核销 `90.00`,结算 `94.00`, and service fee `4.00` even when the commission rate changes. Add a zero-valued `技术服务费` column to the signed-ticket-count美团 fixture so that test continues to isolate refund counts rather than the new required-column validation.

- [ ] **Step 2: Add calculator tests for preview and fallback consistency**

  Add a focused test in `test_scenic_ledger_calculator.py` that covers both a daily snapshot and the no-daily fallback:

  ```python
  def test_guanquelou_ticket_uses_platform_base_without_commission(self):
      daily = [{"r": "100", "cs": "100", "cd": "-2", "ct": "-1"}]
      result = ticket_ledger.calculateTicketLedger(
          "guanquelou",
          daily,
          platform="抖音",
          rate_hexiao=Decimal("0.90"),
          rate_settle=Decimal("0.94"),
          commission_rate=Decimal("0.06"),
      )
      fallback = ticket_ledger.compute_row(
          Decimal("100"),
          Decimal("25"),
          Decimal("0.90"),
          Decimal("0.94"),
          platform="抖音",
          scenic_id="guanquelou",
      )

      for calculated in (result, fallback):
          self.assertEqual(calculated["supplier_commission"], Decimal("0.00"))
          self.assertEqual(calculated["publisher_due"], Decimal("100.00"))
          self.assertEqual(calculated["hexiao_amount"], Decimal("90.00"))
          self.assertEqual(calculated["jinying_amount"], Decimal("94.00"))
  ```

- [ ] **Step 3: Add a missing Meituan fee-column error test**

  Build a small鹳雀楼美团 sheet with `结算方式、应付金额、张数、时间、产品名称` but no `技术服务费`, and assert:

  ```python
  with self.assertRaisesRegex(ValueError, "技术服务费"):
      ticket_ledger.parse_reconciliation(
          workbook_bytes,
          "鹳雀楼8.1-8.1.xlsx",
          scenic_id="guanquelou",
      )
  ```

- [ ] **Step 4: Run the focused tests and verify the old behavior fails**

  Run:

  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py -q
  ```

  Expected: failures show抖音 still uses the net service-provider amount and commission, while美团 still omits the technical service fee.

- [ ] **Step 5: Normalize Guanquelou amounts in the parser**

  In the抖音 branch of `parse_reconciliation`, replace the current `scenic_id == "guanquelou"` positive/negative fee inference with the confirmed base:

  ```python
  elif scenic_id == "guanquelou":
      base = shishou or Decimal("0")
      commission_daren = Decimal("0")
      commission_tuanzhang = Decimal("0")
  ```

  When populating the commission snapshot for鹳雀楼, store zero in `commission_shishou`, `commission_daren`, and `commission_tuanzhang`. Preserve source `shishou`, `daren`, and `tuanzhang` only as informational historical inputs.

  In the美团 branch, require and add the technical service fee for both遵义 and鹳雀楼:

  ```python
  uses_tech_fee = scenic_id in {"zunyi-zoo", "guanquelou"}
  if uses_tech_fee and i_tech_fee < 0:
      raise ValueError(f"{ticket_product}美团明细缺少必要列：{COL_MT_TECH_FEE}")
  # ...
  if uses_tech_fee:
      tech_fee = _num(raw[i_tech_fee]) if i_tech_fee < len(raw) else None
      base += tech_fee or Decimal("0")
  ```

  Do not change the existing携程 `结算价金额` or同程 `订单金额` branches beyond tests and comments that lock their口径。

- [ ] **Step 6: Enforce zero commission in the shared calculator**

  In `calculate_ticket_ledger`, derive one explicit flag after validating the scenic ID:

  ```python
  commission_exempt = sid == "guanquelou"
  ```

  In both the no-daily and daily branches, set commission to zero when `commission_exempt` is true, even if a stale `commission_override` or old snapshot contains commission inputs. Keep the existing `platform != "抖音"` behavior unchanged for all other景区。

- [ ] **Step 7: Run focused tests and commit the calculator fix**

  Run:

  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py -q
  git diff --check -- backend/app/services/ticket_ledger.py backend/app/services/ledger_calculator.py backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py
  ```

  Expected: focused tests pass and `git diff --check` reports no whitespace errors.

  Commit:

  ```powershell
  git add -- backend/app/services/ticket_ledger.py backend/app/services/ledger_calculator.py backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py
  git commit -m "fix: apply guanquelou platform settlement bases"
  ```

### Task 2: Port Changsha scenic registration

**Files:**
- Modify: `frontend/src/constants/scenic.js:121-143`
- Create: `frontend/src/constants/scenic.test.js`
- Create: `frontend/public/scenic/changsha-dongqu.jpg`
- Modify: `backend/app/services/scenic_config.py:27-35`
- Modify: `backend/tests/test_scenic_config.py:157-203`

**Interfaces:**
- Consumes: existing `SCENIC_DEFS`, `SCENIC_SEEDS`, `getScenicById`, and `list_effective_configs` interfaces.
- Produces: a ticket-only `changsha-dongqu` scenic available in cards, details, ticket configuration, backend defaults, and province aggregation.

- [ ] **Step 1: Add the failing Changsha registration tests**

  Create `frontend/src/constants/scenic.test.js` with the existing feature-branch contract:

  ```javascript
  import { describe, expect, it } from 'vitest'
  import { getScenicById, scenicSpots } from './scenic'

  describe('scenic configuration', () => {
    it('registers Changsha Dongqu Kingdom as a ticket-only scenic spot', () => {
      const spot = getScenicById('changsha-dongqu')
      expect(spot).toMatchObject({
        id: 'changsha-dongqu',
        name: '长沙动趣王国',
        province: '湖南省',
        imagePath: '/scenic/changsha-dongqu.jpg',
        ticketEnabled: true,
        hotelEnabled: false
      })
      expect(spot.scenicPlatforms).toEqual([])
      expect(spot.ticketPlatforms.map(({ key }) => key)).toEqual(['douyin', 'ctrip', 'meituan'])
      expect(scenicSpots).toContainEqual(spot)
    })
  })
  ```

  Extend `test_config_list_endpoint_falls_back_when_hotel_columns_are_missing` to expect `changsha-dongqu`, and add `test_changsha_dongqu_uses_ticket_defaults` with the approved ID, name, order `70`, ticket rates `0.90/0.94`, and commission rate `0.06`.

- [ ] **Step 2: Run the registration tests and verify they fail**

  Run:

  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scenic_config.py -q
  npm --prefix frontend test -- src/constants/scenic.test.js
  ```

  Expected: tests fail because the current main branch has no长沙 definition.

- [ ] **Step 3: Add the Changsha text configuration**

  Add the existing feature-branch seed to `SCENIC_SEEDS`:

  ```python
  ("changsha-dongqu", "长沙动趣王国", 70, SYSTEM_TICKET_PRODUCT, "0.90", "0.94", "0.06", None),
  ```

  Add this entry after鹳雀楼 in `SCENIC_DEFS`:

  ```javascript
  {
    id: 'changsha-dongqu', name: '长沙动趣王国', province: '湖南省', ext: 'jpg',
    ticketEnabled: true, hotelEnabled: false,
    scenic: [],
    ticket: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'ctrip', url: 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard' },
      { key: 'meituan', url: 'https://mpc.meituan.com/#/ticket/product/new' }
    ]
  }
  ```

- [ ] **Step 4: Restore the reviewed binary cover asset**

  The image already exists in Git object `32d76c9`; restore only the absent binary path, then verify its hash matches the reviewed source:

  ```powershell
  git restore --source=32d76c9 -- frontend/public/scenic/changsha-dongqu.jpg
  git rev-parse "32d76c9:frontend/public/scenic/changsha-dongqu.jpg"
  git hash-object frontend/public/scenic/changsha-dongqu.jpg
  ```

  Expected: the two object hashes are identical.

- [ ] **Step 5: Run registration tests and commit the Changsha port**

  Run:

  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scenic_config.py -q
  npm --prefix frontend test -- src/constants/scenic.test.js
  git diff --check -- backend/app/services/scenic_config.py backend/tests/test_scenic_config.py frontend/src/constants/scenic.js frontend/src/constants/scenic.test.js
  ```

  Commit:

  ```powershell
  git add -- backend/app/services/scenic_config.py backend/tests/test_scenic_config.py frontend/src/constants/scenic.js frontend/src/constants/scenic.test.js frontend/public/scenic/changsha-dongqu.jpg
  git commit -m "feat: register Changsha Dongqu scenic"
  ```

### Task 3: Filter hotel configuration by capability

**Files:**
- Modify: `frontend/src/components/ScenicConfigDialog.vue:121-150, 220-260`
- Modify: `frontend/src/components/ScenicConfigDialog.test.js`

**Interfaces:**
- Consumes: `scenicSpots[].hotelEnabled` and the existing full configuration response in `rows`.
- Produces: `hotelRows`, a computed subset used only by the酒店配置 table; the门票配置 table continues using `rows`.

- [ ] **Step 1: Add a failing hotel-row visibility test**

  Expand the test fixtures to include the seven canonical景区 IDs and names, then add:

  ```javascript
  it('shows hotel configuration only for hotel-enabled scenic spots', async () => {
    scenicApi.getScenicConfigs.mockResolvedValue(configsForAllScenics)
    const wrapper = shallowMount(ScenicConfigDialog, { global })
    await wrapper.vm.loadConfigs()

    expect(wrapper.vm.rows.map((row) => row.scenic_id)).toEqual([
      'quancheng-ouleb', 'quanzhou-ouleb', 'fuzhou-ouleb',
      'zunyi-zoo', 'nanyang-wildlife', 'guanquelou', 'changsha-dongqu'
    ])
    expect(wrapper.vm.hotelRows.map((row) => row.scenic_id)).toEqual([
      'quancheng-ouleb', 'quanzhou-ouleb', 'fuzhou-ouleb'
    ])
  })
  ```

- [ ] **Step 2: Run the component test and verify it fails**

  Run:

  ```powershell
  npm --prefix frontend test -- src/components/ScenicConfigDialog.test.js
  ```

  Expected: `hotelRows` does not exist and the酒店 table still receives all rows.

- [ ] **Step 3: Implement the capability filter**

  Import `scenicSpots`, build a stable ID set, and expose a computed subset:

  ```javascript
  import { scenicSpots } from '@/constants/scenic'

  const HOTEL_SCENIC_IDS = new Set(
    scenicSpots.filter((spot) => spot.hotelEnabled).map((spot) => spot.id)
  )
  const hotelRows = computed(() => (
    rows.value.filter((row) => HOTEL_SCENIC_IDS.has(row.scenic_id))
  ))
  ```

  Change only the酒店配置 table binding from `:data="rows"` to `:data="hotelRows"`. Leave the门票配置 table on `rows`.

- [ ] **Step 4: Run the component test and commit the filter**

  Run:

  ```powershell
  npm --prefix frontend test -- src/components/ScenicConfigDialog.test.js
  git diff --check -- frontend/src/components/ScenicConfigDialog.vue frontend/src/components/ScenicConfigDialog.test.js
  ```

  Commit:

  ```powershell
  git add -- frontend/src/components/ScenicConfigDialog.vue frontend/src/components/ScenicConfigDialog.test.js
  git commit -m "fix: hide hotel settings for ticket-only scenics"
  ```

### Task 4: Display Hunan on the screen map

**Files:**
- Modify: `frontend/src/components/screen/ScreenMap.vue:8-40`
- Modify: `frontend/src/components/screen/DataScreen.test.js:54-83`

**Interfaces:**
- Consumes: `provinceData` containing `{ name: "湖南省", revenue, profit, scenicCount }`.
- Produces: an exported `SCREEN_PROVINCE_COORDS` map used by the ECharts node/line builder and directly testable by Vitest.

- [ ] **Step 1: Add failing Hunan aggregation and coordinate assertions**

  Extend `DataScreen.test.js`:

  ```javascript
  const screenMap = wrapper.getComponent({ name: 'ScreenMap' })
  expect(screenMap.props('provinceData').find((item) => item.name === '湖南省')).toMatchObject({
    revenue: 0,
    profit: 0,
    scenicCount: 1
  })
  ```

  Add a named-export test beside the existing tooltip formatter test:

  ```javascript
  it('registers Hunan as a screen-map business node', async () => {
    const { SCREEN_PROVINCE_COORDS } = await import('./ScreenMap.vue')
    expect(SCREEN_PROVINCE_COORDS['湖南省']).toEqual([112.94, 28.23])
  })
  ```

- [ ] **Step 2: Run the screen test and verify the coordinate assertion fails**

  Run:

  ```powershell
  npm --prefix frontend test -- src/components/screen/DataScreen.test.js
  ```

  Expected:长沙 makes湖南 appear in `provinceData`, but `SCREEN_PROVINCE_COORDS` is missing.

- [ ] **Step 3: Export and use the complete coordinate table**

  Move the existing coordinate object into the normal module script next to `formatScreenMapMoney`, export it, and add湖南：

  ```javascript
  export const SCREEN_PROVINCE_COORDS = {
    山东省: [117.02, 36.67],
    福建省: [119.30, 26.08],
    贵州省: [106.71, 26.58],
    河南省: [113.62, 34.75],
    山西省: [112.55, 37.87],
    湖南省: [112.94, 28.23]
  }
  ```

  Replace both node lookup and hub lookup with `SCREEN_PROVINCE_COORDS`; do not change ECharts styling, province matching, or click behavior.

- [ ] **Step 4: Run the screen test and commit the map fix**

  Run:

  ```powershell
  npm --prefix frontend test -- src/components/screen/DataScreen.test.js
  git diff --check -- frontend/src/components/screen/ScreenMap.vue frontend/src/components/screen/DataScreen.test.js
  ```

  Commit:

  ```powershell
  git add -- frontend/src/components/screen/ScreenMap.vue frontend/src/components/screen/DataScreen.test.js
  git commit -m "fix: display Hunan scenic activity on map"
  ```

### Task 5: Run integrated verification

**Files:**
- Verify only; do not modify unrelated failures.

**Interfaces:**
- Consumes: all changes from Tasks 1-4.
- Produces: test/build evidence and a clean task-scoped diff.

- [ ] **Step 1: Run the focused backend suite**

  Run:

  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_ticket_ledger_ctrip_parser.py backend/tests/test_scenic_ledger_calculator.py backend/tests/test_scenic_config.py -q
  ```

  Expected: all focused backend tests pass.

- [ ] **Step 2: Run the focused frontend suite**

  Run:

  ```powershell
  npm --prefix frontend test -- src/constants/scenic.test.js src/components/ScenicConfigDialog.test.js src/components/screen/DataScreen.test.js
  ```

  Expected: all focused frontend tests pass.

- [ ] **Step 3: Run broader regression checks**

  Run:

  ```powershell
  backend\.venv\Scripts\python.exe -m pytest backend/tests -q
  npm --prefix frontend test
  npm --prefix frontend run build
  ```

  Expected: backend suite, frontend suite, and production build pass. Report unrelated pre-existing failures without modifying their files.

- [ ] **Step 4: Review task scope and final diff**

  Run:

  ```powershell
  git diff --check
  git status --short
  git log -5 --oneline
  ```

  Confirm that only the planned files and prior user-owned changes are present, and that no test artifact, generated build output, or unrelated working-tree file was added.

## Self-Review Checklist

- [ ] Every approved design requirement maps to Tasks 1-4.
- [ ] 鹳雀楼 preview, save-time daily recalculation, and no-daily fallback all ignore service-provider commission.
- [ ] 美团 technical service fee preserves its source sign when added to payable amount.
- [ ] Other scenic formulas and the API/database schema remain unchanged.
- [ ] 长沙 appears in frontend cards, backend config defaults,湖南 province aggregation, and map coordinates.
- [ ] Hotel settings show exactly three hotel-enabled scenic spots while ticket settings still show all seven.
- [ ] The binary Changsha cover matches the reviewed feature-branch object hash.
- [ ] Focused tests, broader suites, build, and `git diff --check` are included.
