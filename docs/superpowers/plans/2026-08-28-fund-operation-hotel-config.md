# 资金管理、经营台账与酒店配置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可追溯的资金流水与 30 天到期预警、经营数据中心景区台账、独立酒店配置，并将资金管理、经营数据中心和战略总览的金额按万元展示。

**Architecture:** 后端金额继续以元存储和计算；资金管理新增独立模型、服务与 REST API；经营聚合在现有门票/酒店台账数据点上补充投入和占用权重；景区配置增加酒店专属快照字段。前端只在三个指定页面通过统一工具做元/万元边界转换，景区台账继续使用元。

**Tech Stack:** Python 3、FastAPI 0.115、SQLAlchemy 2、Pydantic 2、MySQL 8、stdlib `unittest`、Vue 3、Pinia、Element Plus、ECharts 5、Vitest 3、Vite 6。

## Global Constraints

- 后端数据库和 API 金额单位始终为元，Numeric 精度保持 `18,2`。
- 只有资金管理、经营数据中心和战略总览按万元展示；其他现有页面不改单位。
- 门票、酒店、景区原始核销台账和导出保持元。
- 酒店平台本轮只允许抖音、美团、携程，不接入同程。
- 保留经营数据中心顶部四张指标卡、柱状图和环形图，景区台账新增在页面尾部。
- 酒店配置只影响后续新解析，历史台账快照不自动重算。
- 使用现有 `supply.finance.view` 和 `supply.finance.update` 权限，不新增权限码。
- 工作区已有用户改动；只修改本计划列出的文件，不覆盖无关变更。
- 不创建 Git 提交，除非用户另行明确要求。

---

## File Map

### 新建文件

- `backend/app/models/fund.py`：资金流水 ORM。
- `backend/app/schemas/fund.py`：资金流水输入、输出、筛选和汇总 schema。
- `backend/app/services/fund.py`：资金汇总、到期状态和查询条件的纯业务逻辑。
- `backend/app/api/v1/endpoints/fund.py`：资金 CRUD、结清和汇总接口。
- `backend/migrations/20260828_fund_management.sql`：资金流水表迁移。
- `backend/migrations/20260828_hotel_config.sql`：景区酒店配置字段迁移。
- `backend/tests/test_fund_management.py`：资金模型、校验、汇总和预警测试。
- `backend/tests/test_fund_api.py`：资金接口注册、权限和 CRUD 测试。
- `frontend/src/api/fund.js`：资金管理 API 封装。
- `frontend/src/utils/money.js`：元/万元转换与格式化。
- `frontend/src/utils/money.test.js`：金额转换测试。
- `frontend/src/views/finance/fund.test.js`：资金页面交互测试。
- `frontend/src/views/operation/index.test.js`：经营页面筛选、图表保留和台账测试。
- `frontend/src/components/ScenicConfigDialog.test.js`：门票/酒店页签与载荷测试。

### 修改文件

- `backend/app/api/v1/router.py`：注册 `/funds` 路由。
- `backend/app/models/scenic_config.py:10`：增加酒店配置列。
- `backend/app/schemas/scenic_config.py:8`：增加酒店配置输入输出 schema。
- `backend/app/services/scenic_config.py:30`：增加酒店默认值、种子和有效配置。
- `backend/app/api/v1/endpoints/scenic.py:100`：序列化并保存酒店配置。
- `backend/app/schemas/hotel_ledger.py`：解析结果携带酒店配置快照。
- `backend/app/api/v1/endpoints/hotel_ledger.py:367`：解析、保存时读取酒店配置。
- `backend/tests/test_scenic_config.py`：酒店配置默认和持久化测试。
- `backend/tests/test_hotel_scenic_config.py`：酒店独立配置联动测试。
- `backend/app/services/scenic_analytics.py:111`：经营点增加投入与占用权重。
- `backend/app/schemas/financial.py:8`：扩展经营点 schema。
- `backend/tests/test_scenic_analytics.py`：景区聚合和酒店去重测试。
- `backend/tests/test_financial_ledger_metrics.py`：经营接口响应契约测试。
- `frontend/src/views/finance/fund.vue`：实现资金管理页面。
- `frontend/src/api/scenic.js`：增加酒店配置更新 API。
- `frontend/src/components/ScenicConfigDialog.vue`：拆分门票/酒店配置页签。
- `frontend/src/utils/hotelLedgerDraft.js:18`：平台名称不再拼接酒店名称，并消费酒店快照。
- `frontend/src/utils/hotelLedgerDraft.test.js`：平台标签和酒店快照测试。
- `frontend/src/components/HotelLedger.vue`：移除硬编码酒店默认值，平台列只显示平台名。
- `frontend/src/views/operation/index.vue:90`：万元展示、筛选汇总和尾部景区台账。
- `frontend/src/components/screen/DataScreen.vue:193`：战略总览指标按万元展示。
- `frontend/src/components/screen/ScreenMap.vue:79`：地图提示按万元展示。
- `frontend/src/components/screen/DataScreen.test.js`：战略总览万元测试。
- `README.md`：记录迁移和功能变更。

