# 资金到期每日登录提醒实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有资金管理 30 天到期口径上增加按用户、按日、按事项和预警阶段去重的站内登录提醒，同时确保提醒失败不阻断登录和正常导航。

**Architecture:** 后端继续以 `maturity_state()` 作为唯一预警状态口径，新建 `FundAlertReceipt` 记录弹窗已经展示的事项；查询接口只返回当前用户当天尚未展示的“即将到期/已逾期”事项，确认接口在弹窗实际显示后批量写入回执。前端用独立 Pinia store 管理一次登录会话内的加载、展示和确认状态，由路由守卫在门户权限加载完成后异步触发，根组件 `App.vue` 挂载全局提醒弹窗，使用户停留在统一门户或进入供管应用时都能看到提醒。

**Tech Stack:** SQLAlchemy、Pydantic、FastAPI、MySQL guarded SQL migration、Vue 3、Pinia、Element Plus、Python unittest、Vitest。

## Global Constraints

- 现有资金管理页面的 30 天预警继续保留，`maturity_state()` 是页面和登录提醒共用的唯一状态函数。
- 仅 `bank_credit`、`company_loan` 且 `settlement_status == "open"` 的记录参与提醒。
- 到期日当天及提前 30 天属于 `due_soon`；提前 31 天不提醒；到期日之后属于 `overdue`。
- 拥有 `supply.finance.view` 权限的用户接收提醒，超级管理员沿用现有权限守卫的放行规则。
- 同一用户、同一自然日、同一资金事项、同一提醒阶段只展示一次；次日仍未结清则继续提醒。
- 事项从 `due_soon` 转为 `overdue` 后使用新的提醒阶段；结清后立即从待提醒列表移除。
- 只提供站内提醒，不接入钉钉、短信、邮件或外部推送。
- 提醒查询或回执失败只能静默保留重试能力，不得注销用户、阻断登录或阻断路由导航。

---

### Task 1: 建立资金提醒回执模型与可重复迁移

