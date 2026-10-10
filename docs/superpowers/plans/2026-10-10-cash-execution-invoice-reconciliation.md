# 资金执行、发票核销与集中待办实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将审批授权、实际收付款和发票核销拆成可审计的三个阶段，并集中展示未执行、待补票和未核销异常。

**Architecture:** `CashExecutionTask` 表示已经审批但尚未全部发生的资金事项，`FundTransaction` 只表示真实银行收付款，`InvoiceFundAllocation` 负责多对多金额核销。集中待办不复制业务数据，而由 `work_items` 服务按权限实时聚合各模块未完成状态。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、MySQL/SQLite、Vue 3、Pinia、Element Plus、Python unittest、Vitest。

## Global Constraints

- 付款审批通过不能直接新增资金流水。
- 财务可分次执行，累计执行金额不得超过审批或应收金额。
- 多张发票可合并收付款，一张发票可分次收付款。
- 进项发票只核销支出流水，销项发票只核销收入流水。
- 允许预付款，未补票金额持续进入待处理事项。
- 合同金额超额首期仅预警，不强制拦截。
- 新闭环上线后的业务收付款必须从待执行任务创建；历史流水允许人工补关联。

---

### Task 1: 建立资金执行与核销模型

**Files:**
- Create: `backend/migrations/20261010_cash_execution_reconciliation.sql`
- Create: `backend/app/models/cash_execution.py`
- Modify: `backend/app/models/fund.py`
- Modify: `backend/app/models/invoice.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/init_db.py`
- Create: `backend/tests/test_cash_execution_models.py`
- Modify: `backend/tests/test_invoice_models.py`

**Interfaces:**
- Produces: `CashExecutionTask(direction, approval_form_id, invoice_id, contract_id, scenic_id, planned_amount, executed_amount, status)`。
- Produces: `InvoiceFundAllocation(fund_transaction_id, invoice_id, amount, allocated_by)`。
- Produces: `FundTransaction.execution_task_id`, `contract_id`, `approval_form_id`, `invoice_id`, `scenic_id`, `bank_reference`。

- [ ] **Step 1: 编写模型约束失败测试**

```python
def test_payment_task_is_unique_per_approval(self):
    names = {constraint.name for constraint in CashExecutionTask.__table__.constraints}
    self.assertIn("uq_cash_task_approval", names)

def test_invoice_allocation_is_audit_backed(self):
    self.assertTrue({"fund_transaction_id", "invoice_id", "amount", "allocated_by"}.issubset(
        InvoiceFundAllocation.__table__.columns
    ))
```

- [ ] **Step 2: 运行模型测试确认失败**

Run: `cd backend; python -m unittest tests.test_cash_execution_models -v`

Expected: FAIL，新增实体尚不存在。

- [ ] **Step 3: 实现模型和状态常量**

```python
class CashTaskStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CashExecutionTask(Base):
    __tablename__ = "biz_cash_execution_task"
    __table_args__ = (
        UniqueConstraint("approval_form_id", name="uq_cash_task_approval"),
        UniqueConstraint("invoice_id", name="uq_cash_task_invoice"),
        CheckConstraint(
            "(direction = 'outflow' AND approval_form_id IS NOT NULL AND invoice_id IS NULL) OR "
            "(direction = 'inflow' AND invoice_id IS NOT NULL AND approval_form_id IS NULL)",
            name="ck_cash_task_single_source",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    approval_form_id: Mapped[int | None] = mapped_column(ForeignKey("biz_approval_form.id", ondelete="SET NULL"))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("biz_invoice.id", ondelete="SET NULL"))
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("biz_contract.id", ondelete="SET NULL"))
    scenic_id: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    executed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CashTaskStatus.PENDING.value)


class InvoiceFundAllocation(Base):
    __tablename__ = "biz_invoice_fund_allocation"
    id: Mapped[int] = mapped_column(primary_key=True)
    fund_transaction_id: Mapped[int] = mapped_column(ForeignKey("biz_fund_transaction.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("biz_invoice.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    allocated_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
```