---

### Task 1: 统一元/万元转换工具

**Files:**
- Create: `frontend/src/utils/money.js`
- Create: `frontend/src/utils/money.test.js`

**Interfaces:**
- Produces: `yuanToWan(value: unknown): number`
- Produces: `wanToYuan(value: unknown): number`
- Produces: `formatWanFromYuan(value: unknown, options?: { prefix?: string, suffix?: string }): string`
- Produces: `formatWanValue(value: unknown, options?: { prefix?: string, suffix?: string }): string`

- [ ] **Step 1: 写失败测试**

~~~javascript
import { describe, expect, it } from 'vitest'
import {
  formatWanFromYuan,
  formatWanValue,
  wanToYuan,
  yuanToWan
} from './money'

describe('money unit boundary', () => {
  it('converts yuan and wan exactly at the API boundary', () => {
    expect(yuanToWan(123456.78)).toBe(12.345678)
    expect(wanToYuan(12.345678)).toBe(123456.78)
    expect(wanToYuan(yuanToWan(1))).toBe(1)
  })

  it('formats API yuan and already-converted wan separately', () => {
    expect(formatWanFromYuan(123456.78)).toBe('¥12.35 万元')
    expect(formatWanValue(12.345678)).toBe('¥12.35 万元')
  })

  it('normalizes empty and invalid values to zero', () => {
    expect(yuanToWan(null)).toBe(0)
    expect(wanToYuan('bad')).toBe(0)
  })
})
~~~

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; npm test -- --run src/utils/money.test.js`  
Expected: FAIL，提示找不到 `./money`。

- [ ] **Step 3: 实现金额边界工具**

~~~javascript
export const YUAN_PER_WAN = 10000

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

export function yuanToWan(value) {
  return finiteNumber(value) / YUAN_PER_WAN
}

export function wanToYuan(value) {
  return Math.round(finiteNumber(value) * YUAN_PER_WAN * 100) / 100
}

function format(value, { prefix = '¥', suffix = ' 万元' } = {}) {
  const amount = finiteNumber(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
  return prefix + amount + suffix
}

export function formatWanFromYuan(value, options) {
  return format(yuanToWan(value), options)
}

export function formatWanValue(value, options) {
  return format(value, options)
}
~~~

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend; npm test -- --run src/utils/money.test.js`  
Expected: PASS。

- [ ] **Step 5: 检查转换调用约束**

确认 `formatWanFromYuan` 只接收 API 元值，`formatWanValue` 只接收已经除以 10000 的图表值。

---

### Task 2: 资金领域模型、校验与汇总

**Files:**
- Create: `backend/app/models/fund.py`
- Create: `backend/app/schemas/fund.py`
- Create: `backend/app/services/fund.py`
- Create: `backend/migrations/20260828_fund_management.sql`
- Create: `backend/tests/test_fund_management.py`

**Interfaces:**
- Produces: `FundTransaction` ORM。
- Produces: `FundTransactionCreate`、`FundTransactionUpdate`、`FundTransactionOut`、`FundSummary`。
- Produces: `summarize_funds(rows, today) -> FundSummary`。
- Produces: `maturity_state(row, today) -> str`，返回 `normal`、`due_soon`、`overdue` 或 `settled`。

- [ ] **Step 1: 写资金校验和汇总失败测试**

~~~python
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.schemas.fund import FundTransactionCreate
from app.services.fund import maturity_state, summarize_funds


class FundManagementTest(unittest.TestCase):
    def test_summary_and_warning_boundaries(self):
        rows = [
            SimpleNamespace(
                direction="increase", category="bank_credit",
                amount=Decimal("1000000"), maturity_date=date(2026, 9, 27),
                settlement_status="open",
            ),
            SimpleNamespace(
                direction="increase", category="customer_payment",
                amount=Decimal("200000"), maturity_date=None,
                settlement_status="open",
            ),
            SimpleNamespace(
                direction="usage", category="business_payment",
                amount=Decimal("350000"), maturity_date=None,
                settlement_status="open",
            ),
        ]

        summary = summarize_funds(rows, today=date(2026, 8, 28))

        self.assertEqual(summary.total_increase, Decimal("1200000"))
        self.assertEqual(summary.total_usage, Decimal("350000"))
        self.assertEqual(summary.available_funds, Decimal("850000"))
        self.assertEqual(summary.due_within_30_amount, Decimal("1000000"))
        self.assertEqual(maturity_state(rows[0], date(2026, 8, 28)), "due_soon")

    def test_day_31_is_not_due_soon_and_past_date_is_overdue(self):
        day_31 = SimpleNamespace(
            direction="increase", category="company_loan",
            maturity_date=date(2026, 9, 28), settlement_status="open",
        )
        overdue = SimpleNamespace(
            direction="increase", category="company_loan",
            maturity_date=date(2026, 8, 27), settlement_status="open",
        )
        self.assertEqual(maturity_state(day_31, date(2026, 8, 28)), "normal")
        self.assertEqual(maturity_state(overdue, date(2026, 8, 28)), "overdue")

    def test_credit_requires_maturity_and_positive_amount(self):
        with self.assertRaises(ValidationError):
            FundTransactionCreate(
                direction="increase", category="bank_credit",
                amount=Decimal("1"), occurred_on=date(2026, 8, 28),
                counterparty="测试银行", summary="流动资金授信",
            )
        with self.assertRaises(ValidationError):
            FundTransactionCreate(
                direction="usage", category="customer_payment",
                amount=Decimal("0"), occurred_on=date(2026, 8, 28),
                counterparty="客户", summary="非法方向类型组合",
            )
