# 经营情况分析与数据 AI 预测实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将原经营数据页面归入“经营数据 → 数据中心”，并新增按景区、门票/酒店、平台分析和预测三项销售指标的“分析预测”页面。

**Architecture:** 后端先把已确认的不规则台账周期转换成只读日序列，再由分析服务生成同比、环比、排名和异常，由预测服务组合历史同期、近期加权平均和线性趋势。天气、节假日、活动和资讯仅作为本次请求的影响因素，Excel 与表单共用 schema；DeepSeek 只解释结果，失败时使用规则模板。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、openpyxl、Python Decimal、Vue 3、Element Plus、ECharts、Vitest、Python unittest。

## Global Constraints

- 只读取 `confirmed == true` 的门票、酒店台账。
- 预测单位固定为景区 + 业务类型 + 平台。
- 预测指标固定为结算金额、景区核销金额和订单量。
- 自定义周期最长 90 天。
- 不调用天气或资讯外部接口。
- 不保存影响因素、预测请求或预测结果。
- 金额保留两位小数，订单量为非负整数。
- 少于三个自身完整周期时按同景区同业务趋势降级并标记低置信度。

---

### Task 1: 建立已确认台账日序列

**Files:**
- Create: `backend/app/services/operation_series.py`
- Create: `backend/tests/test_operation_series.py`

**Interfaces:**
- Produces: `OperationDailyPoint(day, scenic_id, business_type, platform, settlement_amount, writeoff_amount, order_count)`。
- Produces: `build_confirmed_daily_series(ticket_rows, hotel_rows) -> tuple[list[OperationDailyPoint], list[DataQualityIssue]]`。
- Consumes: `period_start`, `period_end`, `confirmed`, `jinying_amount`, `hexiao_amount`, `order_count`。

- [ ] **Step 1: 编写日分摊失败测试**

```python
def test_confirmed_three_day_period_is_split_without_losing_totals(self):
    points, issues = build_confirmed_daily_series([ticket(
        period_start=date(2026, 10, 1), period_end=date(2026, 10, 3),
        jinying_amount=Decimal("100.00"), hexiao_amount=Decimal("80.00"), order_count=10,
        confirmed=True,
    )], [])
    self.assertEqual(sum(p.settlement_amount for p in points), Decimal("100.00"))
    self.assertEqual(sum(p.order_count for p in points), 10)
    self.assertEqual(issues, [])

def test_unconfirmed_and_undated_rows_are_excluded(self):
    self.assertEqual(len(points), 0)
    self.assertEqual(issues[0].code, "missing_period_dates")
```

- [ ] **Step 2: 运行序列测试确认失败**

Run: `cd backend; python -m unittest tests.test_operation_series -v`

Expected: FAIL，序列服务尚不存在。

- [ ] **Step 3: 实现 Decimal 安全分摊**

每日金额先计算等额基础值，尾差全部放入最后一天，确保日序列汇总与台账金额完全一致。订单量用商和余数分配，前若干天各多一个订单。结束日期早于开始日期的行作为数据质量问题排除。

```python
def _split_decimal(total: Decimal, days: int) -> list[Decimal]:
    unit = (total / Decimal(days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    values = [unit] * days
    values[-1] += total - sum(values, Decimal("0"))
    return values


def _split_count(total: int, days: int) -> list[int]:
    quotient, remainder = divmod(max(total, 0), days)
    return [quotient + (1 if index < remainder else 0) for index in range(days)]


def build_confirmed_daily_series(ticket_rows, hotel_rows):
    points, issues = [], []
    for business_type, rows in (("ticket", ticket_rows), ("hotel", hotel_rows)):
        for row in rows:
            if not row.confirmed:
                continue
            if not row.period_start or not row.period_end or row.period_end < row.period_start:
                issues.append(DataQualityIssue(row_id=row.id, business_type=business_type, code="missing_period_dates"))
                continue
            dates = [row.period_start + timedelta(days=offset) for offset in range((row.period_end - row.period_start).days + 1)]
            settlements = _split_decimal(Decimal(row.jinying_amount or 0), len(dates))
            writeoffs = _split_decimal(Decimal(row.hexiao_amount or 0), len(dates))
            orders = _split_count(row.order_count or 0, len(dates))
            points.extend(OperationDailyPoint(day=day, scenic_id=row.scenic_id, business_type=business_type, platform=row.platform, settlement_amount=settlements[index], writeoff_amount=writeoffs[index], order_count=orders[index]) for index, day in enumerate(dates))
    return points, issues
```