付款任务以 `approval_form_id` 唯一；回款任务以 `invoice_id` 唯一。两列均允许空，但增加检查约束，确保付款任务只有审批来源、回款任务只有发票来源。金额统一 `Numeric(18, 2)` 且数据库默认零。

- [ ] **Step 4: 编写幂等迁移并注册模型**

迁移创建 `biz_cash_execution_task`、`biz_invoice_fund_allocation`，并为资金流水增加追溯列。所有 DDL 使用现有 `information_schema` 守卫，外键删除策略以保存历史为目标：任务、合同、审批和发票删除时资金快照使用 `SET NULL`，核销明细随资金或发票删除使用 `CASCADE`；业务接口禁止删除已核销对象。

```sql
CREATE TABLE IF NOT EXISTS `biz_cash_execution_task` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `direction` VARCHAR(16) NOT NULL,
  `approval_form_id` INT NULL,
  `invoice_id` INT NULL,
  `contract_id` INT NULL,
  `scenic_id` VARCHAR(64) NOT NULL,
  `planned_amount` DECIMAL(18,2) NOT NULL,
  `executed_amount` DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  `status` VARCHAR(16) NOT NULL DEFAULT 'pending',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cash_task_approval` (`approval_form_id`),
  UNIQUE KEY `uq_cash_task_invoice` (`invoice_id`),
  CONSTRAINT `ck_cash_task_single_source` CHECK ((`direction`='outflow' AND `approval_form_id` IS NOT NULL AND `invoice_id` IS NULL) OR (`direction`='inflow' AND `invoice_id` IS NOT NULL AND `approval_form_id` IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `biz_invoice_fund_allocation` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `fund_transaction_id` INT NOT NULL,
  `invoice_id` INT NOT NULL,
  `amount` DECIMAL(18,2) NOT NULL,
  `allocated_by` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_invoice_fund_allocation_fund` (`fund_transaction_id`),
  KEY `ix_invoice_fund_allocation_invoice` (`invoice_id`),
  CONSTRAINT `fk_allocation_fund` FOREIGN KEY (`fund_transaction_id`) REFERENCES `biz_fund_transaction` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_allocation_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

资金流水新增列逐列使用 `information_schema.columns` + `PREPARE/EXECUTE` 守卫；索引和外键分别使用 `information_schema.statistics`、`information_schema.table_constraints` 守卫。`app/models/__init__.py` 与 `app/db/init_db.py` 显式导入两个新模型。

- [ ] **Step 5: 回归模型并提交**

Run: `cd backend; python -m unittest tests.test_cash_execution_models tests.test_invoice_models tests.test_init_db -v`

Expected: PASS。

```bash
git add -- backend/migrations/20261010_cash_execution_reconciliation.sql backend/app/models/cash_execution.py backend/app/models/fund.py backend/app/models/invoice.py backend/app/models/__init__.py backend/app/db/init_db.py backend/tests/test_cash_execution_models.py backend/tests/test_invoice_models.py
git commit -m "feat: add cash execution and invoice allocation models"
```

### Task 2: 审批完成后幂等生成待执行任务

**Files:**
- Create: `backend/app/services/cash_execution.py`
- Modify: `backend/app/api/v1/endpoints/approval.py`
- Modify: `backend/app/api/v1/endpoints/invoice.py`
- Create: `backend/tests/test_cash_execution.py`
- Modify: `backend/tests/test_workflow_api.py`
- Modify: `backend/tests/test_invoice_workflow.py`

**Interfaces:**
- Produces: `ensure_payment_task(db: Session, form: ApprovalForm) -> CashExecutionTask | None`。
- Produces: `ensure_receipt_task(db: Session, invoice: Invoice) -> CashExecutionTask | None`。
- Payment task creation condition: `form_type == payment and form.status == approved`。
- Receipt task activation condition: 销项发票审批已完成且至少上传一张发票附件。

- [ ] **Step 1: 编写幂等任务失败测试**

```python
def test_final_payment_approval_creates_task_not_fund_transaction(self):
    task = ensure_payment_task(self.db, approved_form)
    again = ensure_payment_task(self.db, approved_form)
    self.assertEqual(task.id, again.id)
    self.assertEqual(self.db.query(FundTransaction).count(), 0)

def test_output_receipt_task_waits_for_approval_and_attachment(self):
    self.assertIsNone(ensure_receipt_task(self.db, invoice_without_attachment))
```

- [ ] **Step 2: 运行服务测试确认失败**

Run: `cd backend; python -m unittest tests.test_cash_execution -v`

Expected: FAIL，任务服务尚不存在。

- [ ] **Step 3: 实现任务创建服务**

```python
def ensure_payment_task(db, form):
    if form.form_type != ContractType.PAYMENT or form.status != ContractStatus.APPROVED:
        return None
    task = db.scalar(select(CashExecutionTask).where(CashExecutionTask.approval_form_id == form.id))
    if task:
        return task
    task = CashExecutionTask(direction="outflow", approval_form_id=form.id,
        contract_id=form.contract_id, scenic_id=form.scenic_id,
        planned_amount=money(form.amount), executed_amount=Decimal("0"), status="pending")
    db.add(task)
    db.flush()
    return task
```

`ensure_receipt_task` 同样幂等，计划金额取销项发票金额。任务创建必须位于最终审批或附件上传现有事务中，不另行提交。

- [ ] **Step 4: 将服务接入最终状态变更**

在 `complete_task` 返回后检查持久化对象的新状态并调用任务服务；发票附件上传后再次调用 `ensure_receipt_task`。数据库唯一约束负责并发兜底，捕获重复键后重新读取既有任务。

```python
workflow_result = complete_task(db, task_id=task_id, actor=current_user, action=payload.action)
db.flush()
if form.status == ContractStatus.APPROVED:
    ensure_payment_task(db, form)
db.commit()


attachment = save_invoice_attachment(db, invoice, upload, current_user.id)
db.flush()
ensure_receipt_task(db, invoice)
db.commit()
```

```python
def _flush_or_reload(db, task, lookup):
    try:
        with db.begin_nested():
            db.add(task)
            db.flush()
        return task
    except IntegrityError:
        return db.scalar(lookup)
```

- [ ] **Step 5: 回归工作流并提交**

Run: `cd backend; python -m unittest tests.test_cash_execution tests.test_workflow_api tests.test_invoice_workflow -v`

Expected: PASS，非最终节点不生成任务，最终节点只生成一次。

```bash
git add -- backend/app/services/cash_execution.py backend/app/api/v1/endpoints/approval.py backend/app/api/v1/endpoints/invoice.py backend/tests/test_cash_execution.py backend/tests/test_workflow_api.py backend/tests/test_invoice_workflow.py
git commit -m "feat: create cash tasks after final approval"
```

### Task 3: 财务执行任务并生成真实资金流水

**Files:**
- Create: `backend/app/schemas/cash_execution.py`
- Modify: `backend/app/services/cash_execution.py`
- Modify: `backend/app/api/v1/endpoints/fund.py`
- Modify: `backend/tests/test_cash_execution.py`
- Modify: `backend/tests/test_fund_api.py`
- Modify: `frontend/src/api/fund.js`
- Modify: `frontend/src/views/finance/fund.vue`
- Modify: `frontend/src/views/finance/fund.test.js`

**Interfaces:**
- Produces: `GET /funds/execution-tasks?status=&direction=`。
- Produces: `POST /funds/execution-tasks/{id}/execute`。
- Request: `CashExecutionIn(amount, occurred_on, counterparty, bank_reference, summary, remark)`。
- Produces: `execute_task(db, task_id, payload, actor_id) -> FundTransaction`。

- [ ] **Step 1: 编写分次执行与超额失败测试**

```python
def test_execute_task_supports_partial_then_complete(self):
    first = execute_task(self.db, task.id, Execution(amount=Decimal("40.00"), ...), actor_id=1)
    self.assertEqual(task.status, "partial")
    second = execute_task(self.db, task.id, Execution(amount=Decimal("60.00"), ...), actor_id=1)
    self.assertEqual(task.status, "completed")
    self.assertEqual(first.direction, "usage")

def test_execute_task_rejects_amount_above_remaining(self):
    with self.assertRaises(CashExecutionError):
        execute_task(self.db, task.id, Execution(amount=Decimal("100.01"), ...), actor_id=1)
```

- [ ] **Step 2: 运行服务测试确认失败**

Run: `cd backend; python -m unittest tests.test_cash_execution -v`

Expected: FAIL，`execute_task` 尚不存在。

- [ ] **Step 3: 实现带行锁的执行事务**

用 `select(...).with_for_update()` 读取任务，计算 `remaining = planned_amount - executed_amount`。金额必须大于零且不超过剩余额。生成资金流水后更新累计金额和状态；所有操作由 endpoint 单次 `commit`。

```python
def execute_task(db, task_id, payload, actor_id):
    task = db.scalar(select(CashExecutionTask).where(CashExecutionTask.id == task_id).with_for_update())
    if not task or task.status in {"completed", "cancelled"}:
        raise CashExecutionError("task_not_executable")
    amount = money(payload.amount)
    remaining = money(task.planned_amount) - money(task.executed_amount)
    if amount <= 0 or amount > remaining:
        raise CashExecutionError("amount_exceeds_remaining")
    fund = FundTransaction(
        direction="usage" if task.direction == "outflow" else "increase",
        category="business_payment" if task.direction == "outflow" else "customer_payment",
        amount=amount,
        occurred_on=payload.occurred_on,
        counterparty=payload.counterparty,
        summary=payload.summary,
        remark=payload.remark,
        bank_reference=payload.bank_reference,
        execution_task_id=task.id,
        contract_id=task.contract_id,
        approval_form_id=task.approval_form_id,
        invoice_id=task.invoice_id,
        scenic_id=task.scenic_id,
        created_by=actor_id,
    )
    task.executed_amount = money(task.executed_amount) + amount
    task.status = "completed" if task.executed_amount == task.planned_amount else "partial"
    db.add(fund)
    db.flush()
    return fund
```

- [ ] **Step 4: 扩展资金管理页面**

新增“资金流水”“待资金执行”两个页签。任务列表显示合同、景区、计划金额、已执行、未执行和状态；财务执行弹窗要求实际日期、金额、对方、银行流水号。历史手工流水显示“历史未关联”标记，新任务流水显示来源审批或发票。

```javascript
const activeTab = ref('ledger')
const executionTasks = ref([])
const executionForm = reactive({ amount: null, occurred_on: todayString(), counterparty: '', bank_reference: '', summary: '', remark: '' })

async function loadExecutionTasks() {
  executionTasks.value = await listCashExecutionTasks({ status: taskFilters.status, direction: taskFilters.direction })
}

async function submitExecution(task) {
  await executeCashTask(task.id, { ...executionForm, amount: wanToYuan(executionForm.amount) })
  await Promise.all([loadExecutionTasks(), loadLedger(), loadSummary()])
}

function taskSource(row) {
  if (!row.execution_task_id) return '历史未关联'
  return row.approval_form_id ? `付款审批 #${row.approval_form_id}` : `销项发票 #${row.invoice_id}`
}
```

- [ ] **Step 5: 运行前后端测试并提交**

Run: `cd backend; python -m unittest tests.test_cash_execution tests.test_fund_api tests.test_fund_management -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/views/finance/fund.test.js`

Expected: PASS。

```bash
git add -- backend/app/schemas/cash_execution.py backend/app/services/cash_execution.py backend/app/api/v1/endpoints/fund.py backend/tests/test_cash_execution.py backend/tests/test_fund_api.py frontend/src/api/fund.js frontend/src/views/finance/fund.vue frontend/src/views/finance/fund.test.js
git commit -m "feat: execute approved cash tasks"
```

### Task 4: 实现发票与资金多对多核销

**Files:**
- Create: `backend/app/services/invoice_reconciliation.py`
- Modify: `backend/app/schemas/invoice.py`
- Modify: `backend/app/api/v1/endpoints/invoice.py`
- Create: `backend/tests/test_invoice_fund_reconciliation.py`
- Modify: `frontend/src/api/invoice.js`
- Modify: `frontend/src/views/invoice/index.vue`
- Modify: `frontend/src/views/invoice/index.test.js`

**Interfaces:**
- Produces: `GET /invoices/{invoice_id}/allocations`。
- Produces: `POST /invoices/{invoice_id}/allocations` with `{fund_transaction_id, amount}`。
- Produces: `DELETE /invoices/{invoice_id}/allocations/{allocation_id}`。
- Produces: `invoice_reconciliation_state(invoice) -> unallocated|partial|allocated`。

- [ ] **Step 1: 编写方向和余额约束失败测试**

```python
def test_input_invoice_only_accepts_usage_funds(self):
    with self.assertRaises(ReconciliationError) as caught:
        allocate(self.db, input_invoice.id, increase_fund.id, Decimal("10"), actor_id=1)
    self.assertEqual(caught.exception.code, "direction_mismatch")

def test_allocation_cannot_exceed_invoice_or_fund_remaining(self):
    with self.assertRaises(ReconciliationError):
        allocate(self.db, invoice.id, fund.id, Decimal("100.01"), actor_id=1)
```

- [ ] **Step 2: 运行核销测试确认失败**

Run: `cd backend; python -m unittest tests.test_invoice_fund_reconciliation -v`

Expected: FAIL，核销服务尚不存在。

- [ ] **Step 3: 实现并发安全核销服务**

同时锁定发票和资金流水，分别汇总现有核销金额，验证方向、合同一致性和剩余额。删除核销明细仅允许资金管理编辑权限，并重新计算双方状态；不修改发票原金额和资金流水原金额。

```python
def allocate(db, invoice_id, fund_id, amount, actor_id):
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
    fund = db.scalar(select(FundTransaction).where(FundTransaction.id == fund_id).with_for_update())
    if not invoice or not fund:
        raise ReconciliationError("source_not_found")
    expected_direction = "usage" if invoice.direction == InvoiceDirection.INPUT else "increase"
    if fund.direction != expected_direction:
        raise ReconciliationError("direction_mismatch")
    if invoice.contract_id and fund.contract_id and invoice.contract_id != fund.contract_id:
        raise ReconciliationError("contract_mismatch")
    value = money(amount)
    invoice_remaining = money(invoice.amount) - allocated_to_invoice(db, invoice.id)
    fund_remaining = money(fund.amount) - allocated_from_fund(db, fund.id)
    if value <= 0 or value > invoice_remaining or value > fund_remaining:
        raise ReconciliationError("allocation_exceeds_remaining")
    allocation = InvoiceFundAllocation(fund_transaction_id=fund.id, invoice_id=invoice.id, amount=value, allocated_by=actor_id)
    db.add(allocation)
    db.flush()
    return allocation
```

- [ ] **Step 4: 更新发票管理核销界面**

列表增加资金状态和未核销金额；操作中增加“收付款核销”，可选择同合同、正确方向且有未分配余额的资金流水，支持多次添加和撤销。进项显示“已付款/未补票”，销项显示“已回款/待回款”。

```javascript
async function openReconciliation(invoice) {
  currentInvoice.value = invoice
  const [allocations, candidates] = await Promise.all([
    listInvoiceAllocations(invoice.id),
    listFunds({ contract_id: invoice.contract_id, direction: invoice.direction === 'input' ? 'usage' : 'increase', unallocated_only: true })
  ])
  reconciliation.value = { allocations, candidates }
  reconciliationVisible.value = true
}

async function addAllocation() {
  await createInvoiceAllocation(currentInvoice.value.id, {
    fund_transaction_id: allocationForm.fund_transaction_id,
    amount: allocationForm.amount
  })
  await openReconciliation(currentInvoice.value)
}
```

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend; python -m unittest tests.test_invoice_fund_reconciliation tests.test_invoice_api -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/views/invoice/index.test.js`

Expected: PASS。

```bash
git add -- backend/app/services/invoice_reconciliation.py backend/app/schemas/invoice.py backend/app/api/v1/endpoints/invoice.py backend/tests/test_invoice_fund_reconciliation.py frontend/src/api/invoice.js frontend/src/views/invoice/index.vue frontend/src/views/invoice/index.test.js
git commit -m "feat: reconcile invoices with cash transactions"
```

### Task 5: 计算预付款、合同金额与集中待处理事项

**Files:**
- Create: `backend/app/schemas/work_item.py`
- Create: `backend/app/services/work_items.py`
- Create: `backend/app/api/v1/endpoints/work_items.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_work_items.py`
- Create: `frontend/src/api/workItems.js`
- Create: `frontend/src/store/workItems.js`
- Create: `frontend/src/views/work-items/index.vue`
- Create: `frontend/src/views/work-items/index.test.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/router/routes.test.js`
- Modify: `frontend/src/layout/index.vue`
- Modify: `frontend/src/layout/index.test.js`
- Modify: `frontend/src/views/contract/index.vue`

**Interfaces:**
- Produces: `GET /work-items -> list[WorkItemOut]`，按当前用户权限过滤。
- Work item types: `missing_contract`, `cash_execution`, `receipt_confirmation`, `input_invoice_missing`, `invoice_unallocated`, `fund_unallocated`, `contract_amount_exceeded`, `fund_due_soon`, `fund_overdue`。
- Produces: `GET /contracts/{id}/closure-summary`。

- [ ] **Step 1: 编写待办聚合失败测试**

```python
def test_prepaid_amount_is_payment_minus_input_allocations(self):
    items = build_work_items(self.db, finance_user)
    item = next(row for row in items if row.item_type == "input_invoice_missing")
    self.assertEqual(item.amount, Decimal("70.00"))

def test_user_without_invoice_permission_cannot_see_invoice_items(self):
    self.assertFalse(any(row.item_type == "invoice_unallocated" for row in build_work_items(self.db, restricted_user)))
```

- [ ] **Step 2: 运行聚合测试确认失败**

Run: `cd backend; python -m unittest tests.test_work_items -v`

Expected: FAIL，聚合服务尚不存在。

- [ ] **Step 3: 实现实时聚合和合同汇总**

`build_work_items` 只返回调用者具有对应查看权限的事项。预付款未补票金额按合同下实际支出减已核销进项发票计算；合同超额分别比较累计已审批付款和累计销项发票金额，合同金额为零时生成“未配置控制金额”提示而非超额。

```python
def build_contract_closure_summary(db, contract_id: int) -> ContractClosureSummary:
    approved = approved_payment_total(db, contract_id)
    pending = pending_execution_total(db, contract_id)
    paid = actual_payment_total(db, contract_id)
    input_allocated = allocated_input_invoice_total(db, contract_id)
    output_invoiced = output_invoice_total(db, contract_id)
    received = actual_receipt_total(db, contract_id)
    return ContractClosureSummary(
        approved_payment=approved,
        pending_payment=pending,
        actual_payment=paid,
        output_invoiced=output_invoiced,
        actual_receipt=received,
        missing_input_invoice=max(paid - input_allocated, Decimal("0")),
    )


def build_work_items(db, current_user):
    items = []
    if has_permission(db, current_user, "supply.scenic.view"):
        items.extend(missing_contract_items(db))
    if has_permission(db, current_user, "supply.finance.view"):
        items.extend(cash_execution_items(db))
        items.extend(unallocated_fund_items(db))
        items.extend(fund_maturity_items(db))
    if has_permission(db, current_user, "supply.invoice.view"):
        items.extend(missing_input_invoice_items(db))
        items.extend(unallocated_invoice_items(db))
    if has_permission(db, current_user, "supply.contract.view"):
        items.extend(contract_control_items(db))
    return sorted(items, key=lambda item: (item.priority, item.due_date or date.max, item.item_type))
```

- [ ] **Step 4: 新增集中待办页面与导航角标**

新增 `/supplymanagement/work-items`，表格列为类型、景区、合同、金额、日期、状态、去处理。Pinia store 每 30 秒刷新数量，布局显示角标；点击事项使用后端提供的 `target_path` 和查询参数跳转原模块。

```javascript
export const useWorkItemsStore = defineStore('workItems', () => {
  const items = ref([])
  const count = computed(() => items.value.length)
  let timer = null
  async function load() { items.value = await getWorkItems() }
  function startPolling() { stopPolling(); void load(); timer = setInterval(load, 30000) }
  function stopPolling() { if (timer) clearInterval(timer); timer = null }
  return { items, count, load, startPolling, stopPolling }
})

async function handleWorkItem(item) {
  await router.push({ path: item.target_path, query: item.target_query || {} })
}
```

```javascript
{
  path: 'work-items',
  name: 'WorkItems',
  component: () => import('@/views/work-items/index.vue'),
  meta: { title: '待处理事项', icon: 'Bell', company: supplyCompany }
}
```

- [ ] **Step 5: 合同页面展示闭环汇总**

合同详情显示已审批付款、待执行付款、实际付款、销项发票、已回款和未补进项发票金额。数据全部来自 `/contracts/{id}/closure-summary`，不在前端重复聚合。

```javascript
const closureSummary = ref(null)

async function openContractDetail(row) {
  currentContract.value = row
  closureSummary.value = await getContractClosureSummary(row.id)
  detailVisible.value = true
}

const closureCards = computed(() => closureSummary.value ? [
  ['已审批付款', closureSummary.value.approved_payment],
  ['待执行付款', closureSummary.value.pending_payment],
  ['实际付款', closureSummary.value.actual_payment],
  ['销项发票', closureSummary.value.output_invoiced],
  ['已回款', closureSummary.value.actual_receipt],
  ['未补进项发票', closureSummary.value.missing_input_invoice]
] : [])
```

- [ ] **Step 6: 运行前后端测试并提交**

Run: `cd backend; python -m unittest tests.test_work_items tests.test_cash_execution tests.test_invoice_fund_reconciliation -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/views/work-items/index.test.js src/router/routes.test.js src/layout/index.test.js`

Expected: PASS。

```bash
git add -- backend/app/schemas/work_item.py backend/app/services/work_items.py backend/app/api/v1/endpoints/work_items.py backend/app/api/v1/router.py backend/tests/test_work_items.py frontend/src/api/workItems.js frontend/src/store/workItems.js frontend/src/views/work-items/index.vue frontend/src/views/work-items/index.test.js frontend/src/router/index.js frontend/src/router/routes.test.js frontend/src/layout/index.vue frontend/src/layout/index.test.js frontend/src/views/contract/index.vue
git commit -m "feat: add supply chain work items"
```

### Task 6: 增加全链路下钻接口

**Files:**
- Create: `backend/app/schemas/business_trace.py`
- Create: `backend/app/services/business_trace.py`
- Modify: `backend/app/api/v1/endpoints/operation.py`
- Create: `backend/tests/test_business_trace.py`
- Modify: `frontend/src/api/operation.js`
- Create: `frontend/src/components/BusinessTraceDrawer.vue`
- Create: `frontend/src/components/BusinessTraceDrawer.test.js`
- Modify: `frontend/src/views/operation/index.vue`

**Interfaces:**
- Produces: `GET /operation/trace?scenic_id=&source_kind=&period_key=`。
- Produces: `BusinessTraceOut(ledger_rows, invoices, allocations, funds, execution_tasks, approvals, contracts)`。

- [ ] **Step 1: 编写追溯链失败测试**

```python
def test_trace_returns_only_one_scenic_period_chain(self):
    trace = build_business_trace(self.db, "scenic-a", InvoiceSourceKind.TICKET, "P1")
    self.assertEqual({row.scenic_id for row in trace.ledger_rows}, {"scenic-a"})
    self.assertEqual(trace.contracts[0].id, self.contract.id)
    self.assertEqual(trace.funds[0].id, self.fund.id)
```

- [ ] **Step 2: 运行追溯测试确认失败**

Run: `cd backend; python -m unittest tests.test_business_trace -v`

Expected: FAIL，追溯服务尚不存在。

- [ ] **Step 3: 实现只读追溯服务和权限交集**

先校验经营数据查看权限，再按各下游模块权限裁剪发票、资金、审批和合同节点；无权查看的节点返回 `restricted_count`，不泄露字段。

```python
def build_business_trace(db, scenic_id, source_kind, period_key, current_user):
    ledger_rows = load_period_rows(db, scenic_id, source_kind, period_key)
    invoices = load_source_invoices(db, scenic_id, source_kind, period_key)
    visible_invoices, invoice_restricted = permission_slice(db, current_user, "supply.invoice.view", invoices)
    allocations = load_allocations(db, [invoice.id for invoice in invoices])
    funds = load_funds(db, [allocation.fund_transaction_id for allocation in allocations])
    visible_funds, fund_restricted = permission_slice(db, current_user, "supply.finance.view", funds)
    approvals = load_approvals(db, invoices, funds)
    visible_approvals, approval_restricted = permission_slice(db, current_user, "supply.approval.view", approvals)
    contracts = load_contracts(db, ledger_rows, invoices, approvals)
    visible_contracts, contract_restricted = permission_slice(db, current_user, "supply.contract.view", contracts)
    return BusinessTraceOut(
        ledger_rows=ledger_rows,
        invoices=visible_invoices,
        allocations=allocations if visible_invoices and visible_funds else [],
        funds=visible_funds,
        execution_tasks=load_execution_tasks(db, funds) if visible_funds else [],
        approvals=visible_approvals,
        contracts=visible_contracts,
        restricted_count=invoice_restricted + fund_restricted + approval_restricted + contract_restricted,
    )
```

- [ ] **Step 4: 在数据中心接入追溯抽屉**

景区经营台账行增加“查看业务链路”，抽屉按台账 → 发票 → 核销 → 资金 → 审批 → 合同展示，节点可点击进入有权限的详情页。

```javascript
async function openBusinessTrace(row) {
  trace.value = await getBusinessTrace({
    scenic_id: row.scenic_id,
    source_kind: row.business_type,
    period_key: row.period_key
  })
  traceVisible.value = true
}
```

```vue
<BusinessTraceDrawer
  v-model="traceVisible"
  :trace="trace"
  @open-node="({ path, query }) => router.push({ path, query })"
/>
```

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend; python -m unittest tests.test_business_trace -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/components/BusinessTraceDrawer.test.js src/views/operation/index.test.js`

Expected: PASS。

```bash
git add -- backend/app/schemas/business_trace.py backend/app/services/business_trace.py backend/app/api/v1/endpoints/operation.py backend/tests/test_business_trace.py frontend/src/api/operation.js frontend/src/components/BusinessTraceDrawer.vue frontend/src/components/BusinessTraceDrawer.test.js frontend/src/views/operation/index.vue
git commit -m "feat: add supply chain trace view"
```