~~~

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_fund_management -v`  
Expected: FAIL，提示 `app.schemas.fund` 不存在。

- [ ] **Step 3: 创建资金 ORM 和幂等迁移**

`FundTransaction` 使用字符串列保存方向、类型和状态，避免 MySQL native enum 演进成本。迁移创建索引 `idx_fund_occurred_on`、`idx_fund_maturity_status`，并为 `amount` 添加 `DECIMAL(18,2) NOT NULL`。

~~~python
class FundTransaction(Base):
    __tablename__ = "biz_fund_transaction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(String(300), default="")
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    settlement_status: Mapped[str] = mapped_column(String(16), default="open")
    settled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"), nullable=True)
~~~

- [ ] **Step 4: 实现 Pydantic 交叉校验**

`FundTransactionCreate` 使用 `model_validator(mode="after")` 校验：
- 金额大于 0。
- 方向与类型属于对应允许集合。
- 授信、借款必须有到期日。
- `settled_on` 不早于 `occurred_on`。
- 只有银行授信、公司借款允许 `settlement_status="settled"`。

更新 schema 继承相同验证逻辑，输出 schema 增加只读 `maturity_status`。

- [ ] **Step 5: 实现纯汇总与预警函数**

~~~python
DUE_CATEGORIES = frozenset({"bank_credit", "company_loan"})

def maturity_state(row, today: date) -> str:
    if row.settlement_status == "settled":
        return "settled"
    if row.category not in DUE_CATEGORIES or not row.maturity_date:
        return "normal"
    days = (row.maturity_date - today).days
    if days < 0:
        return "overdue"
    return "due_soon" if days <= 30 else "normal"
~~~

`summarize_funds` 使用 `Decimal("0")` 累加，不把已结清资金增加从余额中剔除，只停止预警。

- [ ] **Step 6: 运行资金领域测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_fund_management -v`  
Expected: PASS。

- [ ] **Step 7: 检查迁移**

Run: `git diff --check -- backend/migrations/20260828_fund_management.sql backend/app/models/fund.py backend/app/schemas/fund.py backend/app/services/fund.py backend/tests/test_fund_management.py`  
Expected: 无输出。

---

### Task 3: 资金 REST API 与权限

**Files:**
- Create: `backend/app/api/v1/endpoints/fund.py`
- Create: `backend/tests/test_fund_api.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Produces: `GET /api/v1/funds`，参数 `page`、`page_size`、`direction`、`category`、`settlement_status`、`maturity_status`、`start_date`、`end_date`、`keyword`。
- Produces: `GET /api/v1/funds/summary`。
- Produces: `POST /api/v1/funds`、`PUT /api/v1/funds/{id}`、`DELETE /api/v1/funds/{id}`、`POST /api/v1/funds/{id}/settle`。

- [ ] **Step 1: 写接口注册与权限失败测试**

~~~python
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import create_app


class FundApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = Mock()
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7, is_superuser=True, is_active=True
        )
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_routes_are_registered(self):
        paths = {route.path for route in self.app.routes}
        self.assertIn("/api/v1/funds", paths)
        self.assertIn("/api/v1/funds/summary", paths)
        self.assertIn("/api/v1/funds/{fund_id}/settle", paths)
~~~

在同一测试文件加入可持有单行对象的 fake session，并直接调用端点函数：

~~~python
class FakeSession:
    def __init__(self):
        self.row = None

    def add(self, row):
        row.id = 1
        self.row = row

    def get(self, _model, fund_id):
        return self.row if self.row and self.row.id == fund_id else None

    def commit(self):
        return None

    def refresh(self, _row):
        return None

    def delete(self, _row):
        self.row = None


def test_create_settle_delete_and_missing(self):
    db = FakeSession()
    user = SimpleNamespace(id=9)
    created = create_fund(
        FundTransactionCreate(
            direction="increase", category="company_loan",
            amount=Decimal("100000"), occurred_on=date(2026, 8, 28),
            maturity_date=date(2026, 9, 27), counterparty="股东公司",
            summary="流动资金借款",
        ),
        db,
        user,
    )
    self.assertEqual(db.row.created_by, 9)
    self.assertEqual(created.data.amount, Decimal("100000"))

    settled = settle_fund(
        1, FundSettleIn(settled_on=date(2026, 8, 29)), db, user
    )
    self.assertEqual(settled.data.settlement_status, "settled")

    delete_fund(1, db)
    self.assertIsNone(db.row)
    with self.assertRaises(HTTPException) as raised:
        delete_fund(404, db)
    self.assertEqual(raised.exception.status_code, 404)
~~~

- [ ] **Step 2: 运行接口测试确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_fund_api -v`  
Expected: FAIL，缺少资金路由。