**Files:**
- Create: `backend/app/models/fund_alert.py`
- Create: `backend/migrations/20261010_fund_alert_receipts.sql`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/init_db.py`
- Create: `backend/tests/test_fund_alert_models.py`

**Interfaces:**
- Produces: `FundAlertReceipt(user_id: int, fund_id: int, alert_date: date, stage: str, shown_at: datetime)`。
- Produces: 唯一约束 `uq_fund_alert_receipt_daily_stage(user_id, fund_id, alert_date, stage)`。
- Produces: `fund_id -> biz_fund_transaction.id ON DELETE CASCADE` 与 `user_id -> sys_user.id ON DELETE CASCADE`。

- [ ] **Step 1: 编写模型与迁移失败测试**

```python
class FundAlertReceiptModelTest(unittest.TestCase):
    def test_daily_stage_receipt_has_expected_unique_key_and_cascades(self):
        constraint = next(
            item for item in FundAlertReceipt.__table__.constraints
            if item.name == "uq_fund_alert_receipt_daily_stage"
        )
        self.assertEqual(
            [column.name for column in constraint.columns],
            ["user_id", "fund_id", "alert_date", "stage"],
        )
        foreign_keys = {
            foreign_key.parent.name: (foreign_key.target_fullname, foreign_key.ondelete)
            for foreign_key in FundAlertReceipt.__table__.foreign_keys
        }
        self.assertEqual(foreign_keys["fund_id"], ("biz_fund_transaction.id", "CASCADE"))
        self.assertEqual(foreign_keys["user_id"], ("sys_user.id", "CASCADE"))

    def test_mysql_migration_is_repeatable_and_matches_model(self):
        source = Path("migrations/20261010_fund_alert_receipts.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS `biz_fund_alert_receipt`", source)
        self.assertIn("UNIQUE KEY `uq_fund_alert_receipt_daily_stage`", source)
        self.assertIn("FOREIGN KEY (`fund_id`) REFERENCES `biz_fund_transaction` (`id`) ON DELETE CASCADE", source)
        self.assertIn("FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE", source)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python -m unittest tests.test_fund_alert_models -v`

Expected: FAIL，提示 `app.models.fund_alert` 或 `FundAlertReceipt` 不存在。

- [ ] **Step 3: 实现 ORM 模型并注册元数据**

```python
class FundAlertReceipt(Base):
    __tablename__ = "biz_fund_alert_receipt"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "fund_id", "alert_date", "stage",
            name="uq_fund_alert_receipt_daily_stage",
        ),
        Index("ix_fund_alert_receipt_lookup", "user_id", "alert_date", "stage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("biz_fund_transaction.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    shown_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
```

在 `app/models/__init__.py` 和 `app/db/init_db.py` 显式导入 `FundAlertReceipt`，保证 SQLite `create_all`、开发初始化和测试均能发现该表。

- [ ] **Step 4: 编写可重复 MySQL 迁移**

```sql
CREATE TABLE IF NOT EXISTS `biz_fund_alert_receipt` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `fund_id` INT NOT NULL,
  `alert_date` DATE NOT NULL,
  `stage` VARCHAR(16) NOT NULL,
  `shown_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fund_alert_receipt_daily_stage` (`user_id`, `fund_id`, `alert_date`, `stage`),
  KEY `ix_fund_alert_receipt_lookup` (`user_id`, `alert_date`, `stage`),
  KEY `ix_biz_fund_alert_receipt_fund_id` (`fund_id`),
  CONSTRAINT `fk_fund_alert_receipt_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_fund_alert_receipt_fund` FOREIGN KEY (`fund_id`) REFERENCES `biz_fund_transaction` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

该迁移只创建新表，不修改历史资金流水；`CREATE TABLE IF NOT EXISTS` 使生产环境重复执行安全。

- [ ] **Step 5: 运行模型测试并提交**

Run: `cd backend; python -m unittest tests.test_fund_alert_models tests.test_init_db -v`

Expected: PASS，元数据包含 `biz_fund_alert_receipt`，迁移文本与 ORM 主键、列、唯一约束和外键一致。

```bash
git add -- backend/app/models/fund_alert.py backend/app/models/__init__.py backend/app/db/init_db.py backend/migrations/20261010_fund_alert_receipts.sql backend/tests/test_fund_alert_models.py
git commit -m "feat: add daily fund alert receipts"
```

### Task 2: 实现当天提醒查询与展示回执接口

**Files:**
- Modify: `backend/app/schemas/fund.py`
- Modify: `backend/app/services/fund.py`
- Modify: `backend/app/api/v1/endpoints/fund.py`
- Create: `backend/tests/test_fund_alert_api.py`
- Modify: `backend/tests/test_fund_api.py`

**Interfaces:**
- Produces: `FundAlertItem(id, category, counterparty, summary, amount, maturity_date, days_remaining, stage)`。
- Produces: `FundAlertToday(alert_date, items)`。
- Produces: `FundAlertReceiptItem(fund_id, stage)` 和 `FundAlertAcknowledgeIn(items)`。
- Produces: `build_fund_alert_item(row, today) -> FundAlertItem | None`。
- Produces: `list_today_alerts(db, user_id: int, today: date) -> FundAlertToday`。
- Produces: `acknowledge_alert_receipts(db, user_id: int, items: list[FundAlertReceiptItem], today: date) -> int`。
- Produces: `GET /funds/alerts/today -> Response[FundAlertToday]`。
- Produces: `POST /funds/alerts/today/acknowledge -> Response[dict]`，返回 `{"acknowledged": int}`。
- Consumes: Task 1 的 `FundAlertReceipt` 与现有 `_view_guard`。

- [ ] **Step 1: 编写预警边界与权限失败测试**

```python
def test_alert_builder_includes_day_30_and_overdue_but_not_day_31_or_settled(self):
    today = date(2026, 10, 10)
    self.assertEqual(build_fund_alert_item(self.fund(today + timedelta(days=30)), today).stage, "due_soon")
    self.assertIsNone(build_fund_alert_item(self.fund(today + timedelta(days=31)), today))
    self.assertEqual(build_fund_alert_item(self.fund(today - timedelta(days=1)), today).stage, "overdue")
    self.assertIsNone(build_fund_alert_item(self.fund(today, settlement_status="settled"), today))

def test_alert_routes_require_fund_view_permission(self):
    self.app.dependency_overrides[_view_guard] = deny_view
    self.assertEqual(self.client.get("/api/v1/funds/alerts/today").status_code, 403)
    self.assertEqual(
        self.client.post("/api/v1/funds/alerts/today/acknowledge", json={"items": []}).status_code,
        403,
    )
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `cd backend; python -m unittest tests.test_fund_alert_api -v`

Expected: FAIL，提示提醒 schemas、服务函数和路由尚不存在。

- [ ] **Step 3: 增加严格的提醒 schemas 与纯函数**

```python
class FundAlertItem(BaseModel):
    id: int
    category: str
    counterparty: str = ""
    summary: str = ""
    amount: Decimal
    maturity_date: date
    days_remaining: int
    stage: Literal["due_soon", "overdue"]


class FundAlertToday(BaseModel):
    alert_date: date
    items: list[FundAlertItem] = []


class FundAlertReceiptItem(BaseModel):
    fund_id: int = Field(gt=0)
    stage: Literal["due_soon", "overdue"]


class FundAlertAcknowledgeIn(BaseModel):
    items: list[FundAlertReceiptItem] = Field(default_factory=list, max_length=200)
```

```python
def build_fund_alert_item(row, today: date) -> FundAlertItem | None:
    stage = maturity_state(row, today)
    if stage not in {"due_soon", "overdue"}:
        return None
    return FundAlertItem(
        id=row.id,
        category=row.category,
        counterparty=row.counterparty or "",
        summary=row.summary or "",
        amount=Decimal(row.amount),
        maturity_date=row.maturity_date,
        days_remaining=(row.maturity_date - today).days,
        stage=stage,
    )
```

禁止在新服务中复制 30 天判断；所有边界必须通过现有 `maturity_state()` 得出。

- [ ] **Step 4: 实现当天未展示提醒查询**

```python
@router.get("/alerts/today", response_model=Response[FundAlertToday])
def today_fund_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(_view_guard),
):
    today = date.today()
    rows = db.scalars(
        select(FundTransaction)
        .where(
            FundTransaction.category.in_(DUE_CATEGORIES),
            FundTransaction.settlement_status == "open",
            FundTransaction.maturity_date <= today + timedelta(days=30),
        )
        .order_by(FundTransaction.maturity_date.asc(), FundTransaction.id.asc())
    ).all()
    receipts = db.execute(
        select(FundAlertReceipt.fund_id, FundAlertReceipt.stage).where(
            FundAlertReceipt.user_id == current_user.id,
            FundAlertReceipt.alert_date == today,
        )
    ).all()
    shown = {(fund_id, stage) for fund_id, stage in receipts}
    items = [item for row in rows if (item := build_fund_alert_item(row, today))]
    return Response.ok(FundAlertToday(
        alert_date=today,
        items=[item for item in items if (item.id, item.stage) not in shown],
    ))
