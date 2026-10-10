# 战略总览景区完成度实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在战略总览点击省份后的核心经营指标区域，按景区和门票/酒店独立展示景区完成度，并保证累计核销与最新待核销余额使用唯一、可测试的数据口径。

**Architecture:** 后端在现有经营财务聚合中增加 `scenic_completion` 明细，不引入第二个大屏接口；累计核销按历史平台行求和，待核销按“景区 + 业务类型”的最新一期只取一次，最后计算完成度。前端继续通过景区常量把后端 `scenic_id` 映射到省份，省份被点击后在右上角指标坞中展示该省逐景区、逐业务类型的完成度列表。

**Tech Stack:** SQLAlchemy、Pydantic、FastAPI、Decimal、Vue 3、Element Plus、Python unittest、Vitest。

## Global Constraints

- 完成度公式固定为 `累计景区核销金额 / (累计景区核销金额 + 最新景区待核销金额)`。
- 聚合维度固定为 `scenic_id + business_type(ticket|hotel)`，同一景区门票和酒店必须分开展示。
- 累计景区核销金额为该景区、该业务类型全部历史平台行的 `hexiao_amount` 之和。
- 最新景区待核销金额为该景区、该业务类型最新一期的滚动余额；同期多个平台共享余额时只取一次，禁止按平台重复相加。
- 最新一期按 `period_end`、`period_start`、`created_at`、`id` 依次确定；缺失日期时排在有日期记录之前，最终由 `created_at` 和 `id` 保证稳定结果。
- 分母为 0 时后端返回 `None`，前端显示 `—`；其他结果保留两位小数并以百分比展示。
- 省级营收、区域利润、全国指标和现有 20 秒轮询继续保留，不改变现有金额口径。
- 大屏只消费已落库台账快照，不重新执行任何景区平台解析公式。

---

### Task 1: 定义完成度 schema 与纯聚合函数

**Files:**
- Modify: `backend/app/schemas/financial.py`
- Modify: `backend/app/services/financial.py`
- Create: `backend/tests/test_scenic_completion.py`

**Interfaces:**
- Produces: `ScenicCompletionDetail(scenic_id, business_type, cumulative_writeoff, pending_writeoff, completion_rate)`。
- Produces: `build_scenic_completion(ticket_rows, hotel_rows) -> list[dict]`。
- Produces: `FinancialDashboard.scenic_completion: list[ScenicCompletionDetail]`。
- Consumes: `app.services.invoice_generation.ticket_period_key` 和 `hotel_period_key`，保证期次身份与发票/台账确认链路一致。

- [ ] **Step 1: 编写累计核销、最新余额去重和零分母失败测试**

```python
def test_completion_sums_platform_writeoff_but_takes_latest_period_pending_once(self):
    rows = [
        ticket(id=1, scenic_id="guanquelou", platform="抖音", period="P1", period_end=date(2026, 8, 31), hexiao="80", pending="400"),
        ticket(id=2, scenic_id="guanquelou", platform="美团", period="P1", period_end=date(2026, 8, 31), hexiao="20", pending="400"),
        ticket(id=3, scenic_id="guanquelou", platform="抖音", period="P2", period_end=date(2026, 9, 30), hexiao="160", pending="240"),
        ticket(id=4, scenic_id="guanquelou", platform="携程", period="P2", period_end=date(2026, 9, 30), hexiao="40", pending="240"),
    ]
    detail = build_scenic_completion(rows, [])[0]
    self.assertEqual(detail["cumulative_writeoff"], Decimal("300.00"))
    self.assertEqual(detail["pending_writeoff"], Decimal("240.00"))
    self.assertEqual(detail["completion_rate"], Decimal("55.56"))

def test_zero_denominator_returns_none(self):
    detail = build_scenic_completion(
        [ticket(id=1, scenic_id="empty", period="P1", hexiao="0", pending="0")], []
    )[0]
    self.assertIsNone(detail["completion_rate"])
```

- [ ] **Step 2: 运行聚合测试确认失败**

Run: `cd backend; python -m unittest tests.test_scenic_completion -v`

Expected: FAIL，`ScenicCompletionDetail` 和 `build_scenic_completion` 尚不存在。

- [ ] **Step 3: 增加输出 schema**

```python
class ScenicCompletionDetail(BaseModel):
    scenic_id: str
    business_type: Literal["ticket", "hotel"]
    cumulative_writeoff: Decimal = Decimal("0")
    pending_writeoff: Decimal = Decimal("0")
    completion_rate: Decimal | None = None


class FinancialDashboard(BaseModel):
    existing_scale: Decimal = Decimal("0")
    total_realized_scale: Decimal = Decimal("0")
    total_gross_income: Decimal = Decimal("0")
    capital_occupation_days: Optional[float] = None
    ledger_profit: List[LedgerProfitPoint] = Field(default_factory=list)
    available_years: List[int] = Field(default_factory=list)
    scenic_ids: List[str] = Field(default_factory=list)
    scenic_completion: List[ScenicCompletionDetail] = Field(default_factory=list)
```