- [ ] **Step 3: 实现资金端点**

端点使用：

~~~python
_supply_context = lambda: PermissionContext(
    company_code=CompanyCode.SUPPLY_MANAGEMENT.value
)
_view_guard = require_permission("supply.finance.view", _supply_context)
_update_guard = require_permission("supply.finance.update", _supply_context)
~~~

列表查询在数据库层应用方向、类型、日期和关键词条件；`maturity_status` 因依赖当前日期，可在候选结果上由 `maturity_state` 过滤后分页。返回 `items`、`total`、`page`、`page_size`。

结清端点只接受银行授信、公司借款，将状态设为 `settled` 并写入用户提交或当天的 `settled_on`；不自动新增还本付息流水。

- [ ] **Step 4: 注册路由**

~~~python
from app.api.v1.endpoints import fund

api_router.include_router(fund.router, prefix="/funds", tags=["智慧财务·资金管理"])
~~~

- [ ] **Step 5: 运行资金后端测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_fund_management tests.test_fund_api -v`  
Expected: PASS。

---

### Task 4: 资金管理前端

**Files:**
- Create: `frontend/src/api/fund.js`
- Modify: `frontend/src/views/finance/fund.vue`
- Create: `frontend/src/views/finance/fund.test.js`

**Interfaces:**
- Consumes: Task 1 金额工具。
- Consumes: Task 3 资金 API。
- Produces: 可筛选、可新增、编辑、删除和结清的资金管理页面。

- [ ] **Step 1: 写页面失败测试**

~~~javascript
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import FundView from './fund.vue'
import * as fundApi from '@/api/fund'

vi.mock('@/api/fund', () => ({
  listFunds: vi.fn(),
  getFundSummary: vi.fn(),
  createFund: vi.fn(),
  updateFund: vi.fn(),
  deleteFund: vi.fn(),
  settleFund: vi.fn()
}))

describe('fund management view', () => {
  beforeEach(() => {
    fundApi.getFundSummary.mockResolvedValue({
      available_funds: 850000,
      total_increase: 1200000,
      total_usage: 350000,
      due_within_30_amount: 1000000
    })
    fundApi.listFunds.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  })

  it('renders summary in ten-thousand yuan', async () => {
    const wrapper = shallowMount(FundView, {
      global: { stubs: { ElCard: false, ElTable: true, ElDialog: true } }
    })
    await flushPromises()
    expect(wrapper.text()).toContain('85.00')
    expect(wrapper.text()).toContain('万元')
  })
})
~~~

补充表单提交测试：

~~~javascript
it('submits wan input as API yuan and blocks credit without maturity', async () => {
  const wrapper = shallowMount(FundView, { global })
  await flushPromises()
  wrapper.vm.openCreate()
  Object.assign(wrapper.vm.form, {
    direction: 'increase', category: 'bank_credit', amountWan: 12.345678,
    occurred_on: '2026-08-28', maturity_date: '2026-09-27',
    counterparty: '测试银行', summary: '流动资金授信'
  })
  await wrapper.vm.submitForm()
  expect(fundApi.createFund).toHaveBeenCalledWith(expect.objectContaining({
    amount: 123456.78
  }))

  fundApi.createFund.mockClear()
  wrapper.vm.form.maturity_date = null
  await wrapper.vm.submitForm()
  expect(fundApi.createFund).not.toHaveBeenCalled()
})
~~~

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; npm test -- --run src/views/finance/fund.test.js`  
Expected: FAIL，当前页面仍为建设中。

- [ ] **Step 3: 创建 API 封装**

`listFunds(params)`、`getFundSummary()`、`createFund(payload)`、`updateFund(id, payload)`、`deleteFund(id)`、`settleFund(id, settledOn)` 均通过现有 `request` 实例调用 Task 3 路径。

- [ ] **Step 4: 实现资金页面**

页面结构：
- 标题区和“新增流水”按钮。
- 四张汇总卡；负余额、即将到期使用明确状态色。
- 方向、类型、结清状态、到期状态、日期范围、关键词筛选。
- 表格列：发生日期、方向、类型、金额（万元）、对方单位、用途、到期日、到期状态、结清状态、操作。
- 新增/编辑弹窗；金额模型为万元，提交前调用 `wanToYuan`。
- 删除前二次确认。
- 结清仅在未结清授信/借款上显示，成功后同时刷新列表与汇总。

使用 `canUsePermission(portalStore, 'supply.finance.update')` 控制写操作按钮，读取页面由路由资源权限控制。

- [ ] **Step 5: 运行资金前端测试**

Run: `cd frontend; npm test -- --run src/utils/money.test.js src/views/finance/fund.test.js`  
Expected: PASS。