- [ ] **Step 4: 运行测试并提交**

Run: `cd backend; python -m unittest tests.test_operation_series -v`

Expected: PASS。

```bash
git add -- backend/app/services/operation_series.py backend/tests/test_operation_series.py
git commit -m "feat: build confirmed ledger daily series"
```

### Task 2: 实现经营情况分析服务与接口

**Files:**
- Create: `backend/app/schemas/operation_analysis.py`
- Create: `backend/app/services/operation_analysis.py`
- Modify: `backend/app/api/v1/endpoints/operation.py`
- Create: `backend/tests/test_operation_analysis.py`
- Create: `backend/tests/test_operation_analysis_api.py`

**Interfaces:**
- Produces: `GET /operation/analysis`。
- Query: `start_date`, `end_date`, repeated `scenic_id`, repeated `business_type`, repeated `platform`。
- Produces: `OperationAnalysisOut(summary, trends, comparisons, rankings, contributions, anomalies, quality_issues)`。

- [ ] **Step 1: 编写同比、环比和异常失败测试**

```python
def test_analysis_returns_comparable_previous_and_last_year_periods(self):
    result = analyze(points, DateRange(date(2026, 9, 1), date(2026, 9, 30)), filters)
    self.assertEqual(result.summary.settlement_amount, Decimal("120.00"))
    self.assertEqual(result.comparisons.settlement.mom_rate, Decimal("20.00"))
    self.assertEqual(result.comparisons.settlement.yoy_rate, Decimal("50.00"))

def test_zero_comparison_denominator_returns_none(self):
    self.assertIsNone(result.comparisons.orders.mom_rate)
```

- [ ] **Step 2: 运行分析服务测试确认失败**

Run: `cd backend; python -m unittest tests.test_operation_analysis -v`

Expected: FAIL，分析服务尚不存在。

- [ ] **Step 3: 实现确定性分析**

当前周期、前一等长周期和上一年同日历周期分别聚合。贡献度以当前筛选总额为分母；分母为零时返回空值。异常规则集中为常量：环比绝对变化至少 30%，或最近六个可比周期偏离均值至少 2 个标准差；规则命中时返回指标、维度、严重度和证据数字。

```python
MOM_ALERT_RATE = Decimal("30.00")
STANDARD_DEVIATION_ALERT = Decimal("2.00")


def percentage_change(current: Decimal, comparison: Decimal) -> Decimal | None:
    if comparison == 0:
        return None
    return ((current - comparison) / comparison * Decimal("100")).quantize(Decimal("0.01"))


def analyze(points, date_range: DateRange, filters: AnalysisFilters) -> OperationAnalysisOut:
    current = aggregate(filter_points(points, date_range, filters))
    previous_range = date_range.shift(days=-date_range.days)
    last_year_range = DateRange(date_range.start.replace(year=date_range.start.year - 1), date_range.end.replace(year=date_range.end.year - 1))
    previous = aggregate(filter_points(points, previous_range, filters))
    last_year = aggregate(filter_points(points, last_year_range, filters))
    return OperationAnalysisOut(
        summary=current,
        trends=build_trends(points, date_range, filters),
        comparisons=build_comparisons(current, previous, last_year),
        rankings=build_rankings(points, date_range, filters),
        contributions=build_contributions(points, date_range, filters),
        anomalies=detect_anomalies(points, date_range, filters, MOM_ALERT_RATE, STANDARD_DEVIATION_ALERT),
        quality_issues=[],
    )
```

- [ ] **Step 4: 暴露权限受控接口**

接口沿用 `supply.operation.view`，数据库只查询已确认台账。日期跨度限定在 366 天内，开始日期晚于结束日期返回 422。