使用百分数数值表示 `completion_rate`，例如 `55.56` 表示 `55.56%`；不返回 0 到 1 的比例，避免前端二次口径猜测。

- [ ] **Step 4: 实现稳定的最新期次选择与金额计算**

```python
def _period_rank(rows: list) -> tuple:
    representative = max(
        rows,
        key=lambda row: (
            row.period_end is not None,
            row.period_end or date.min,
            row.period_start is not None,
            row.period_start or date.min,
            row.created_at or datetime.min,
            row.id or 0,
        ),
    )
    return (
        representative.period_end is not None,
        representative.period_end or date.min,
        representative.period_start is not None,
        representative.period_start or date.min,
        representative.created_at or datetime.min,
        representative.id or 0,
    )
```

```python
def _completion_for_kind(rows, business_type: str, period_key) -> list[dict]:
    by_scenic = defaultdict(list)
    for row in rows:
        by_scenic[row.scenic_id].append(row)

    result = []
    for scenic_id, scenic_rows in by_scenic.items():
        cumulative = sum((decimal_value(row.hexiao_amount) for row in scenic_rows), Decimal("0"))
        periods = defaultdict(list)
        for row in scenic_rows:
            periods[period_key(row)].append(row)
        latest_rows = max(periods.values(), key=_period_rank)
        latest = max(latest_rows, key=lambda row: (row.created_at or datetime.min, row.id or 0))
        pending = decimal_value(latest.pending_writeoff)
        denominator = cumulative + pending
        rate = None if denominator == 0 else (
            cumulative / denominator * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result.append({
            "scenic_id": scenic_id,
            "business_type": business_type,
            "cumulative_writeoff": cumulative.quantize(Decimal("0.01")),
            "pending_writeoff": pending.quantize(Decimal("0.01")),
            "completion_rate": rate,
        })
    return result
```

`build_scenic_completion()` 分别调用 `_completion_for_kind(ticket_rows, "ticket", ticket_period_key)` 和 `_completion_for_kind(hotel_rows, "hotel", hotel_period_key)`，按 `scenic_id, business_type` 稳定排序。同期平台余额不求和，只从该期稳定代表行读取一次；同期平台的 `hexiao_amount` 仍全部进入累计核销。

- [ ] **Step 5: 覆盖门票/酒店拆分与缺失日期排序**

```python
def test_ticket_and_hotel_are_independent_for_same_scenic(self):
    details = build_scenic_completion(
        [ticket(scenic_id="quancheng-ouleb", hexiao="80", pending="20")],
        [hotel(scenic_id="quancheng-ouleb", hexiao="60", pending="40")],
    )
    self.assertEqual(
        [(item["business_type"], item["completion_rate"]) for item in details],
        [("hotel", Decimal("60.00")), ("ticket", Decimal("80.00"))],
    )

def test_dated_period_wins_over_legacy_undated_period(self):
    details = build_scenic_completion([
        ticket(id=99, period="legacy", period_end=None, created_at=datetime(2026, 10, 1), pending="999"),
        ticket(id=1, period="dated", period_end=date(2026, 9, 30), created_at=datetime(2026, 9, 30), pending="100"),
    ], [])
    self.assertEqual(details[0]["pending_writeoff"], Decimal("100.00"))
```

缺失日期的历史期次不得仅因较晚导入而覆盖已有明确业务日期的期次；仅当全部候选都缺日期时才由 `created_at, id` 决定最新项。

- [ ] **Step 6: 运行聚合测试并提交**

Run: `cd backend; python -m unittest tests.test_scenic_completion tests.test_financial_ledger_metrics tests.test_scenic_analytics -v`

Expected: PASS，原财务指标与利润明细不变，完成度列表新增且口径符合公式。

```bash
git add -- backend/app/schemas/financial.py backend/app/services/financial.py backend/tests/test_scenic_completion.py
git commit -m "feat: aggregate scenic completion metrics"
```

### Task 2: 将完成度接入经营财务接口

**Files:**
- Modify: `backend/app/services/financial.py`
- Modify: `backend/tests/test_financial_ledger_metrics.py`
- Modify: `backend/tests/test_operation_api.py`

**Interfaces:**
- Consumes: Task 1 的 `build_scenic_completion()`。
- Produces: `GET /operation/financial` 响应中的 `data.scenic_completion`。
- Preserves: `existing_scale`、`total_realized_scale`、`total_gross_income`、`capital_occupation_days`、`ledger_profit`、`available_years` 和 `scenic_ids`。