---

### Task 5: 酒店独立配置后端

**Files:**
- Create: `backend/migrations/20260828_hotel_config.sql`
- Modify: `backend/app/models/scenic_config.py:10`
- Modify: `backend/app/schemas/scenic_config.py:8`
- Modify: `backend/app/services/scenic_config.py:30`
- Modify: `backend/app/api/v1/endpoints/scenic.py:100`
- Modify: `backend/app/schemas/hotel_ledger.py`
- Modify: `backend/app/api/v1/endpoints/hotel_ledger.py:367`
- Modify: `backend/tests/test_scenic_config.py`
- Modify: `backend/tests/test_hotel_scenic_config.py`

**Interfaces:**
- Produces: `HotelScenicConfigUpdate`。
- Extends: `ScenicConfigOut` 和 `EffectiveScenicConfig`，增加七个 `hotel_*` 字段。
- Produces: `PUT /api/v1/scenic-spots/{scenic_id}/hotel-config`。
- Consumes: 酒店解析/保存使用 `hotel_rate_hexiao`、`hotel_rate_settle`、`hotel_commission_rate`、`hotel_fee_per_night`、`hotel_fee_algo`。

- [ ] **Step 1: 扩展失败测试**

~~~python
def test_hotel_defaults_are_independent_from_ticket_defaults(self):
    config = get_effective_config(None, "fuzhou-ouleb")
    self.assertEqual(config.ticket_rate_hexiao, Decimal("0.91"))
    self.assertEqual(config.hotel_rate_hexiao, Decimal("0.90"))
    self.assertEqual(config.hotel_fee_per_night, Decimal("44"))
    self.assertEqual(config.hotel_fee_algo, 1)
    self.assertEqual(config.hotel_platforms, ("抖音", "美团", "携程"))
~~~

在 `test_hotel_scenic_config.py` 修改 endpoint 测试，使门票费率为 `0.91`、酒店费率为 `0.82`，断言酒店解析和旧客户端缺省保存均使用 `0.82`。

- [ ] **Step 2: 运行配置测试确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_scenic_config tests.test_hotel_scenic_config -v`  
Expected: FAIL，缺少 `hotel_*` 字段。

- [ ] **Step 3: 增加模型字段与迁移**

迁移幂等增加：
- `default_hotel_name VARCHAR(255)`。
- 三个 `DECIMAL(6,4)` 酒店费率。
- `hotel_fee_per_night DECIMAL(18,2)`。
- `hotel_fee_algo TINYINT`。
- `hotel_platforms VARCHAR(64)`，数据库值使用逗号分隔规范名。

已有景区默认填入当前行为：默认酒店名称、`0.9000`、`0.9400`、`0.0600`、`44.00`、算法 1、`抖音,美团,携程`。

- [ ] **Step 4: 扩展有效配置与 schema**

`EffectiveScenicConfig.hotel_platforms` 对外使用 `tuple[str, ...]`；模型字符串只在 service 层解析/序列化。`HotelScenicConfigUpdate` 校验：
- 名称非空。
- 费率位于 0 至 1。
- 每间夜服务费不小于 0。
- 算法为 1 或 2。
- 平台非空、去重，且是 `{"抖音", "美团", "携程"}` 的子集。

- [ ] **Step 5: 增加酒店配置保存端点**

~~~python
@router.put(
    "/{scenic_id}/hotel-config",
    response_model=Response[ScenicConfigOut],
    summary="修改景区酒店默认配置",
)
def update_hotel_config(
    scenic_id: str,
    payload: HotelScenicConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_update_guard),
):
    sid = _valid_scenic_id(scenic_id)
    row = db.get(ScenicConfig, sid)
    if row is None:
        fallback = scenic_config_svc.get_effective_config(None, sid)
        row = ScenicConfig(
            scenic_id=sid,
            scenic_name=fallback.scenic_name,
            sort_order=fallback.sort_order,
            default_ticket_product=fallback.default_ticket_product,
            ticket_rate_hexiao=fallback.ticket_rate_hexiao,
            ticket_rate_settle=fallback.ticket_rate_settle,
            ticket_commission_rate=fallback.ticket_commission_rate,
            ticket_default_commission=fallback.ticket_default_commission,
        )
        db.add(row)
    row.default_hotel_name = payload.default_hotel_name
    row.hotel_rate_hexiao = payload.hotel_rate_hexiao
    row.hotel_rate_settle = payload.hotel_rate_settle
    row.hotel_commission_rate = payload.hotel_commission_rate
    row.hotel_fee_per_night = payload.hotel_fee_per_night
    row.hotel_fee_algo = payload.hotel_fee_algo
    row.hotel_platforms = ",".join(payload.hotel_platforms)
    row.updated_by = current_user.id
    db.commit()
    db.refresh(row)
    return Response.ok(_config_out(scenic_config_svc.get_effective_config(db, sid)))
~~~

创建缺失配置行时同时写入门票和酒店 fallback，避免非空字段缺失。现有门票 `PUT /config` 只更新门票字段。

- [ ] **Step 6: 酒店解析与保存改用酒店配置**

`parse_file` 将酒店独立费率传给 `parse_hotel_file`，并把默认酒店名称、每间夜服务费、默认算法写入每个 `ParsedPlatform`。未启用平台从解析结果中移除，并返回明确 warning。

`save_ledger` 在旧客户端未提交费率、算法或每间夜服务费时读取 `hotel_*` 默认值；显式提交的历史快照优先，不被当前配置覆盖。

- [ ] **Step 7: 运行酒店配置测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_scenic_config tests.test_hotel_scenic_config tests.test_hotel_brand_platform_parser -v`  
Expected: PASS。