```python
@router.get(
    "/analysis",
    response_model=Response[OperationAnalysisOut],
    dependencies=[Depends(_operation_guard)],
)
def operation_analysis(
    start_date: date,
    end_date: date,
    scenic_id: list[str] = Query(default=[]),
    business_type: list[str] = Query(default=[]),
    platform: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    date_range = validated_date_range(start_date, end_date, max_days=366)
    tickets = db.scalars(select(TicketLedger).where(TicketLedger.confirmed.is_(True))).all()
    hotels = db.scalars(select(HotelLedger).where(HotelLedger.confirmed.is_(True))).all()
    points, issues = build_confirmed_daily_series(tickets, hotels)
    result = analyze(points, date_range, AnalysisFilters(scenic_ids=scenic_id, business_types=business_type, platforms=platform))
    return Response.ok(result.model_copy(update={"quality_issues": issues}))
```

- [ ] **Step 5: 运行服务与 API 测试并提交**

Run: `cd backend; python -m unittest tests.test_operation_analysis tests.test_operation_analysis_api -v`

Expected: PASS。

```bash
git add -- backend/app/schemas/operation_analysis.py backend/app/services/operation_analysis.py backend/app/api/v1/endpoints/operation.py backend/tests/test_operation_analysis.py backend/tests/test_operation_analysis_api.py
git commit -m "feat: add explainable operation analysis"
```

### Task 3: 建立影响因素表单与 Excel 解析

**Files:**
- Create: `backend/app/schemas/operation_forecast.py`
- Create: `backend/app/services/forecast_factor_excel.py`
- Modify: `backend/app/api/v1/endpoints/operation.py`
- Create: `backend/tests/test_forecast_factor_excel.py`
- Create: `frontend/src/components/ForecastFactorEditor.vue`
- Create: `frontend/src/components/ForecastFactorEditor.test.js`
- Modify: `frontend/src/api/operation.js`

**Interfaces:**
- Produces: `ForecastFactor(start_date, end_date, scenic_id, business_type, platform, factor_type, name, impact_rate, remark)`。
- Produces: `GET /operation/forecast-factors/template`。
- Produces: `POST /operation/forecast-factors/parse` multipart upload，返回 `items` 和逐行 `errors`。
- Impact rate input: 百分比小数，`-0.80 <= impact_rate <= 2.00`。

- [ ] **Step 1: 编写 Excel 校验失败测试**

```python
def test_parser_returns_row_errors_without_dropping_valid_rows(self):
    result = parse_factor_workbook(workbook_bytes([
        ["2026-11-01", "2026-11-03", "changsha", "ticket", "抖音", "天气", "雨天", "-10%", ""],
        ["bad-date", "2026-11-03", "changsha", "ticket", "抖音", "活动", "促销", "5%", ""],
    ]))
    self.assertEqual(len(result.items), 1)
    self.assertEqual(result.errors[0].row_no, 3)
```

- [ ] **Step 2: 运行解析测试确认失败**

Run: `cd backend; python -m unittest tests.test_forecast_factor_excel -v`

Expected: FAIL，模板和解析器尚不存在。

- [ ] **Step 3: 实现共用 schema 和 Excel 服务**

固定表头为“开始日期、结束日期、景区、业务类型、平台、因素类型、因素名称、影响比例、备注”。因素类型仅允许天气、节假日、活动、资讯；业务类型仅允许 ticket、hotel 或空；空景区和空平台表示全部。文件限制 `.xlsx`、5MB、1000 行。

```python
class ForecastFactor(BaseModel):
    start_date: date
    end_date: date
    scenic_id: str = ""
    business_type: Literal["", "ticket", "hotel"] = ""
    platform: str = ""
    factor_type: Literal["天气", "节假日", "活动", "资讯"]
    name: str = Field(min_length=1, max_length=100)
    impact_rate: Decimal = Field(ge=Decimal("-0.80"), le=Decimal("2.00"))
    remark: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


def parse_factor_workbook(content: bytes) -> ForecastFactorParseResult:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    validate_headers(next(rows), FACTOR_HEADERS)
    items, errors = [], []
    for row_no, values in enumerate(rows, start=2):
        try:
            items.append(ForecastFactor.model_validate(map_factor_row(values)))
        except (ValidationError, ValueError) as error:
            errors.append(ForecastFactorRowError(row_no=row_no, message=str(error)))
    return ForecastFactorParseResult(items=items, errors=errors)
```