- [ ] **Step 1: 编写财务 dashboard 合并失败测试**

```python
def test_dashboard_includes_completion_without_changing_existing_metrics(self):
    result = build_ledger_metrics(self.ticket_rows, self.hotel_rows, today=date(2026, 10, 10))
    self.assertEqual(result["total_gross_income"], Decimal("739.31"))
    self.assertEqual(
        {(item["scenic_id"], item["business_type"]) for item in result["scenic_completion"]},
        {("guanquelou", "ticket"), ("quancheng-ouleb", "hotel")},
    )
```

- [ ] **Step 2: 运行接口聚合测试确认失败**

Run: `cd backend; python -m unittest tests.test_financial_ledger_metrics tests.test_operation_api -v`

Expected: FAIL，dashboard 尚未包含 `scenic_completion`。

- [ ] **Step 3: 在共用 dashboard 结果中合并完成度**

```python
def build_ledger_metrics(ticket_rows, hotel_rows, *, today=None) -> dict:
    result = build_financial_metrics(ticket_rows, hotel_rows, today=today)
    result["scenic_completion"] = build_scenic_completion(ticket_rows, hotel_rows)
    return result
```

继续由 `build_dashboard()` 一次性读取门票和酒店台账并传给两个聚合函数，不增加第二轮数据库查询，也不新增大屏专用端点。

- [ ] **Step 4: 验证 API schema 序列化**

```python
def test_financial_endpoint_serializes_null_zero_denominator(self):
    response = self.client.get("/api/v1/operation/financial")
    self.assertEqual(response.status_code, 200)
    detail = response.json()["data"]["scenic_completion"][0]
    self.assertIn("cumulative_writeoff", detail)
    self.assertIn("pending_writeoff", detail)
    self.assertIsNone(detail["completion_rate"])
```

金额使用 JSON 字符串或数字沿用当前 Pydantic/请求客户端行为；前端统一用 `Number()` 消费，不更改全局 Decimal 序列化配置。

- [ ] **Step 5: 运行后端经营数据回归并提交**

Run: `cd backend; python -m unittest tests.test_financial_ledger_metrics tests.test_operation_api tests.test_scenic_completion -v`

Expected: PASS，`/operation/financial` 权限、原字段和 739.31 毛利润回归值保持不变。

```bash
git add -- backend/app/services/financial.py backend/tests/test_financial_ledger_metrics.py backend/tests/test_operation_api.py
git commit -m "feat: expose scenic completion on financial dashboard"
```

### Task 3: 在省份核心经营指标中展示完成度

**Files:**
- Modify: `frontend/src/components/screen/DataScreen.vue`
- Modify: `frontend/src/components/screen/DataScreen.test.js`

**Interfaces:**
- Consumes: `getFinancial().scenic_completion`。
- Consumes: `getScenicById(scenic_id).province` 与 `.name`。
- Produces: `selectedCompletionDetails`，仅含当前所选省份并按景区名、门票在前酒店在后排序。
- Produces: `formatCompletionRate(value) -> string`，`null`/`undefined` 返回 `—`，其他值返回两位小数百分比。

- [ ] **Step 1: 扩展 API mock 并编写省份拆分显示失败测试**

```javascript
getFinancial.mockResolvedValue({
  total_realized_scale: 123456,
  total_gross_income: 45678,
  ledger_profit: [
    { scenic_id: 'quancheng-ouleb', realized_amount: 100000, service_fee: 20000 }
  ],
  scenic_completion: [
    { scenic_id: 'quancheng-ouleb', business_type: 'ticket', cumulative_writeoff: 800, pending_writeoff: 200, completion_rate: 80 },
    { scenic_id: 'quancheng-ouleb', business_type: 'hotel', cumulative_writeoff: 600, pending_writeoff: 400, completion_rate: 60 },
    { scenic_id: 'zunyi-zoo', business_type: 'ticket', cumulative_writeoff: 0, pending_writeoff: 0, completion_rate: null }
  ]
})

it('shows every scenic and business type separately for the selected province', async () => {
  const screenMap = wrapper.getComponent({ name: 'ScreenMap' })
  screenMap.vm.$emit('province-click', '山东省')
  await wrapper.vm.$nextTick()
  expect(wrapper.findAll('[data-test="completion-row"]').map(node => node.text())).toEqual([
    expect.stringContaining('泉城欧乐堡'),
    expect.stringContaining('泉城欧乐堡')
  ])
  expect(wrapper.text()).toContain('门票')
  expect(wrapper.text()).toContain('酒店')
  expect(wrapper.text()).toContain('80.00%')
  expect(wrapper.text()).toContain('60.00%')
})
```

- [ ] **Step 2: 运行大屏测试确认失败**

Run: `cd frontend; npm test -- src/components/screen/DataScreen.test.js`

