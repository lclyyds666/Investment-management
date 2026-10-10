# 合同、台账与发票强关联实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为合同补充期限、景区和业务范围，并让审批单、台账期次和来源发票通过真实外键形成可追溯主线。

**Architecture:** 合同保存唯一景区和 JSON 业务范围；台账不在每个平台行复制合同，而用 `LedgerContractLink` 以“景区 + 门票/酒店 + 期次”唯一关联。审批和发票保存 `contract_id` 外键及编号快照，确认台账的事务同时锁定合同、确认台账并生成发票。

**Tech Stack:** SQLAlchemy、Pydantic、FastAPI、MySQL guarded SQL migrations、Vue 3、Element Plus、Python unittest、Vitest。

## Global Constraints

- 合同期限是自由文本，签订日期保持不变。
- 新合同必须且只能选择一个景区，至少选择门票或酒店一种业务类型。
- 合同不限制平台，可覆盖多个台账期次。
- 历史数据允许空外键；不能唯一匹配时禁止自动猜测。
- 台账确认前必须关联状态为已审批且范围匹配的合同。
- 已开票或已参与资金核销的来源发票不得被静默重建。

---

### Task 1: 建立合同与期次关联数据模型

**Files:**
- Create: `backend/migrations/20261010_contract_ledger_invoice_linkage.sql`
- Create: `backend/app/models/ledger_contract.py`
- Modify: `backend/app/models/contract.py`
- Modify: `backend/app/models/approval_form.py`
- Modify: `backend/app/models/invoice.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/init_db.py`
- Test: `backend/tests/test_contract_ledger_link_models.py`
- Test: `backend/tests/test_init_db.py`

**Interfaces:**
- Produces: `Contract.contract_term: str`, `Contract.scenic_id: str | None`, `Contract.business_scopes: list[str]`。
- Produces: `ApprovalForm.contract_id: int | None`, `ApprovalForm.scenic_id: str`。
- Produces: `Invoice.contract_id: int | None`。
- Produces: `LedgerContractLink(scenic_id, source_kind, period_key, contract_id, contract_no_snapshot, selected_by)`。
- Produces: `ScenicContractPreference(scenic_id, source_kind, last_contract_id)`。

- [ ] **Step 1: 编写模型失败测试**

```python
def test_period_contract_link_is_unique_per_scenic_kind_and_period(self):
    names = {constraint.name for constraint in LedgerContractLink.__table__.constraints}
    self.assertIn("uq_ledger_contract_period", names)
    self.assertTrue({"contract_term", "scenic_id", "business_scopes"}.issubset(Contract.__table__.columns))
    self.assertIn("contract_id", ApprovalForm.__table__.columns)
    self.assertIn("contract_id", Invoice.__table__.columns)
```

- [ ] **Step 2: 运行模型测试确认失败**

Run: `cd backend; python -m unittest tests.test_contract_ledger_link_models -v`

Expected: FAIL，提示 `LedgerContractLink` 或新增字段不存在。

- [ ] **Step 3: 实现 ORM 模型与关系**

```python
class LedgerContractLink(Base):
    __tablename__ = "biz_ledger_contract_link"
    __table_args__ = (UniqueConstraint(
        "scenic_id", "source_kind", "period_key", name="uq_ledger_contract_period"
    ),)
    id: Mapped[int] = mapped_column(primary_key=True)
    scenic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[InvoiceSourceKind] = mapped_column(SAEnum(InvoiceSourceKind, native_enum=False, length=16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_id: Mapped[int] = mapped_column(ForeignKey("biz_contract.id", ondelete="RESTRICT"), nullable=False)
    contract_no_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), nullable=False)
```

`business_scopes` 使用 SQLAlchemy `JSON`，新对象默认 `[]`；迁移中的历史列允许 `NULL`，Pydantic 输出归一化为空列表。

- [ ] **Step 4: 编写并执行可重复 MySQL 迁移**

迁移为每个新增列、索引、外键使用 `information_schema` 守卫；创建 `biz_ledger_contract_link` 和 `biz_scenic_contract_preference` 使用 `CREATE TABLE IF NOT EXISTS`。外键删除策略：审批、发票为 `SET NULL`，台账期次关联为 `RESTRICT`。