- [ ] **Step 4: 实现前端因素编辑器**

组件支持逐行添加、删除、编辑、下载模板和导入；导入成功行追加到当前表格，错误行显示行号和原因。组件只通过 `v-model` 返回数组，不持久化到 Pinia 或 localStorage。

```javascript
const factors = defineModel({ type: Array, default: () => [] })
const importErrors = ref([])

function addFactor() {
  factors.value = [...factors.value, {
    start_date: '', end_date: '', scenic_id: '', business_type: '', platform: '',
    factor_type: '天气', name: '', impact_rate: 0, remark: ''
  }]
}

function removeFactor(index) {
  factors.value = factors.value.filter((_, itemIndex) => itemIndex !== index)
}

async function importFactors(file) {
  const result = await parseForecastFactors(file.raw)
  factors.value = [...factors.value, ...(result.items || [])]
  importErrors.value = result.errors || []
}
```

- [ ] **Step 5: 运行前后端测试并提交**

Run: `cd backend; python -m unittest tests.test_forecast_factor_excel -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/components/ForecastFactorEditor.test.js`

Expected: PASS。

```bash
git add -- backend/app/schemas/operation_forecast.py backend/app/services/forecast_factor_excel.py backend/app/api/v1/endpoints/operation.py backend/tests/test_forecast_factor_excel.py frontend/src/components/ForecastFactorEditor.vue frontend/src/components/ForecastFactorEditor.test.js frontend/src/api/operation.js
git commit -m "feat: add forecast factor input and import"
```

### Task 4: 实现可解释分层预测算法

**Files:**
- Create: `backend/app/services/operation_forecast.py`
- Create: `backend/tests/test_operation_forecast.py`

**Interfaces:**
- Produces: `forecast(series, request) -> ForecastOut`。
- Produces: `ForecastLine(scenic_id, business_type, platform, baseline, factor_adjustment, forecast, interval_low, interval_high, confidence, reasons)`。
- Consumes: `ForecastRequest(start_date, end_date, scenic_ids, business_types, platforms, factors)`。

- [ ] **Step 1: 编写组合基线失败测试**

```python
def test_forecast_normalizes_weights_when_same_period_is_missing(self):
    result = forecast(points_without_last_year, request)
    self.assertEqual(result.lines[0].components["recent"].weight, Decimal("0.6667"))
    self.assertEqual(result.lines[0].components["trend"].weight, Decimal("0.3333"))

def test_factor_rates_add_and_are_capped_per_day(self):
    result = forecast(points, request_with_factors(Decimal("1.50"), Decimal("1.00")))
    self.assertEqual(result.lines[0].max_daily_factor, Decimal("2.00"))
```

- [ ] **Step 2: 运行预测测试确认失败**

Run: `cd backend; python -m unittest tests.test_operation_forecast -v`

Expected: FAIL，预测服务尚不存在。

- [ ] **Step 3: 实现历史同期、近期和趋势分量**

历史同期读取上一年相同日历区间；近期水平读取目标日前最近三个等长完整周期并按 3:2:1 加权；趋势项使用最近六个等长周期的普通最小二乘斜率，以最近水平的 -50% 至 +100% 限制外推。可用分量按 40%、40%、20% 重新归一化。

```python
BASE_WEIGHTS = {"same_period": Decimal("0.40"), "recent": Decimal("0.40"), "trend": Decimal("0.20")}


def normalized_components(components: dict[str, Decimal | None]) -> dict[str, ForecastComponent]:
    available = {name: value for name, value in components.items() if value is not None}
    weight_total = sum((BASE_WEIGHTS[name] for name in available), Decimal("0"))
    return {
        name: ForecastComponent(value=value, weight=(BASE_WEIGHTS[name] / weight_total).quantize(Decimal("0.0001")))
        for name, value in available.items()
    }


def baseline_for_metric(history, target_range, metric):
    same_period = aggregate_metric(history, target_range.shift(years=-1), metric)
    recent = weighted_recent_periods(history, target_range, metric, weights=(3, 2, 1))
    trend = bounded_linear_trend(history, target_range, metric, periods=6, lower=Decimal("-0.50"), upper=Decimal("1.00"))
    components = normalized_components({"same_period": same_period, "recent": recent, "trend": trend})
    return sum((item.value * item.weight for item in components.values()), Decimal("0")), components
```