Expected: FAIL，页面尚无完成度明细。

- [ ] **Step 3: 增加省份筛选和格式化计算属性**

```javascript
const selectedCompletionDetails = computed(() => {
  if (mode.value !== 'region') return []
  return (fin.value.scenic_completion || [])
    .map((item) => ({ ...item, scenic: getScenicById(item.scenic_id) }))
    .filter((item) => item.scenic?.province === region.value)
    .sort((left, right) => (
      left.scenic.name.localeCompare(right.scenic.name, 'zh-CN')
      || ({ ticket: 0, hotel: 1 }[left.business_type] ?? 9)
      - ({ ticket: 0, hotel: 1 }[right.business_type] ?? 9)
    ))
})

function formatCompletionRate(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toFixed(2)}%`
}
```

`loadFinancial()` 的初始值和异常回退值同时补充 `scenic_completion: []`，避免接口失败时模板访问未定义。

- [ ] **Step 4: 在核心经营指标坞加入可滚动明细**

```vue
<section v-if="mode === 'region'" class="completion-panel" aria-label="景区完成度">
  <div class="completion-title">景区完成度</div>
  <div v-if="selectedCompletionDetails.length" class="completion-list">
    <article
      v-for="item in selectedCompletionDetails"
      :key="`${item.scenic_id}-${item.business_type}`"
      class="completion-row"
      data-test="completion-row"
    >
      <div>
        <strong>{{ item.scenic.name }}</strong>
        <span>{{ item.business_type === 'ticket' ? '门票' : '酒店' }}</span>
      </div>
      <b>{{ formatCompletionRate(item.completion_rate) }}</b>
    </article>
  </div>
  <el-empty v-else :image-size="40" description="该省暂无台账完成度数据" />
</section>
```

指标坞保持固定高度，完成度列表使用内部滚动；营收和区域利润两张卡仍位于列表之前。全国模式不展示逐景区完成度，避免把不同省份的独立指标错误汇总成单一百分比。

- [ ] **Step 5: 覆盖多景区、零分母与省份切换**

测试加入同省第二景区，断言每个 `scenic_id + business_type` 恰好一行；点击贵州省时只显示遵义动物园并把 `null` 渲染为 `—`；返回全国后完成度列表消失；再次点击山东时数据仍来自最新轮询响应。

Run: `cd frontend; npm test -- src/components/screen/DataScreen.test.js src/components/screen/ScreenMap.test.js`

Expected: PASS，原全国/区域金额换算、湖南地图节点和 AI 助手入口测试继续通过。

- [ ] **Step 6: 提交大屏完成度 UI**

```bash
git add -- frontend/src/components/screen/DataScreen.vue frontend/src/components/screen/DataScreen.test.js
git commit -m "feat: show scenic completion by province"
```

### Task 4: 完成战略总览集成回归

**Files:**
- Verify: `backend/app/schemas/financial.py`
- Verify: `backend/app/services/financial.py`
- Verify: `frontend/src/components/screen/DataScreen.vue`

**Interfaces:**
- Verifies: 门票/酒店台账快照到 `/operation/financial` 再到省份指标坞的单向数据链路。

- [ ] **Step 1: 运行后端财务与完成度专项测试**

Run: `cd backend; python -m unittest tests.test_scenic_completion tests.test_financial_ledger_metrics tests.test_scenic_analytics tests.test_operation_api -v`

Expected: PASS。

- [ ] **Step 2: 运行战略大屏专项测试**

Run: `cd frontend; npm test -- src/components/screen/DataScreen.test.js src/components/screen/ScreenMap.test.js src/api/operation.test.js`

Expected: PASS。

- [ ] **Step 3: 运行前端构建**

Run: `cd frontend; npm run build`

Expected: PASS，并生成 `frontend/dist`。

- [ ] **Step 4: 使用真实多平台场景人工验收**

准备同一省份至少两个景区，其中一个同时有门票和酒店；让最新一期包含两个平台且每行保存相同 `pending_writeoff`。核对：累计核销等于全部平台核销之和；最新待核销只取一次；门票和酒店分两行；两个景区分别展示；分母为 0 显示 `—`；省份切换不会残留上一省份数据；现有营收、区域利润及全国毛利润数值不变。

- [ ] **Step 5: 检查数值精度与稳定排序**

用 `1 / 3` 场景确认百分比显示 `33.33%`；用相同期次多平台、缺失日期历史期次和同日导入记录确认后端结果稳定；轮询刷新前后列表键不变化且无重复闪动。

- [ ] **Step 6: 提交集成回归记录**

```bash
git add -- backend frontend
git commit -m "test: verify strategic scenic completion"
```

提交前运行 `git diff --check`，并确认暂存区不含用户已有的无关改动。