```

查询必须在 SQL 层先限制类别、未结清和到期上界；服务函数负责最终状态判断，避免提前 31 天和已结清记录漏入。

- [ ] **Step 5: 实现幂等展示回执写入**

确认接口以服务器 `date.today()` 为准，不接受客户端日期。对请求中的每个 `(fund_id, stage)`：锁定资金记录、重新计算当前阶段、丢弃不存在/已结清/阶段不匹配的条目；有效条目用唯一键查询后再新增。并发下若唯一约束冲突，回滚该保存点后视为已存在，不返回 500。

```python
@router.post("/alerts/today/acknowledge", response_model=Response[dict])
def acknowledge_fund_alerts(
    payload: FundAlertAcknowledgeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_view_guard),
):
    acknowledged = acknowledge_alert_receipts(
        db, user_id=current_user.id, items=payload.items, today=date.today()
    )
    db.commit()
    return Response.ok({"acknowledged": acknowledged})
```

- [ ] **Step 6: 覆盖每日、阶段变化与结清场景**

```python
def test_receipt_hides_same_stage_same_day_but_reappears_next_day(self):
    first = list_today_alerts(self.db, self.user.id, date(2026, 10, 10))
    acknowledge_alert_receipts(self.db, self.user.id, first.items, date(2026, 10, 10))
    self.assertEqual(list_today_alerts(self.db, self.user.id, date(2026, 10, 10)).items, [])
    self.assertEqual(len(list_today_alerts(self.db, self.user.id, date(2026, 10, 11)).items), 1)

def test_overdue_stage_can_be_shown_after_due_soon_receipt(self):
    acknowledge_alert_receipts(
        self.db, self.user.id,
        [FundAlertReceiptItem(fund_id=self.row.id, stage="due_soon")],
        date(2026, 10, 10),
    )
    self.row.maturity_date = date(2026, 10, 9)
    self.assertEqual(
        list_today_alerts(self.db, self.user.id, date(2026, 10, 10)).items[0].stage,
        "overdue",
    )