---

### Task 6: 景区配置页签与酒店平台显示

**Files:**
- Modify: `frontend/src/api/scenic.js`
- Modify: `frontend/src/components/ScenicConfigDialog.vue`
- Create: `frontend/src/components/ScenicConfigDialog.test.js`
- Modify: `frontend/src/utils/hotelLedgerDraft.js:18`
- Modify: `frontend/src/utils/hotelLedgerDraft.test.js`
- Modify: `frontend/src/components/HotelLedger.vue`

**Interfaces:**
- Consumes: `updateHotelScenicConfig(scenicId, payload)`。
- Consumes: Task 5 解析结果中的 `default_hotel_name`、`fee_per_night`、`fee_algo`。
- Produces: 门票配置和酒店配置两个页签。
- Produces: `hotelPlatformLabel(row)` 只返回规范平台名。

- [ ] **Step 1: 修改平台标签失败测试**

~~~javascript
it('shows only the canonical platform in the platform column', () => {
  expect(hotelPlatformLabel({ hotel_name: '海洋', platform: '携程' })).toBe('携程')
  expect(hotelPlatformLabel({ hotel_name: '骑士', platform: '美团' })).toBe('美团')
})
~~~

扩展草稿测试，断言解析结果中的 `hotel_name`、`fee_per_night`、`fee_algo` 原样进入保存载荷，不再使用组件硬编码常量。

- [ ] **Step 2: 写配置页签失败测试**

浅挂载 `ScenicConfigDialog`，mock `getScenicConfigs`、`updateScenicConfig`、`updateHotelScenicConfig`，断言：
- 页面存在“门票配置”“酒店配置”两个页签。
- 酒店保存载荷字段名与 Task 5 一致。
- 启用平台选项只有抖音、美团、携程。

- [ ] **Step 3: 运行测试确认失败**

Run: `cd frontend; npm test -- --run src/utils/hotelLedgerDraft.test.js src/components/ScenicConfigDialog.test.js`  
Expected: FAIL，平台标签仍拼接酒店名称且没有酒店页签。

- [ ] **Step 4: 实现 API 与双页签配置**

保留门票保存逻辑；酒店页签把百分数与 0-1 小数互转，每间夜服务费保持元。每个景区酒店行单独保存，调用 `updateHotelScenicConfig`。

- [ ] **Step 5: 移除酒店硬编码默认值**

`createHotelDraftRows(parseResult)` 直接读取平台对象中的：
- `hotel_name`。
- `fee_per_night`。
- `fee_algo`。
- 三个酒店费率。

`HotelLedger.vue` 删除 `DEFAULT_HOTEL_NAME` 和 `DEFAULT_FEE_PER_NIGHT`，平台列使用新的 `hotelPlatformLabel`。酒店名称仍在独立列，排序仍按酒店和平台联合维度。

- [ ] **Step 6: 运行前端酒店测试**

Run: `cd frontend; npm test -- --run src/utils/hotelLedgerDraft.test.js src/components/ScenicConfigDialog.test.js`  
Expected: PASS。

---

### Task 7: 经营聚合点增加景区投入与占用权重

**Files:**
- Modify: `backend/app/services/scenic_analytics.py:111`
- Modify: `backend/app/schemas/financial.py:8`
- Modify: `backend/tests/test_scenic_analytics.py`
- Modify: `backend/tests/test_financial_ledger_metrics.py`

**Interfaces:**
- Extends: `LedgerProfitPoint` 增加 `existing_scale: Decimal`、`occupation_weight: Decimal`、`occupation_amount: Decimal`。
- Preserves: `FinancialDashboard` 顶层四项汇总字段和现有 `ledger_profit` 字段。
- Produces: 前端可按年份、景区对数据点求和并计算加权占用天数。

- [ ] **Step 1: 写聚合点失败测试**

在现有票务与酒店测试数据上增加断言：

~~~python
ticket_point = next(
    point for point in result["ledger_profit"]
    if point["scenic_id"] == "quancheng-ouleb"
    and point["business_type"] == "ticket"
)
self.assertEqual(ticket_point["existing_scale"], Decimal("800"))
self.assertEqual(ticket_point["occupation_amount"], Decimal("800"))
self.assertEqual(ticket_point["occupation_weight"], Decimal("8000"))