- [ ] **Step 4: 实现影响因素、区间和置信度**

同日适用影响比例相加后限制到 -80% 至 +200%。置信区间按历史残差标准差生成，并限制下界不小于零。高置信度要求至少 12 个完整周期且覆盖率至少 90%；3 至 11 个周期为中；使用同景区同业务降级为低。

```python
def combined_factor_rate(day: date, line: ForecastKey, factors: list[ForecastFactor]) -> Decimal:
    rate = sum((factor.impact_rate for factor in factors if factor.applies(day, line)), Decimal("0"))
    return min(max(rate, Decimal("-0.80")), Decimal("2.00"))


def confidence_for(period_count: int, coverage: Decimal, fallback_used: bool) -> Literal["high", "medium", "low"]:
    if fallback_used or period_count < 3:
        return "low"
    if period_count >= 12 and coverage >= Decimal("0.90"):
        return "high"
    return "medium"


def forecast_interval(value: Decimal, residual_sigma: Decimal) -> tuple[Decimal, Decimal]:
    spread = residual_sigma * Decimal("1.96")
    return max(value - spread, Decimal("0")), value + spread
```

- [ ] **Step 5: 实现数据不足降级**

自身少于 3 个周期时，使用同景区同业务全部平台趋势，再按目标平台最近可用金额或订单占比分配；目标平台从未出现时不凭空生成平台预测。若同景区同业务无历史，返回 `insufficient_data` 行而不是零值。

```python
def fallback_baseline(series, key: ForecastKey, metric: str) -> FallbackResult:
    own = complete_periods(series, key, metric)
    if len(own) >= 3:
        return FallbackResult(points=own, used=False)
    peers = complete_periods(series, key.without_platform(), metric)
    shares = latest_platform_shares(series, key.scenic_id, key.business_type, metric)
    if not peers or key.platform not in shares:
        return FallbackResult(points=[], used=True, reason="insufficient_data")
    return FallbackResult(
        points=[point.scale(shares[key.platform]) for point in peers],
        used=True,
        reason="same_scenic_business_fallback",
    )
```

- [ ] **Step 6: 运行算法测试并提交**

Run: `cd backend; python -m unittest tests.test_operation_forecast -v`

Expected: PASS，金额尾差、影响上限、负值下限和低置信度均有断言。

```bash
git add -- backend/app/services/operation_forecast.py backend/tests/test_operation_forecast.py
git commit -m "feat: add explainable operation forecast"
```

### Task 5: 暴露预测、解读和导出接口

**Files:**
- Create: `backend/app/services/operation_insights.py`
- Modify: `backend/app/api/v1/endpoints/operation.py`
- Create: `backend/tests/test_operation_forecast_api.py`
- Modify: `backend/tests/test_ai_tools.py`

**Interfaces:**
- Produces: `POST /operation/forecast`。
- Produces: `POST /operation/forecast/export`，返回 `.xlsx`。
- Produces: `render_operation_insights(analysis_or_forecast) -> {engine, summary, recommendations}`。
- Permissions: forecast uses `supply.operation.create`；export uses `supply.operation.export`。

- [ ] **Step 1: 编写边界和权限失败测试**

```python
def test_forecast_rejects_more_than_ninety_days(self):
    response = client.post("/api/v1/operation/forecast", json={
        "start_date": "2026-11-01", "end_date": "2027-02-01", "factors": []
    })
    self.assertEqual(response.status_code, 422)

def test_forecast_response_is_not_persisted(self):
    before = database_table_counts(self.db)
    client.post("/api/v1/operation/forecast", json=valid_request)
    self.assertEqual(database_table_counts(self.db), before)
```

- [ ] **Step 2: 运行 API 测试确认失败**