```

同时断言：不同用户相互独立；同批重复条目只写一条；确认后结清立即不再返回；新进入 30 天范围且当天无回执的事项仍可在下一次登录返回。

- [ ] **Step 7: 运行后端回归并提交**

Run: `cd backend; python -m unittest tests.test_fund_alert_api tests.test_fund_api tests.test_fund_management -v`

Expected: PASS；原 `/funds`、`/funds/summary`、`/{fund_id}/settle` 行为不变，新接口均受 `supply.finance.view` 保护。

```bash
git add -- backend/app/schemas/fund.py backend/app/services/fund.py backend/app/api/v1/endpoints/fund.py backend/tests/test_fund_alert_api.py backend/tests/test_fund_api.py
git commit -m "feat: expose daily fund maturity alerts"
```

### Task 3: 增加前端提醒 store、API 与全局弹窗

**Files:**
- Modify: `frontend/src/api/fund.js`
- Create: `frontend/src/store/fundAlerts.js`
- Create: `frontend/src/store/fundAlerts.test.js`
- Create: `frontend/src/components/FundDueAlertModal.vue`
- Create: `frontend/src/components/FundDueAlertModal.test.js`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/App.test.js`
- Modify: `frontend/src/views/finance/fund.vue`
- Modify: `frontend/src/store/user.js`
- Modify: `frontend/src/store/user.test.js`

**Interfaces:**
- Produces: `getTodayFundAlerts()` 与 `acknowledgeTodayFundAlerts(items)`。
- Produces: `useFundAlertStore()`，公开 `items`、`visible`、`loading`、`loadForLogin()`、`acknowledgeShown()`、`reset()`。
- Produces: `FundDueAlertModal` 的“进入资金管理”跳转 `/supplymanagement/finance/fund?maturity_status=<stage>`。
- Produces: `fund.vue` 从 `route.query.maturity_status` 初始化 `filters.maturity_status`，并在 query 变化时重新加载列表。
- Consumes: Task 2 的 `GET /funds/alerts/today` 和确认接口。

- [ ] **Step 1: 编写 store 并发去重与非阻塞失败测试**

```javascript
it('deduplicates simultaneous loads and opens only for returned items', async () => {
  fundApi.getTodayFundAlerts.mockResolvedValue({
    alert_date: '2026-10-10',
    items: [{ id: 7, stage: 'due_soon', amount: 100000, maturity_date: '2026-11-09' }]
  })
  const store = useFundAlertStore()
  await Promise.all([store.loadForLogin(), store.loadForLogin()])
  expect(fundApi.getTodayFundAlerts).toHaveBeenCalledTimes(1)
  expect(store.visible).toBe(true)
})

it('keeps login usable when alert loading fails', async () => {
  fundApi.getTodayFundAlerts.mockRejectedValue(new Error('offline'))
  const store = useFundAlertStore()
  await expect(store.loadForLogin()).resolves.toBeUndefined()
  expect(store.visible).toBe(false)
})
```

- [ ] **Step 2: 运行前端测试确认失败**

Run: `cd frontend; npm test -- src/store/fundAlerts.test.js src/components/FundDueAlertModal.test.js`

Expected: FAIL，提醒 store、组件和 API 方法尚不存在。

- [ ] **Step 3: 实现 API 与每次登录只加载一次的 store**

```javascript
export function getTodayFundAlerts() {
  return request.get('/funds/alerts/today')
}

export function acknowledgeTodayFundAlerts(items) {
  return request.post('/funds/alerts/today/acknowledge', { items })
}
```

```javascript
export const useFundAlertStore = defineStore('fundAlerts', () => {
  const items = ref([])
  const visible = ref(false)
  const loading = ref(false)
  let loadedForSession = false
  let inFlight = null

  function loadForLogin() {
    if (loadedForSession) return Promise.resolve()
    if (inFlight) return inFlight
    loading.value = true
    inFlight = getTodayFundAlerts()
      .then((result) => {
        loadedForSession = true
        items.value = result?.items || []
        visible.value = items.value.length > 0
      })
      .catch(() => undefined)
      .finally(() => {
        loading.value = false
        inFlight = null
      })
    return inFlight
  }

  async function acknowledgeShown() {
    const shown = items.value.map(item => ({ fund_id: item.id, stage: item.stage }))
    if (shown.length) await acknowledgeTodayFundAlerts(shown)
  }

  function reset() {
    loadedForSession = false
    inFlight = null
    items.value = []
    visible.value = false
    loading.value = false
  }

  return { items, visible, loading, loadForLogin, acknowledgeShown, reset }
})
```