```sql
CREATE TABLE IF NOT EXISTS `biz_ledger_contract_link` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `scenic_id` VARCHAR(64) NOT NULL,
  `source_kind` VARCHAR(16) NOT NULL,
  `period_key` VARCHAR(255) NOT NULL,
  `contract_id` INT NOT NULL,
  `contract_no_snapshot` VARCHAR(64) NOT NULL,
  `selected_by` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ledger_contract_period` (`scenic_id`, `source_kind`, `period_key`),
  CONSTRAINT `fk_ledger_contract_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_ledger_contract_user` FOREIGN KEY (`selected_by`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `biz_scenic_contract_preference` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `scenic_id` VARCHAR(64) NOT NULL,
  `source_kind` VARCHAR(16) NOT NULL,
  `last_contract_id` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scenic_contract_preference` (`scenic_id`, `source_kind`),
  CONSTRAINT `fk_scenic_contract_preference_contract` FOREIGN KEY (`last_contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

合同、审批和发票新增列逐列使用以下守卫模式，索引和外键分别使用 `information_schema.statistics`、`information_schema.table_constraints` 守卫：

```sql
SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='biz_contract' AND column_name='contract_term'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `contract_term` VARCHAR(255) NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
```

Run: `cd backend; python -m unittest tests.test_init_db -v`

Expected: PASS，SQLite `create_all` 能发现新表。

- [ ] **Step 5: 运行模型回归并提交**

Run: `cd backend; python -m unittest tests.test_contract_ledger_link_models tests.test_invoice_models tests.test_init_db -v`

Expected: PASS。

```bash
git add -- backend/migrations/20261010_contract_ledger_invoice_linkage.sql backend/app/models backend/app/db/init_db.py backend/tests/test_contract_ledger_link_models.py backend/tests/test_init_db.py
git commit -m "feat: add contract ledger linkage models"
```

### Task 2: 扩展合同 API、表单、详情与导出

**Files:**
- Modify: `backend/app/schemas/contract.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Create: `backend/tests/test_contract_business_scope.py`
- Modify: `frontend/src/api/contract.js`
- Modify: `frontend/src/views/contract/index.vue`
- Modify: `frontend/src/components/ContractDetailDrawer.vue`
- Modify: `frontend/src/components/ContractDetailDrawer.test.js`
- Create: `frontend/src/views/contract/index.test.js`

**Interfaces:**
- Produces: `GET /contracts/eligible?scenic_id=<id>&source_kind=ticket|hotel -> list[ContractOut]`。
- Produces: `ContractCreate.contract_term`, `scenic_id`, `business_scopes`。
- Consumes: 景区选项来自现有 `GET /scenic-spots/configs`。

- [ ] **Step 1: 编写合同范围验证失败测试**

```python
def test_new_contract_requires_one_scenic_and_business_scope(self):
    with self.assertRaises(ValidationError):
        ContractCreate(contract_no="HT-1", title="测试", scenic_id="", business_scopes=[])

def test_eligible_contract_requires_approved_matching_scope(self):
    result = eligible_contracts(self.db, "changsha-dongqu", InvoiceSourceKind.TICKET)
    self.assertEqual([row.id for row in result], [self.approved_ticket_contract.id])
```

- [ ] **Step 2: 运行合同测试确认失败**

Run: `cd backend; python -m unittest tests.test_contract_business_scope -v`

Expected: FAIL，新增字段和 `eligible_contracts` 尚不存在。

- [ ] **Step 3: 实现 schema 与合资格查询**

```python
@field_validator("business_scopes")
def validate_business_scopes(cls, value):
    normalized = list(dict.fromkeys(value))
    if not normalized or not set(normalized) <= {"ticket", "hotel"}:
        raise ValueError("业务范围只能选择门票或酒店，且至少选择一项")
    return normalized
```

`/eligible` 只返回 `status == approved`、`scenic_id` 相同且 `business_scopes` 包含请求类型的合同，并继续应用现有合同可见范围过滤。

- [ ] **Step 4: 更新合同页面和详情测试**

前端新建/编辑表单增加“合同期限”“所属景区”“业务范围”；详情和合同台账增加相同字段；导出列顺序在签订日期后加入合同期限、景区、业务范围。

```javascript
const contractForm = reactive({
  contract_no: '', title: '', signed_date: null, contract_term: '', scenic_id: '', business_scopes: []
})

const contractRules = {
  scenic_id: [{ required: true, message: '请选择所属景区', trigger: 'change' }],
  business_scopes: [{ type: 'array', required: true, min: 1, message: '至少选择一种业务类型', trigger: 'change' }]
}

function contractPayload() {
  return {
    ...existingContractPayload(),
    contract_term: contractForm.contract_term.trim(),
    scenic_id: contractForm.scenic_id,
    business_scopes: [...contractForm.business_scopes]
  }
}
```

```javascript
expect(contractApi.createContract).toHaveBeenCalledWith(expect.objectContaining({
  contract_term: '2026年1月1日至2027年12月31日',
  scenic_id: 'guanquelou',
  business_scopes: ['ticket', 'hotel']
}))
expect(wrapper.text()).toContain('合同期限')
expect(wrapper.text()).toContain('鹳雀楼')
```

Run: `cd frontend; npm test -- src/views/contract/index.test.js src/components/ContractDetailDrawer.test.js src/api/contract.test.js`

Expected: PASS，提交载荷包含三个新增字段，详情能显示历史空值为 `—`。

- [ ] **Step 5: 运行合同 API 回归并提交**

Run: `cd backend; python -m unittest tests.test_contract_business_scope tests.test_contract_workflow_routing -v`

Expected: PASS。

```bash
git add -- backend/app/schemas/contract.py backend/app/api/v1/endpoints/contract.py backend/tests/test_contract_business_scope.py frontend/src/api/contract.js frontend/src/views/contract/index.vue frontend/src/views/contract/index.test.js frontend/src/components/ContractDetailDrawer.vue frontend/src/components/ContractDetailDrawer.test.js
git commit -m "feat: add contract term and scenic scope"
```

### Task 3: 将业务审批单改为真实合同选择

**Files:**
- Modify: `backend/app/schemas/approval_form.py`
- Modify: `backend/app/api/v1/endpoints/approval.py`
- Modify: `backend/tests/test_workflow_api.py`
- Modify: `frontend/src/views/approval/index.vue`
- Modify: `frontend/src/views/approval/index.test.js`

**Interfaces:**
- Consumes: `Contract.id`, `Contract.contract_no`, `Contract.scenic_id`。
- Produces: `ApprovalFormCreate.contract_id: int`，普通业务/付款审批必填。
- Produces: `_apply_contract_snapshot(form, contract)`，设置合同编号、景区和客户快照。

- [ ] **Step 1: 编写审批合同验证失败测试**

```python
def test_payment_form_requires_approved_contract(self):
    response = self.client.post("/api/v1/approval-forms", json={
        "form_type": "payment", "contract_id": self.draft_contract.id, "amount": "100.00"
    })
    self.assertEqual(response.status_code, 422)

def test_contract_snapshot_is_not_changed_after_contract_edit(self):
    self.assertEqual(form.contract_id, contract.id)
    self.assertEqual(form.contract_no, "HT-2026-001")
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `cd backend; python -m unittest tests.test_workflow_api.ApprovalFormApiTest -v`

Expected: FAIL，接口仍只接受手工合同编号。

- [ ] **Step 3: 实现后端合同门禁与快照**

创建和草稿编辑时按 `contract_id` 加载合同，要求已审批；更新 `contract_no`、`scenic_id`、`customer_name` 快照。`contract_no` 从写入 schema 移除或设为只读兼容字段，禁止客户端用编号覆盖已选合同。

```python
def _approved_contract(db: Session, contract_id: int) -> Contract:
    contract = db.get(Contract, contract_id)
    if not contract or contract.status != ContractStatus.APPROVED:
        raise HTTPException(status_code=422, detail="请选择已审批合同")
    return contract


def _apply_contract_snapshot(form: ApprovalForm, contract: Contract) -> None:
    form.contract_id = contract.id
    form.contract_no = contract.contract_no
    form.scenic_id = contract.scenic_id or ""
    form.customer_name = contract.party_b or contract.party_a or ""


contract = _approved_contract(db, payload.contract_id)
form = ApprovalForm(**payload.model_dump(exclude={"contract_no"}))
_apply_contract_snapshot(form, contract)
```

- [ ] **Step 4: 将审批表单改为合同下拉框**

前端加载可见已审批合同；选择后显示景区、客户、合同编号。编辑历史 `contract_id is null` 的单据时显示“历史未关联”，必须补选合同后才能重新提交。

```javascript
const approvedContracts = ref([])

async function loadApprovedContracts() {
  approvedContracts.value = await listContracts({ status: 'approved', page_size: 200 })
}

const selectedContract = computed(() => approvedContracts.value.find(item => item.id === form.contract_id))

function approvalPayload() {
  return { ...existingApprovalPayload(), contract_id: form.contract_id }
}
```

```vue
<el-select v-model="form.contract_id" filterable placeholder="选择已审批合同">
  <el-option v-for="item in approvedContracts" :key="item.id" :value="item.id" :label="`${item.contract_no} · ${item.title}`" />
</el-select>
<el-alert v-if="editingRow && !editingRow.contract_id" title="历史未关联，请补选合同后再提交" type="warning" />
```

Run: `cd frontend; npm test -- src/views/approval/index.test.js`

Expected: PASS，创建请求发送 `contract_id`，不再发送用户手工输入的 `contract_no`。

- [ ] **Step 5: 回归审批工作流并提交**

Run: `cd backend; python -m unittest tests.test_workflow_api tests.test_workflow_engine -v`

Expected: PASS，合同快照不影响现有审批节点和打印。

```bash
git add -- backend/app/schemas/approval_form.py backend/app/api/v1/endpoints/approval.py backend/tests/test_workflow_api.py frontend/src/views/approval/index.vue frontend/src/views/approval/index.test.js
git commit -m "feat: link approval forms to contracts"
```

### Task 4: 在台账确认时锁定合同

**Files:**
- Create: `backend/app/schemas/ledger_contract.py`
- Create: `backend/app/services/contract_linkage.py`
- Modify: `backend/app/api/v1/endpoints/ticket_ledger.py`
- Modify: `backend/app/api/v1/endpoints/hotel_ledger.py`
- Create: `backend/tests/test_ledger_contract_linkage.py`
- Modify: `backend/tests/test_ticket_ledger_invoice_sync.py`
- Modify: `backend/tests/test_hotel_ledger_invoice_sync.py`
- Modify: `frontend/src/api/ticketLedger.js`
- Modify: `frontend/src/api/hotelLedger.js`
- Modify: `frontend/src/components/TicketLedger.vue`
- Modify: `frontend/src/components/HotelLedger.vue`
- Modify: `frontend/src/components/TicketLedger.test.js`
- Modify: `frontend/src/components/HotelLedger.test.js`

**Interfaces:**
- Produces: `LedgerConfirmApproveIn(contract_id: int)`。
- Produces: `link_period_contract(db, scenic_id, source_kind, period_key, contract_id, user_id) -> LedgerContractLink`。
- Produces: `remember_contract_preference(...)`，按景区和门票/酒店分别记忆。

- [ ] **Step 1: 编写合同匹配与历史锁定失败测试**

```python
def test_confirm_rejects_contract_from_another_scenic(self):
    with self.assertRaises(ContractLinkError) as caught:
        link_period_contract(self.db, "scenic-a", InvoiceSourceKind.TICKET, "P1", self.other_contract.id, 1)
    self.assertEqual(caught.exception.code, "contract_scenic_mismatch")

def test_confirmed_period_keeps_original_contract(self):
    self.assertEqual(link.contract_id, first_contract.id)
```

- [ ] **Step 2: 运行台账关联测试确认失败**

Run: `cd backend; python -m unittest tests.test_ledger_contract_linkage -v`

Expected: FAIL，服务和 schema 尚不存在。

- [ ] **Step 3: 实现关联服务与确认事务**

`approve_confirm` 接收 JSON `{ "contract_id": 123 }`。在同一事务内：锁定期次关联行 → 校验合同状态、景区、业务范围 → 写关联与偏好 → 标记同期行已确认 → 生成进销项发票 → 提交。已确认期次若已有不同合同则返回 409，要求先撤销确认。

```python
def link_period_contract(db, scenic_id, source_kind, period_key, contract_id, user_id):
    existing = db.scalar(select(LedgerContractLink).where(
        LedgerContractLink.scenic_id == scenic_id,
        LedgerContractLink.source_kind == source_kind,
        LedgerContractLink.period_key == period_key,
    ).with_for_update())
    if existing:
        if existing.contract_id != contract_id:
            raise ContractLinkError("confirmed_period_contract_locked")
        return existing
    contract = db.get(Contract, contract_id)
    if not contract or contract.status != ContractStatus.APPROVED:
        raise ContractLinkError("contract_not_approved")
    if contract.scenic_id != scenic_id:
        raise ContractLinkError("contract_scenic_mismatch")
    if source_kind.value not in (contract.business_scopes or []):
        raise ContractLinkError("contract_scope_mismatch")
    link = LedgerContractLink(scenic_id=scenic_id, source_kind=source_kind, period_key=period_key, contract_id=contract.id, contract_no_snapshot=contract.contract_no, selected_by=user_id)
    db.add(link)
    remember_contract_preference(db, scenic_id, source_kind, contract.id)
    db.flush()
    return link
```

```python
link_period_contract(db, sid, source_kind, key, payload.contract_id, current_user.id)
for sibling in period_rows:
    sibling.confirmed = True
invoice_svc.sync_confirmed_period_invoices(db, scenic_id=sid, source_kind=source_kind, period_key=key)
db.commit()
```

- [ ] **Step 4: 更新门票与酒店合同选择 UI**

在“确认”动作前弹出合同选择框；默认值来自 `GET /contracts/eligible` 中标记的偏好合同。门票和酒店偏好独立。无合资格合同时禁用确认按钮并提供进入合同管理的提示。

```javascript
async function openConfirmContract(period) {
  const result = await listEligibleContracts({ scenic_id: props.scenicId, source_kind: 'ticket' })
  eligibleContracts.value = result.items || result
  confirmForm.contract_id = result.preferred_contract_id || eligibleContracts.value[0]?.id || null
  confirmPeriod.value = period
  contractDialogVisible.value = true
}

async function confirmPeriod() {
  await approveTicketLedgerConfirm(props.scenicId, confirmPeriod.value.row_id, {
    contract_id: confirmForm.contract_id
  })
  contractDialogVisible.value = false
  await loadLedger()
}
```

酒店组件使用相同流程，但 `source_kind: 'hotel'`，不得共享门票选择状态。

- [ ] **Step 5: 运行前后端台账测试**

Run: `cd backend; python -m unittest tests.test_ledger_contract_linkage tests.test_ticket_ledger_invoice_sync tests.test_hotel_ledger_invoice_sync -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/components/TicketLedger.test.js src/components/HotelLedger.test.js`

Expected: PASS。

- [ ] **Step 6: 提交期次合同关联**

```bash
git add -- backend/app/schemas/ledger_contract.py backend/app/services/contract_linkage.py backend/app/api/v1/endpoints/ticket_ledger.py backend/app/api/v1/endpoints/hotel_ledger.py backend/tests/test_ledger_contract_linkage.py backend/tests/test_ticket_ledger_invoice_sync.py backend/tests/test_hotel_ledger_invoice_sync.py frontend/src/api/ticketLedger.js frontend/src/api/hotelLedger.js frontend/src/components/TicketLedger.vue frontend/src/components/HotelLedger.vue frontend/src/components/TicketLedger.test.js frontend/src/components/HotelLedger.test.js
git commit -m "feat: require contracts for ledger confirmation"
```

### Task 5: 让来源发票继承合同并保护已使用数据

**Files:**
- Modify: `backend/app/services/invoice_generation.py`
- Modify: `backend/app/schemas/invoice.py`
- Modify: `backend/app/api/v1/endpoints/invoice.py`
- Modify: `backend/tests/test_invoice_generation.py`
- Modify: `backend/tests/test_invoice_api.py`
- Modify: `frontend/src/views/invoice/index.vue`
- Modify: `frontend/src/views/invoice/index.test.js`

**Interfaces:**
- Consumes: `LedgerContractLink`。
- Produces: 来源发票的 `contract_id` 与 `contract_no` 快照。
- Produces: `source_invoice_is_locked(invoice) -> bool`，当已开票、已有审批或已有资金核销时为真。

- [ ] **Step 1: 编写发票继承与锁定失败测试**

```python
def test_generated_invoices_inherit_period_contract(self):
    input_invoice, output_invoice = sync_confirmed_period_invoices(...)
    self.assertEqual(input_invoice.contract_id, self.contract.id)
    self.assertEqual(output_invoice.contract_no, self.contract.contract_no)

def test_used_source_invoice_cannot_be_invalidated(self):
    with self.assertRaises(InvoiceSourceLocked):
        invalidate_period_invoices(...)
```

- [ ] **Step 2: 运行发票测试确认失败**

Run: `cd backend; python -m unittest tests.test_invoice_generation tests.test_invoice_api -v`

Expected: FAIL，来源发票尚未读取期次合同。

- [ ] **Step 3: 实现合同继承与只读规则**

`sync_confirmed_period_invoices` 必须先取得唯一 `LedgerContractLink`；进销项均保存合同外键和编号快照。发票编辑时只允许从同景区合资格合同中更换，已有审批或资金使用后禁止更换合同和来源金额。

```python
def source_invoice_is_locked(invoice: Invoice) -> bool:
    return (
        invoice.status == InvoiceStatus.ISSUED
        or invoice.workflow_instance_id is not None
        or bool(invoice.allocations)
    )


def sync_confirmed_period_invoices(db, scenic_id, source_kind, period_key):
    link = db.scalar(select(LedgerContractLink).where(
        LedgerContractLink.scenic_id == scenic_id,
        LedgerContractLink.source_kind == source_kind,
        LedgerContractLink.period_key == period_key,
    ))
    if not link:
        raise InvoiceGenerationError("period_contract_missing")
    rows = _source_rows(db, source_kind, scenic_id, period_key)
    return upsert_source_invoices(
        db, rows=rows, scenic_id=scenic_id, source_kind=source_kind, period_key=period_key,
        contract_id=link.contract_id, contract_no=link.contract_no_snapshot,
    )
```

更新来源发票前调用 `source_invoice_is_locked()`；为真时返回 409，不执行失效、覆盖金额或更换合同。

- [ ] **Step 4: 更新发票页面合同信息**

显示合同编号、景区、来源业务和期次；来源发票默认只读展示继承合同。历史空关联发票允许业务复核补选一次，保存后形成快照。

```javascript
const invoiceColumns = [
  ...existingInvoiceColumns,
  { prop: 'contract_no', label: '合同编号', minWidth: 150 },
  { prop: 'scenic_name', label: '景区', minWidth: 140 },
  { prop: 'source_kind', label: '来源业务', minWidth: 100 },
  { prop: 'period_key', label: '台账期次', minWidth: 180 }
]

function canBackfillContract(row) {
  return canReview.value && row.generated_by_source && !row.contract_id && !row.workflow_instance_id && row.status !== 'issued'
}

async function saveHistoricalContract(row, contractId) {
  await updateInvoice(row.id, { contract_id: contractId })
  await loadInvoices()
}
```

- [ ] **Step 5: 运行回归并提交**

Run: `cd backend; python -m unittest tests.test_invoice_generation tests.test_invoice_api tests.test_invoice_workflow -v`

Expected: PASS。

Run: `cd frontend; npm test -- src/views/invoice/index.test.js`

Expected: PASS。

```bash
git add -- backend/app/services/invoice_generation.py backend/app/schemas/invoice.py backend/app/api/v1/endpoints/invoice.py backend/tests/test_invoice_generation.py backend/tests/test_invoice_api.py frontend/src/views/invoice/index.vue frontend/src/views/invoice/index.test.js
git commit -m "feat: inherit contracts on ledger invoices"
```