Run: `cd backend; python -m unittest tests.test_operation_forecast_api -v`

Expected: FAIL，预测端点尚不存在。

- [ ] **Step 3: 实现请求期计算和规则降级解读**

加载已确认台账 → 构建日序列 → 预测 → 生成规则说明。DeepSeek 配置可用时只接收聚合数字、异常和影响因素摘要，不接收原始客户信息；调用失败返回相同结构且 `engine="rules"`。

```python
def render_operation_insights(result) -> dict:
    rule_result = {
        "engine": "rules",
        "summary": build_rule_summary(result),
        "recommendations": build_rule_recommendations(result),
    }
    if not settings.DEEPSEEK_API_KEY:
        return rule_result
    try:
        return {"engine": "deepseek", **deepseek_explain(sanitize_aggregate_result(result))}
    except Exception:
        return rule_result


@router.post("/forecast", response_model=Response[ForecastOut], dependencies=[Depends(_operation_create_guard)])
def operation_forecast(payload: ForecastRequest, db: Session = Depends(get_db)):
    validated_date_range(payload.start_date, payload.end_date, max_days=90)
    series, issues = load_confirmed_operation_series(db)
    result = forecast(series, payload)
    return Response.ok(result.model_copy(update={"quality_issues": issues, "insights": render_operation_insights(result)}))
```

- [ ] **Step 4: 实现即时 Excel 导出**

导出接口用相同 `ForecastRequest` 重新计算，工作簿包含“预测汇总”“分层明细”“影响因素”“数据质量”四个工作表。导出过程不落库。

```python
def build_forecast_workbook(result: ForecastOut, request: ForecastRequest) -> bytes:
    workbook = Workbook()
    write_summary_sheet(workbook.active, result)
    workbook.active.title = "预测汇总"
    write_lines_sheet(workbook.create_sheet("分层明细"), result.lines)
    write_factors_sheet(workbook.create_sheet("影响因素"), request.factors)
    write_quality_sheet(workbook.create_sheet("数据质量"), result.quality_issues)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@router.post("/forecast/export", dependencies=[Depends(_operation_export_guard)])
def export_operation_forecast(payload: ForecastRequest, db: Session = Depends(get_db)):
    result = calculate_forecast_response(db, payload)
    return StreamingResponse(BytesIO(build_forecast_workbook(result, payload)), media_type=XLSX_MIME, headers={"Content-Disposition": "attachment; filename=operation-forecast.xlsx"})
```

- [ ] **Step 5: 运行 API 测试并提交**

Run: `cd backend; python -m unittest tests.test_operation_forecast_api tests.test_ai_tools -v`

Expected: PASS。

```bash
git add -- backend/app/services/operation_insights.py backend/app/api/v1/endpoints/operation.py backend/tests/test_operation_forecast_api.py backend/tests/test_ai_tools.py
git commit -m "feat: expose forecast and export APIs"
```