`acknowledgeShown()` 的错误由组件捕获且不阻塞关闭；回执失败时后端不会记录，用户下次登录可重新看到，避免静默丢失提醒。

- [ ] **Step 4: 实现汇总弹窗与资金页深链**

弹窗按“已逾期”在前、“即将到期”在后排列，显示类型、对方单位、摘要、金额、到期日和“逾期 N 天/剩余 N 天”。弹窗首次变为可见后调用 `acknowledgeShown()`；关闭不修改资金数据。

```javascript
async function goToFunds(stage) {
  alertStore.visible = false
  await router.push({
    path: '/supplymanagement/finance/fund',
    query: { maturity_status: stage }
  })
}
```

`fund.vue` 已有 `maturity_status` 筛选，组件测试必须断言跳转 query 分别为 `overdue` 或 `due_soon`，而不是新增第二套筛选状态。

- [ ] **Step 5: 挂载全局弹窗并在退出时重置**

```vue
<template>
  <el-config-provider :locale="zhCn">
    <FundDueAlertModal />
    <router-view />
  </el-config-provider>
</template>
```

在 `useUserStore().logout()` 内、清理 token 前调用 `useFundAlertStore().reset()`，确保同一浏览器切换用户后不会继承上一用户的加载标记或提醒内容。`fund.vue` 使用 `useRoute()` 读取 query，且只接受 `due_soon`、`overdue`、`normal`、`settled`：

```javascript
const route = useRoute()
const maturityStatuses = new Set(['due_soon', 'overdue', 'normal', 'settled'])
const routeMaturityStatus = () => (
  maturityStatuses.has(String(route.query.maturity_status || ''))
    ? String(route.query.maturity_status)
    : ''
)

const filters = reactive({
  direction: '',
  category: '',
  settlement_status: '',
  maturity_status: routeMaturityStatus(),
  dateRange: [],
  keyword: '',
  page: 1,
  page_size: 20
})

watch(
  () => route.query.maturity_status,
  async () => {
    const nextStatus = routeMaturityStatus()
    if (nextStatus === filters.maturity_status) return
    filters.maturity_status = nextStatus
    filters.page = 1
    await loadLedger()
  }
)
```

首次挂载仍只执行现有的一次 `loadLedger()`，不得因 query 初始化额外请求第二次。

`App.test.js` 验证根组件始终挂载提醒组件而不替换路由出口：

```javascript
it('mounts the global fund alert modal beside the router view', () => {
  const wrapper = shallowMount(App, {
    global: {
      stubs: {
        ElConfigProvider: { template: '<div><slot /></div>' },
        RouterView: true,
        FundDueAlertModal: true
      }
    }
  })
  expect(wrapper.findComponent({ name: 'FundDueAlertModal' }).exists()).toBe(true)
  expect(wrapper.findComponent({ name: 'RouterView' }).exists()).toBe(true)
})
```

- [ ] **Step 6: 运行组件和 store 测试并提交**

Run: `cd frontend; npm test -- src/store/fundAlerts.test.js src/components/FundDueAlertModal.test.js src/App.test.js src/store/user.test.js src/views/finance/fund.test.js`

Expected: PASS；空列表不打开弹窗，失败不抛出到登录流程，退出登录清空提醒状态，深链使用现有资金状态筛选。

```bash
git add -- frontend/src/api/fund.js frontend/src/store/fundAlerts.js frontend/src/store/fundAlerts.test.js frontend/src/components/FundDueAlertModal.vue frontend/src/components/FundDueAlertModal.test.js frontend/src/App.vue frontend/src/App.test.js frontend/src/views/finance/fund.vue frontend/src/store/user.js frontend/src/store/user.test.js
git commit -m "feat: show fund alerts after login"
```

### Task 4: 在权限加载后异步触发提醒

**Files:**
- Modify: `frontend/src/permission.js`
- Modify: `frontend/src/permission.test.js`

**Interfaces:**
- Consumes: Task 3 的 `useFundAlertStore().loadForLogin()`。
- Consumes: `portalStore.hasPermission("supply.finance.view")`。
- Produces: `triggerFundAlerts(portalStore)`，只负责授权判断和 fire-and-forget 调度。

- [ ] **Step 1: 编写权限时序与导航非阻塞失败测试**