hotel_point = next(
    point for point in result["ledger_profit"]
    if point["business_type"] == "hotel"
)
self.assertEqual(hotel_point["existing_scale"], Decimal("1500"))
self.assertEqual(hotel_point["occupation_amount"], Decimal("1500"))
self.assertEqual(hotel_point["occupation_weight"], Decimal("30000"))
~~~

酒店多个平台的投入和占用权重必须只进入一个聚合点。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_scenic_analytics tests.test_financial_ledger_metrics -v`  
Expected: FAIL，数据点缺少三个字段。

- [ ] **Step 3: 扩展聚合实现**

将占用计算改为返回数据点所需的三个值：

~~~python
def occupation_values(net_investment, start, end, today):
    if net_investment <= 0 or not start:
        return Decimal("0"), Decimal("0")
    days = max(((end or today) - start).days, 0)
    return net_investment * Decimal(days), net_investment
~~~

票务行和酒店期聚合分别把净投入、占用权重、占用金额传入 `_profit_point`。顶层汇总从相同值累加，保证 API 总计与前端筛选汇总同源。

- [ ] **Step 4: 扩展 schema 契约**

`LedgerProfitPoint` 三个新字段默认 `Decimal("0")`，兼容旧测试对象。更新响应字段集合断言，不删除任何现有字段。

- [ ] **Step 5: 运行经营后端测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_scenic_analytics tests.test_financial_ledger_metrics -v`  
Expected: PASS。

---

### Task 8: 经营数据中心万元、筛选联动与尾部台账

**Files:**
- Modify: `frontend/src/views/operation/index.vue:90`
- Create: `frontend/src/views/operation/index.test.js`

**Interfaces:**
- Consumes: Task 1 `yuanToWan`、`formatWanFromYuan`、`formatWanValue`。
- Consumes: Task 7 扩展经营点。
- Produces: `filteredSummary`、`scenicLedgerRows` 和合计行。
- Preserves: 两个 ECharts series 类型分别为 `bar` 和 `pie`。

- [ ] **Step 1: 写经营页面失败测试**

mock `getFinancial` 返回两个景区、两个年份的数据点。浅挂载页面并断言：
- 顶部仍有四张 KPI 卡。
- 页面仍存在柱状图和环形图容器。
- 页面尾部出现“景区经营数据台账”和“合计”。
- `100000` 元显示为 `10.00 万元`。
- 切换年份后卡片和台账不再包含另一年份数据。
- 合计占用天数按 `sum(occupation_weight) / sum(occupation_amount)`，不是景区天数平均值。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; npm test -- --run src/views/operation/index.test.js`  
Expected: FAIL，当前没有尾部台账且卡片不随筛选变化。

- [ ] **Step 3: 建立筛选汇总计算**

~~~javascript
function aggregatePoints(points) {
  const summary = {
    existing_scale: 0,
    total_realized_scale: 0,
    total_gross_income: 0,
    occupation_weight: 0,
    occupation_amount: 0
  }
  for (const point of points) {
    summary.existing_scale += Number(point.existing_scale || 0)
    summary.total_realized_scale += Number(point.realized_amount || 0)
    summary.total_gross_income += Number(point.service_fee || 0)
    summary.occupation_weight += Number(point.occupation_weight || 0)
    summary.occupation_amount += Number(point.occupation_amount || 0)
  }
  summary.capital_occupation_days = summary.occupation_amount > 0
    ? Math.round(summary.occupation_weight / summary.occupation_amount * 10) / 10
    : null
  return summary
}
~~~

`kpiCards` 改为读取 `sharedFilteredPoints` 的聚合结果，而不是未筛选的顶层总计。

- [ ] **Step 4: 新增景区台账和合计行**

以 `scenicSpots` 中全部景区为基础，并合并 API 返回的未知景区 ID；当前有景区筛选时只保留选中项。每景区调用相同 `aggregatePoints`。表尾使用 `show-summary=false` 的显式合计行，以便占用天数按权重计算。

- [ ] **Step 5: 图表切换为万元数据**

柱状图 series 和环形图 data 在进入 ECharts 前调用 `yuanToWan`。坐标轴名称改为“服务费（万元）”，tooltip 使用 `formatWanValue`，避免二次除以 10000。保留现有 `type: 'bar'` 和 `type: 'pie'`。

- [ ] **Step 6: 运行经营页面测试**

Run: `cd frontend; npm test -- --run src/utils/money.test.js src/views/operation/index.test.js`  
Expected: PASS。

---

### Task 9: 战略总览全部金额按万元展示

**Files:**
- Modify: `frontend/src/components/screen/DataScreen.vue:193`
- Modify: `frontend/src/components/screen/ScreenMap.vue:79`
- Modify: `frontend/src/components/screen/DataScreen.test.js`

**Interfaces:**
- Consumes: Task 1 金额工具。
- Preserves: 地图视觉强度仍使用原始元值，避免数值单位改变造成比例逻辑漂移。
- Produces: 指标卡、全国/区域切换和地图 tooltip 的万元文案。

- [ ] **Step 1: 写战略总览失败测试**

扩展 `CountTo` stub 记录 `value`，mock 返回 `total_realized_scale: 123456`、`total_gross_income: 45678`，断言传入 CountTo 的值分别为 `12.3456` 和 `4.5678`，页面单位为“人民币 · 万元”。

为 `ScreenMap` 导出或抽取可测试 formatter，断言 `100000` 元显示为 `¥10.00 万元`。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; npm test -- --run src/components/screen/DataScreen.test.js`  
Expected: FAIL，当前 CountTo 仍接收元值且单位显示“元”。