### Task 6: 拆分经营数据菜单并建设分析预测页面

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/router/legacyRedirects.js`
- Modify: `frontend/src/router/routes.test.js`
- Modify: `frontend/src/layout/index.vue`
- Modify: `frontend/src/layout/index.test.js`
- Modify: `frontend/src/views/operation/index.vue`
- Modify: `frontend/src/views/operation/index.test.js`
- Create: `frontend/src/views/operation/analysis.vue`
- Create: `frontend/src/views/operation/analysis.test.js`
- Modify: `frontend/src/api/operation.js`

**Interfaces:**
- Route: `Operation` remains `/supplymanagement/operation`, title `数据中心`, group `经营数据`。
- Route: `OperationAnalysis` at `/supplymanagement/operation/analysis`, title `分析预测`, group `经营数据`。
- Legacy `/operation` redirects to `Operation` and preserves query/hash。

- [ ] **Step 1: 编写路由与菜单失败测试**

```javascript
expect(router.resolve('/supplymanagement/operation').meta.title).toBe('数据中心')
expect(router.resolve('/supplymanagement/operation/analysis').name).toBe('OperationAnalysis')
expect(operationRoutes.map(route => route.meta.group)).toEqual(['经营数据', '经营数据'])
```

- [ ] **Step 2: 运行路由测试确认失败**

Run: `cd frontend; npm test -- src/router/routes.test.js src/layout/index.test.js`

Expected: FAIL，分析预测路由尚不存在。

- [ ] **Step 3: 更新路由与原页面文案**

将原页面标题和测试描述改为“数据中心”，数据与图表逻辑不变；两个路由通过现有 `meta.group` 生成“经营数据”一级折叠菜单。

```javascript
{
  path: 'operation',
  name: 'Operation',
  component: () => import('@/views/operation/index.vue'),
  meta: { title: '数据中心', icon: 'TrendCharts', group: '经营数据', groupIcon: 'DataAnalysis', company: supplyCompany, resource: RESOURCE_CODES.SUPPLY_OPERATION }
},
{
  path: 'operation/analysis',
  name: 'OperationAnalysis',
  component: () => import('@/views/operation/analysis.vue'),
  meta: { title: '分析预测', icon: 'DataAnalysis', group: '经营数据', groupIcon: 'DataAnalysis', company: supplyCompany, resource: RESOURCE_CODES.SUPPLY_OPERATION }
}
```

- [ ] **Step 4: 实现经营情况分析页签**

统一筛选区包含时间、景区、业务、平台；展示四张 KPI、趋势图、同比/环比、排名、贡献度、异常和经营洞察。所有金额显示万元但 API 数据保持元。

```javascript
const analysisFilters = reactive({ dateRange: [], scenic_ids: [], business_types: [], platforms: [] })
const analysis = ref(null)

async function loadAnalysis() {
  const [start_date, end_date] = analysisFilters.dateRange || []
  analysis.value = await getOperationAnalysis({
    start_date, end_date,
    scenic_id: analysisFilters.scenic_ids,
    business_type: analysisFilters.business_types,
    platform: analysisFilters.platforms
  })
}

const analysisCards = computed(() => analysis.value ? [
  { label: '结算金额', value: yuanToWan(analysis.value.summary.settlement_amount) },
  { label: '景区核销金额', value: yuanToWan(analysis.value.summary.writeoff_amount) },
  { label: '订单量', value: analysis.value.summary.order_count },
  { label: '资金占用', value: yuanToWan(analysis.value.summary.capital_occupation) }
] : [])
```

- [ ] **Step 5: 实现数据 AI 预测页签**

左侧为周期和影响因素，右侧为三项预测 KPI、历史/预测趋势及区间、分层明细、置信度和解释。生成按钮仅在用户具有 `supply.operation.create` 时显示，导出按钮要求 `supply.operation.export`。

```javascript
const forecastRequest = reactive({ start_date: '', end_date: '', scenic_ids: [], business_types: [], platforms: [], factors: [] })
const forecastResult = ref(null)
const canForecast = computed(() => portalStore.hasPermission('supply.operation.create'))
const canExport = computed(() => portalStore.hasPermission('supply.operation.export'))

async function generateForecast() {
  if (!canForecast.value) return
  forecastResult.value = await createOperationForecast({ ...forecastRequest })
}

async function exportForecast() {
  if (!canExport.value) return
  downloadBlob(await exportOperationForecast({ ...forecastRequest }), '经营数据预测.xlsx')
}
```

- [ ] **Step 6: 运行页面测试和构建**

Run: `cd frontend; npm test -- src/router/routes.test.js src/layout/index.test.js src/views/operation/index.test.js src/views/operation/analysis.test.js src/components/ForecastFactorEditor.test.js`

Expected: PASS。

Run: `cd frontend; npm run build`

Expected: PASS。

- [ ] **Step 7: 提交菜单和页面**

```bash
git add -- frontend/src/router/index.js frontend/src/router/legacyRedirects.js frontend/src/router/routes.test.js frontend/src/layout/index.vue frontend/src/layout/index.test.js frontend/src/views/operation/index.vue frontend/src/views/operation/index.test.js frontend/src/views/operation/analysis.vue frontend/src/views/operation/analysis.test.js frontend/src/api/operation.js
git commit -m "feat: add operation analysis and forecast workspace"
```