```javascript
it('loads fund alerts only after portal permissions and only for viewers', async () => {
  const { portalStore } = authenticatedContext({
    permissions: [{ code: 'supply.finance.view' }]
  })
  const loadPortal = vi.spyOn(portalStore, 'loadPortalContext').mockResolvedValue()
  const alertStore = useFundAlertStore()
  const loadAlerts = vi.spyOn(alertStore, 'loadForLogin').mockResolvedValue()

  await expect(portalGuard(route('/'))).resolves.toBe(true)
  expect(loadPortal.mock.invocationCallOrder[0]).toBeLessThan(loadAlerts.mock.invocationCallOrder[0])
})

it('does not block navigation when the alert request rejects', async () => {
  authenticatedContext({ permissions: [{ code: 'supply.finance.view' }] })
  vi.spyOn(useFundAlertStore(), 'loadForLogin').mockRejectedValue(new Error('offline'))
  await expect(portalGuard(route('/'))).resolves.toBe(true)
})
```

- [ ] **Step 2: 运行权限测试确认失败**

Run: `cd frontend; npm test -- src/permission.test.js`

Expected: FAIL，路由守卫尚未调度资金提醒。

- [ ] **Step 3: 实现授权后的非阻塞调度**

```javascript
export function triggerFundAlerts(portalStore) {
  if (!portalStore.hasPermission('supply.finance.view')) return
  void useFundAlertStore().loadForLogin().catch(() => undefined)
}
```

在 `await portalStore.loadPortalContext()` 成功之后调用 `triggerFundAlerts(portalStore)`；不要 `await` 提醒请求。公司、资源、角色和超级管理员路由校验保持原顺序，提醒失败不得进入现有 `logout()` 分支。

- [ ] **Step 4: 覆盖无权限、重复导航和超级管理员**

测试断言：无 `supply.finance.view` 权限不调用 API；同一登录会话多次导航由 store 去重；超级管理员即使权限数组为空也通过 `hasPermission()` 触发；刷新后后端回执阻止同日重复弹窗。

Run: `cd frontend; npm test -- src/permission.test.js src/store/portal.test.js src/store/fundAlerts.test.js`

Expected: PASS，现有门户权限和法务路由守卫测试不变。

- [ ] **Step 5: 提交权限时序集成**

```bash
git add -- frontend/src/permission.js frontend/src/permission.test.js
git commit -m "feat: trigger fund reminders after permission load"
```

### Task 5: 完成资金提醒集成回归

**Files:**
- Verify: `backend/app/models/fund_alert.py`
- Verify: `backend/app/api/v1/endpoints/fund.py`
- Verify: `frontend/src/components/FundDueAlertModal.vue`
- Verify: `frontend/src/permission.js`

**Interfaces:**
- Verifies: 数据库唯一键、接口权限、前端登录时序和资金管理深链构成完整提醒闭环。

- [ ] **Step 1: 运行后端资金专项测试**

Run: `cd backend; python -m unittest tests.test_fund_alert_models tests.test_fund_alert_api tests.test_fund_api tests.test_fund_management -v`

Expected: PASS。

- [ ] **Step 2: 运行前端资金与权限专项测试**

Run: `cd frontend; npm test -- src/store/fundAlerts.test.js src/components/FundDueAlertModal.test.js src/permission.test.js src/store/user.test.js src/views/finance/fund.test.js`

Expected: PASS。

- [ ] **Step 3: 运行前端构建**

Run: `cd frontend; npm run build`

Expected: PASS，并生成 `frontend/dist`。

- [ ] **Step 4: 验证生产迁移可重复执行**

在与生产同版本的 MySQL 8 测试库连续执行两次 `backend/migrations/20261010_fund_alert_receipts.sql`；第一次创建表，第二次无重复表、索引或外键错误。随后验证删除资金流水和删除用户均能级联删除对应回执。

- [ ] **Step 5: 完成人工端到端验收**

使用固定测试日期准备提前 31 天、提前 30 天、当天到期、逾期和已结清五笔资金记录，依次验证：有查看权限用户仅看到后三种未结清预警；当天二次登录不重复；次日再次提醒；结清后消失；点击事项进入带状态筛选的资金管理页；无权限用户不请求提醒接口；模拟提醒接口 500 时仍能正常进入系统。

- [ ] **Step 6: 提交集成回归记录**

```bash
git add -- backend frontend
git commit -m "test: verify daily fund maturity reminders"
```

提交前运行 `git diff --check`，并确认暂存区不含用户已有的无关改动。