- [ ] **Step 3: 修改指标卡与区域指标**

`provinceMetrics` 保持原始元值用于地图比例。`metricCards` 在交给 `CountTo` 前调用 `yuanToWan`；单位文案改为“人民币 · 万元”。

- [ ] **Step 4: 修改地图提示**

`ScreenMap.money` 使用 `formatWanFromYuan`。地图 `value`、`maximumRevenue`、symbolSize 和飞线宽度继续使用原始元值，只修改人类可见 tooltip。

- [ ] **Step 5: 运行战略总览测试**

Run: `cd frontend; npm test -- --run src/utils/money.test.js src/components/screen/DataScreen.test.js`  
Expected: PASS。

---

### Task 10: 文档、针对性回归与完整验证

**Files:**
- Modify: `README.md`
- Verify: 本计划全部文件。

**Interfaces:**
- Produces: 清晰的迁移执行顺序和功能说明。
- Verifies: 资金、酒店配置、经营聚合、万元展示以及景区台账单位边界。

- [ ] **Step 1: 更新 README**

在变更记录增加：
- 资金管理流水、自动余额和 30 天预警。
- 经营数据中心尾部景区台账，保留 KPI/柱状图/环形图。
- 景区配置新增独立酒店页签。
- 资金管理、经营数据中心、战略总览使用万元。
- 酒店台账平台列只显示抖音、美团、携程。

在迁移列表追加并按顺序说明：

~~~text
mysql -u root -p sd_publish_scm < backend/migrations/20260828_fund_management.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260828_hotel_config.sql
~~~

- [ ] **Step 2: 运行后端针对性测试**

Run:

~~~powershell
cd backend
..\.venv\Scripts\python.exe -m unittest tests.test_fund_management tests.test_fund_api tests.test_scenic_config tests.test_hotel_scenic_config tests.test_hotel_brand_platform_parser tests.test_scenic_analytics tests.test_financial_ledger_metrics -v
~~~

Expected: PASS。

- [ ] **Step 3: 运行前端针对性测试**

Run:

~~~powershell
cd frontend
npm test -- --run src/utils/money.test.js src/views/finance/fund.test.js src/utils/hotelLedgerDraft.test.js src/components/ScenicConfigDialog.test.js src/views/operation/index.test.js src/components/screen/DataScreen.test.js
~~~

Expected: PASS。

- [ ] **Step 4: 运行完整前端测试与构建**

Run:

~~~powershell
cd frontend
npm test -- --run
npm run build
~~~

Expected: 全部测试 PASS，Vite 构建成功。

- [ ] **Step 5: 运行后端完整测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`  
Expected: 全部测试 PASS；若出现与本次文件无关的既有失败，记录失败用例和原因，不修改无关模块。

- [ ] **Step 6: 检查差异质量与范围**

Run:

~~~powershell
git diff --check
git status --short
git diff -- backend/app/models/fund.py backend/app/schemas/fund.py backend/app/services/fund.py backend/app/api/v1/endpoints/fund.py backend/app/models/scenic_config.py backend/app/schemas/scenic_config.py backend/app/services/scenic_config.py backend/app/api/v1/endpoints/scenic.py backend/app/api/v1/endpoints/hotel_ledger.py backend/app/services/scenic_analytics.py backend/app/schemas/financial.py frontend/src/views/finance/fund.vue frontend/src/components/ScenicConfigDialog.vue frontend/src/components/HotelLedger.vue frontend/src/views/operation/index.vue frontend/src/components/screen/DataScreen.vue frontend/src/components/screen/ScreenMap.vue
~~~

Expected: `git diff --check` 无输出；差异只覆盖本计划范围；用户已有改动未被覆盖。

- [ ] **Step 7: 手工验收清单**

1. 资金增加 100 万元、使用 30 万元后，可使用资金显示 70 万元。
2. 授信到期日在第 30 天显示预警，第 31 天不显示，逾期显示危险状态。
3. 结清授信后预警消失，余额不自动变化；新增还本付息流水后余额下降。
4. 经营数据中心顶部四卡、柱状图、环形图均存在，尾部有每景区和合计台账。
5. 切换年份或景区后，四卡、两张图和台账同步变化。
6. 经营数据中心和战略总览金额显示万元。
7. 门票、酒店、景区原始核销台账仍显示元。
8. 景区配置有门票和酒店两个页签，酒店新解析使用独立参数。
9. 酒店台账平台列只显示抖音、美团、携程，酒店名称独立显示。
