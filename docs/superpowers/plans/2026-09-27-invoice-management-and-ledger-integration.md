# 文旅台账与发票管理联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将门票/酒店已确认台账周期自动转换为可追溯的进项、销项发票记录，补齐客户银行信息、票付通平台、销项审批和模板打印能力。

**Architecture:** 在现有 `biz_invoice` 和审批中心上做扩展，新增来源快照、附件、销项明细和景区方向默认合同数据。门票/酒店确认接口调用一个幂等的来源同步服务；前端发票页面按进项/销项展示，销项审批复用岗位工作流但使用两节点发票流程。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、MySQL 增量 SQL、Vue 3、Element Plus、Vitest、pytest、openpyxl、python-docx。

## Global Constraints

- 景区、台账类型（门票/酒店）和发票方向（进项/销项）均独立隔离。
- 同一来源周期生成一条进项和一条销项；销项明细保留每个平台明细行。
- 金额只统计平台明细行，排除本期合计和总合计展示行。
- 确认函删除、重传、重新确认及影响已确认周期的台账修改，删除旧发票、附件、明细和审批后重新生成。
- 业务复核独占发票编辑、上传、审批单生成和开票明细调整；供管负责人只审批；其他角色只读/打印。
- 发票状态只能由附件上传接口从“待开票”变为“已开票”，编辑接口拒绝状态字段。
- 每条发票允许多个附件，任一附件上传成功即为“已开票”。
- 销项金额修改后明细必须逐行手工调整，明细合计不相等时禁止提交审批和打印。
- 取消普通“新建发票”和手工删除；来源周期负责发票记录生命周期。
- 门票和酒店编辑平台下拉及酒店平台配置均支持“票付通”。
- 保留当前门票、酒店金额算法，不在本计划中修改既有景区算法。

---

### Task 1: 建立发票来源与客户字段数据基础

**Files:**
- Create: `backend/migrations/20260927_invoice_ledger_integration.sql`
- Modify: `backend/app/models/invoice.py`
- Create: `backend/app/models/invoice_preference.py`
- Modify: `backend/app/models/customer.py`
- Modify: `backend/app/models/approval_form.py`
- Modify: `backend/app/core/enums.py`
- Modify: `backend/app/db/init_db.py`
- Modify: `backend/app/schemas/invoice.py`
- Modify: `backend/app/schemas/customer.py`
- Modify: `backend/app/schemas/approval_form.py`
- Test: `backend/tests/test_invoice_models.py`
- Test: `backend/tests/test_customer_schema.py`
- Test: `backend/tests/test_workflow_models.py`

**Interfaces:**
- Produces `InvoiceDirection`, `InvoiceSourceKind`, `InvoiceApprovalStatus` and source fields on `Invoice`.
- Produces `InvoiceAttachment`, `InvoiceDetail`, and `ScenicInvoicePreference` SQLAlchemy models with cascade relationships.
- Produces `InvoiceOut`, `InvoiceUpdate`, `InvoiceDetailOut`, `CustomerOut` fields consumed by later API tasks.
- Adds `ContractType.INVOICE` and `ApprovalForm.invoice_id` for the later two-node workflow.

- [ ] **Step 1: Write failing model and schema tests**

  Add tests that instantiate an invoice with `direction`, `source_kind`, `scenic_id`, `period_key`, and `source_fingerprint`; assert the unique constraint columns exist; assert an invoice can have multiple attachments and details; assert `ScenicInvoicePreference` keys include `scenic_id` and `direction`; assert customer create/update schemas accept `bank_name` and `bank_account`; assert `ContractType.INVOICE` is available and `ApprovalForm` exposes `invoice_id`.

- [ ] **Step 2: Run the focused tests to verify failure**

  Run from `backend`:

  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_invoice_models.py tests/test_customer_schema.py tests/test_workflow_models.py -q
  ```

  Expected: failures for missing invoice source fields, attachment/detail models, customer bank fields, and invoice form type.

- [ ] **Step 3: Implement the model and schema foundation**

  Extend `Invoice` with nullable legacy-compatible source fields, direction/status enums, customer snapshots, workflow linkage, and a uniqueness constraint on `direction + source_kind + scenic_id + period_key` for generated records. Add `InvoiceAttachment` and `InvoiceDetail` relationships with delete-orphan cascade. Add `ScenicInvoicePreference` with one row per scenic/direction and the last contract number. Add customer bank columns and Pydantic fields. Extend `ApprovalForm` with nullable `invoice_id` and add the invoice form enum without changing payment/business behavior.

- [ ] **Step 4: Add the idempotent MySQL migration**

  Use the repository's `information_schema`/prepared-statement pattern. Add nullable columns to `biz_invoice`, create `biz_invoice_attachment`, `biz_invoice_detail`, and `biz_scenic_invoice_preference`, add customer bank columns, add the invoice form enum value/approval link, and create the source uniqueness index. Make the migration safe to run twice and leave existing manual invoices readable.

- [ ] **Step 5: Register models and rerun tests**

  Import the new models in `backend/app/db/init_db.py`, run the focused pytest command again, and run `git diff --check`.

- [ ] **Step 6: Commit the foundation**

  ```bash
  git add backend/migrations/20260927_invoice_ledger_integration.sql backend/app/models/invoice.py backend/app/models/invoice_preference.py backend/app/models/customer.py backend/app/models/approval_form.py backend/app/core/enums.py backend/app/db/init_db.py backend/app/schemas/invoice.py backend/app/schemas/customer.py backend/app/schemas/approval_form.py backend/tests/test_invoice_models.py backend/tests/test_customer_schema.py backend/tests/test_workflow_models.py
  git commit -m "feat: add invoice source and customer bank models"
  ```

### Task 2: 支持票付通平台

**Files:**
- Modify: `backend/app/services/hotel_ledger.py`
- Modify: `backend/app/services/scenic_config.py`
- Modify: `backend/app/schemas/scenic_config.py`
- Modify: `backend/app/api/v1/endpoints/hotel_ledger.py`
- Modify: `frontend/src/components/TicketLedger.vue`
- Modify: `frontend/src/components/HotelLedger.vue`
- Modify: `frontend/src/components/ScenicConfigDialog.vue`
- Test: `backend/tests/test_hotel_scenic_config.py`
- Test: `backend/tests/test_scenic_config.py`
- Test: `frontend/src/components/TicketLedger.test.js`
- Test: `frontend/src/components/HotelLedger.test.js`

**Interfaces:**
- Produces one shared hotel platform tuple containing `抖音、美团、携程、票付通`.
- Keeps ticket platform options as `抖音、美团、携程、同程、票付通`.
- Makes both frontend edit dialogs and the hotel configuration checkbox consume the same displayed option.

- [ ] **Step 1: Add failing platform tests**

  Assert the hotel schema accepts `hotel_platforms=["票付通"]`, the scenic config service parses and serializes it, and the ticket/hotel edit components render an option labeled `票付通`.

- [ ] **Step 2: Run the focused platform tests**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_hotel_scenic_config.py tests/test_scenic_config.py -q
  npm run test -- --run frontend/src/components/TicketLedger.test.js frontend/src/components/HotelLedger.test.js
  ```

  Expected: failures because hotel platform validation currently rejects `票付通` and the hotel UI list has only three options.

- [ ] **Step 3: Implement platform constants and validation**

  Update `SYSTEM_HOTEL_PLATFORMS`, `HOTEL_PLATFORMS`, hotel parser platform recognition, and endpoint filtering. Add `票付通` to both edit dialog arrays and the hotel configuration checkbox list. Do not alter platform-specific amount calculations.

- [ ] **Step 4: Verify and commit platform support**

  Rerun both focused test commands, then commit:

  ```bash
  git add backend/app/services/hotel_ledger.py backend/app/services/scenic_config.py backend/app/schemas/scenic_config.py backend/app/api/v1/endpoints/hotel_ledger.py frontend/src/components/TicketLedger.vue frontend/src/components/HotelLedger.vue frontend/src/components/ScenicConfigDialog.vue backend/tests/test_hotel_scenic_config.py backend/tests/test_scenic_config.py frontend/src/components/TicketLedger.test.js frontend/src/components/HotelLedger.test.js
  git commit -m "feat: add piaofutong ledger platform"
  ```

### Task 3: 实现来源周期汇总与确认同步服务

**Files:**
- Create: `backend/app/services/invoice_generation.py`
- Modify: `backend/app/api/v1/endpoints/ticket_ledger.py`
- Modify: `backend/app/api/v1/endpoints/hotel_ledger.py`
- Modify: `backend/app/services/ticket_ledger.py` (only if period/detail helpers need extraction)
- Modify: `backend/app/services/hotel_ledger.py` (only if period/detail helpers need extraction)
- Test: `backend/tests/test_invoice_generation.py`
- Test: `backend/tests/test_ticket_ledger_invoice_sync.py`
- Test: `backend/tests/test_hotel_ledger_invoice_sync.py`

**Interfaces:**
- `ticket_period_key(row: TicketLedger) -> str`
- `hotel_period_key(row: HotelLedger) -> str`
- `remove_period_invoices(db: Session, *, scenic_id: str, source_kind: InvoiceSourceKind, period_key: str) -> None`
- `sync_confirmed_period_invoices(db: Session, *, scenic_id: str, source_kind: InvoiceSourceKind, period_key: str) -> tuple[Invoice, Invoice]`
- `invalidate_period_invoices(...) -> None`

- [ ] **Step 1: Write failing aggregation tests**

  Build ticket and hotel rows for one scenic/period with multiple platforms plus synthetic total rows. Assert `sync_confirmed_period_invoices` creates exactly one input and one output, input amount equals the sum of `hexiao_amount`, output amount equals the sum of `jinying_amount`, total rows are ignored, source fields are populated, and output detail rows preserve source type, platform, source row ID, and amount.

- [ ] **Step 2: Write failing lifecycle tests**

  Assert a second sync replaces the first generated records without duplicates; `remove_period_invoices` removes both directions, attachments, details, and approval links; a source period can be regenerated after confirmation changes; ticket and hotel rows with the same period key do not collide.

- [ ] **Step 3: Run generation tests to verify failure**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_invoice_generation.py tests/test_ticket_ledger_invoice_sync.py tests/test_hotel_ledger_invoice_sync.py -q
  ```

  Expected: import or assertion failures because the service and source relationships do not exist.

- [ ] **Step 4: Implement deterministic period collection**

  Extract/reuse the existing `_period_key` rules. Collect only persisted platform rows in the requested `scenic_id` and period; do not consume frontend total rows. Sort details by source row order and ID. Compute Decimal totals and a stable fingerprint from source row IDs, amounts, and platform names.

- [ ] **Step 5: Implement delete-and-rebuild synchronization**

  Delete generated records by the source unique key, rely on relationships for dependent rows, then insert input/output snapshots and output details. Resolve the remembered contract from `ScenicInvoicePreference` without inventing a contract. Fill customer snapshots when a remembered contract resolves to a customer; otherwise leave them editable/blank.

- [ ] **Step 6: Hook confirmation and source invalidation transactionally**

  In ticket/hotel confirmation approval, call `sync_confirmed_period_invoices` before commit. In confirmation upload/delete and row update/delete paths, call `remove_period_invoices` when a confirmed period is invalidated. If a row moves between periods, invalidate both old and new keys. Let exceptions roll back the ledger confirmation transaction.

- [ ] **Step 7: Run tests and commit the sync service**

  Rerun all three focused test modules and the existing ticket/hotel confirmation tests. Commit:

  ```bash
  git add backend/app/services/invoice_generation.py backend/app/api/v1/endpoints/ticket_ledger.py backend/app/api/v1/endpoints/hotel_ledger.py backend/app/services/ticket_ledger.py backend/app/services/hotel_ledger.py backend/tests/test_invoice_generation.py backend/tests/test_ticket_ledger_invoice_sync.py backend/tests/test_hotel_ledger_invoice_sync.py
  git commit -m "feat: sync invoices from confirmed ledger periods"
  ```

### Task 4: 增加发票附件、明细和业务接口

**Files:**
- Modify: `backend/app/api/v1/endpoints/invoice.py`
- Modify: `backend/app/schemas/invoice.py`
- Create: `backend/app/services/invoice_documents.py`
- Modify: `backend/app/services/organization_catalog.py`
- Modify: `backend/app/api/v1/router.py` only if new subrouters are split out
- Modify: `frontend/src/api/invoice.js`
- Test: `backend/tests/test_invoice_api.py`

**Interfaces:**
- `GET /invoices` accepts `direction`, `scenic_id`, `source_kind`, `period_key`, and `status` filters.
- `PUT /invoices/{invoice_id}` updates title, tax number, amount, contract number, customer snapshot fields, and remark; rejects `status`, source identity, and workflow fields.
- `POST /invoices/{invoice_id}/attachments` accepts multipart `files` and returns all stored attachments.
- `GET /invoices/{invoice_id}/attachments/{attachment_id}` downloads one attachment with authorization.
- `GET /invoices/{invoice_id}/details` returns output detail rows and the current difference from invoice amount.
- `PUT /invoices/{invoice_id}/details/{detail_id}` updates one detail amount for business review only.
- `GET /invoices/{invoice_id}/stats` and existing stats retain backward-compatible aggregate fields.

- [ ] **Step 1: Write failing API permission and lifecycle tests**

  Use the existing test client fixtures to assert business review can edit/upload, supply governance can approve only, ordinary view users receive read-only responses, create/delete endpoints are unavailable or return the documented conflict, and attempting to update `status` returns 422/403. Assert multiple files set status to issued after the first successful upload.

- [ ] **Step 2: Write failing detail validation tests**

  Assert a detail update succeeds while the difference is nonzero but `submit_invoice_approval` and both print endpoints reject the invoice until the detail sum equals `amount`.

- [ ] **Step 3: Run the focused API tests to verify failure**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_invoice_api.py -q
  ```

- [ ] **Step 4: Implement scoped invoice queries and editable-field validation**

  Add direction/source filters, hide legacy manual records from generated tabs unless explicitly requested, and guard all mutation endpoints with the new invoice manage permission. Preserve `InvoiceStatus.VOID` for legacy compatibility but expose generated records as pending/issued.

- [ ] **Step 5: Implement secure multi-file attachment storage**

  Store files below a per-invoice directory using generated names, reject path traversal and disallowed extensions, persist metadata only after the file write succeeds, and set `Invoice.status = ISSUED` in the same transaction. A later upload adds an attachment without replacing existing files.

- [ ] **Step 6: Implement detail updates and source consistency checks**

  Return `detail_total` and `difference` in the schema. Permit only amount and row-level business fields in the detail update. Centralize `assert_invoice_details_balanced(invoice)` for approval/print callers.

- [ ] **Step 7: Add frontend API wrappers and run tests**

  Add request helpers for filtered lists, attachments, details, detail updates, approval creation, and document downloads. Rerun the focused backend tests and commit:

  ```bash
  git add backend/app/api/v1/endpoints/invoice.py backend/app/schemas/invoice.py backend/app/services/invoice_documents.py backend/app/services/organization_catalog.py frontend/src/api/invoice.js backend/tests/test_invoice_api.py
  git commit -m "feat: add invoice attachments and detail APIs"
  ```

### Task 5: 建立两节点销项审批与模板服务

**Files:**
- Modify: `backend/app/core/enums.py`
- Modify: `backend/app/services/workflow_catalog.py`
- Modify: `backend/app/services/workflow_engine.py`
- Modify: `backend/app/api/v1/endpoints/approval.py`
- Modify: `backend/app/api/v1/endpoints/approval_stats.py`
- Modify: `backend/app/schemas/approval_form.py`
- Modify: `backend/app/services/approval_print.py` or create `backend/app/services/invoice_approval_print.py`
- Create: `backend/app/templates/approval/invoice.docx`
- Create: `backend/app/templates/invoice/invoice_detail.xlsx`
- Modify: `backend/app/api/v1/endpoints/invoice.py`
- Test: `backend/tests/test_invoice_workflow.py`
- Test: `backend/tests/test_invoice_templates.py`
- Test: `backend/tests/test_workflow_api.py`

**Interfaces:**
- Workflow code: `supply.invoice.v1`.
- Workflow target: `WorkflowTargetType.INVOICE_APPROVAL`.
- Form type: `ContractType.INVOICE` linked to `ApprovalForm.invoice_id`.
- `POST /invoices/{invoice_id}/approval-form` creates or reopens the invoice approval form for business review.
- `POST /invoices/{invoice_id}/approval-form/submit` starts the invoice workflow.
- `GET /invoices/{invoice_id}/approval-form/print` returns the filled DOCX only after approval.
- `GET /invoices/{invoice_id}/details/print` returns the filled XLSX only after detail balance validation.

- [ ] **Step 1: Write failing workflow tests**

  Assert an invoice approval form uses exactly two nodes: `supply.business_reviewer` applicant and `governance.supply_leader` department head; submission records the reviewer; governance approval changes the form to approved; a non-governance user cannot approve; a rejected form can be resubmitted after business review edits.

- [ ] **Step 2: Run the workflow tests to verify failure**

  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_invoice_workflow.py tests/test_workflow_api.py -q
  ```

- [ ] **Step 3: Add invoice workflow catalog and projection support**

  Add the target enum, workflow definition/version, `ApprovalForm` projection branch, submission permission mapping, pending statistics, and explicit invoice form handling so invoice forms do not fall through to the five-node business chain.

- [ ] **Step 4: Implement invoice approval endpoints**

  Require business review manage permission to create/submit and governance approve permission to approve. Snapshot current customer, contract, amount, and applicant values into the approval form. Refuse creation when the customer name/tax number or balanced detail preconditions are missing.

- [ ] **Step 5: Add template assets and renderers**

  Copy the user-provided `开票审批单.docx` to the fixed backend template path and `开票明细.xlsx` to the fixed template path. Implement DOCX paragraph/run replacement for buyer fields, tax number, address/phone, bank/account, amount, contract, business item, applicant, department head, and dates. Implement XLSX row insertion/filling for columns A-D and a final total row while preserving style/merged cells/print setup.

- [ ] **Step 6: Enforce print preconditions and test files**

  Reject DOCX download before workflow approval. Reject XLSX download when detail total differs from invoice amount. Assert generated files contain the expected buyer/platform/amount values and the correct number of rows. Commit:

  ```bash
  git add backend/app/core/enums.py backend/app/services/workflow_catalog.py backend/app/services/workflow_engine.py backend/app/api/v1/endpoints/approval.py backend/app/api/v1/endpoints/approval_stats.py backend/app/schemas/approval_form.py backend/app/services/approval_print.py backend/app/services/invoice_approval_print.py backend/app/templates/approval/invoice.docx backend/app/templates/invoice/invoice_detail.xlsx backend/app/api/v1/endpoints/invoice.py backend/tests/test_invoice_workflow.py backend/tests/test_invoice_templates.py backend/tests/test_workflow_api.py
  git commit -m "feat: add invoice approval and print workflow"
  ```

### Task 6: 完成客户档案和台账前端字段

**Files:**
- Modify: `frontend/src/views/customer/index.vue`
- Modify: `frontend/src/api/customer.js` only if payload normalization is needed
- Modify: `frontend/src/components/TicketLedger.vue`
- Modify: `frontend/src/components/HotelLedger.vue`
- Modify: `frontend/src/components/ScenicConfigDialog.vue`
- Test: `frontend/src/views/customer/index.test.js`
- Test: `frontend/src/components/TicketLedger.test.js`
- Test: `frontend/src/components/HotelLedger.test.js`

**Interfaces:**
- Customer edit payload includes `bank_name` and `bank_account`.
- Customer detail drawer displays both fields.
- Ticket/hotel edit dialogs and hotel config display the platform option produced by Task 2.

- [ ] **Step 1: Add failing Vue tests**

  Assert empty customer form, edit loading, save payload, and detail drawer include both bank fields. Assert platform options contain `票付通` in ticket and hotel dialogs.

- [ ] **Step 2: Run frontend tests to verify failure**

  ```bash
  npm run test -- --run frontend/src/views/customer/index.test.js frontend/src/components/TicketLedger.test.js frontend/src/components/HotelLedger.test.js
  ```

- [ ] **Step 3: Add bank fields to customer forms and detail view**

  Add labeled inputs “开户行” and “账号” to the edit dialog, include them in `emptyForm`, `openEdit`, `onSave`, and the read-only descriptions. Keep existing customer validation and material upload behavior unchanged.

- [ ] **Step 4: Verify platform UI and commit**

  Rerun the focused frontend tests and commit:

  ```bash
  git add frontend/src/views/customer/index.vue frontend/src/api/customer.js frontend/src/components/TicketLedger.vue frontend/src/components/HotelLedger.vue frontend/src/components/ScenicConfigDialog.vue frontend/src/views/customer/index.test.js frontend/src/components/TicketLedger.test.js frontend/src/components/HotelLedger.test.js
  git commit -m "feat: expose customer bank fields and ledger platform"
  ```

### Task 7: 重做发票管理前端

**Files:**
- Modify: `frontend/src/views/invoice/index.vue`
- Modify: `frontend/src/api/invoice.js`
- Modify: `frontend/src/constants/business.js` if permission labels are needed
- Modify: `frontend/src/router/routes.test.js` if route permission expectations change
- Test: `frontend/src/views/invoice/index.test.js`

**Interfaces:**
- Consumes invoice list/stats, attachment, detail, approval, and print APIs from Tasks 4-5.
- Produces two tabs/filters for `input` and `output`, with operation visibility based on `supply.invoice.manage` and `supply.invoice.approve`.

- [ ] **Step 1: Replace the create-oriented test fixtures**

  Add tests for the input/output tabs, required columns, no “新建发票” button, status read-only rendering, contract selection, separate scenic/direction defaults, multi-file upload, output detail balance display, approval generation, and print button gating.

- [ ] **Step 2: Run the invoice view tests to verify failure**

  ```bash
  npm run test -- --run frontend/src/views/invoice/index.test.js
  ```

- [ ] **Step 3: Implement the input invoice tab**

  Remove `openCreate`, the create dialog mode, and delete action. Render invoice title, tax number, amount, contract, status, and actions. Add business-review-only edit and multi-file upload; refresh list/stats after each upload and show issued status.

- [ ] **Step 4: Implement the output invoice tab and contract/customer form**

  Add output edit dialog with contract-management selection, direction-specific remembered default, customer snapshot fields, and amount editing. Add actions for approval form generation, detail editing, detail print, approval print, and invoice upload with permission guards.

- [ ] **Step 5: Implement the detail editor**

  Render source type, platform, fixed “价税合计” label, editable amount, invoice amount, detail total, and difference. Enable save/print/approval actions only when the difference is zero and the user has manage permission.

- [ ] **Step 6: Run frontend tests and commit**

  Run the focused invoice tests plus route/permission tests, then commit:

  ```bash
  npm run test -- --run frontend/src/views/invoice/index.test.js frontend/src/router/routes.test.js frontend/src/utils/businessAuthorization.test.js
  git add frontend/src/views/invoice/index.vue frontend/src/api/invoice.js frontend/src/constants/business.js frontend/src/router/routes.test.js frontend/src/views/invoice/index.test.js
  git commit -m "feat: redesign invoice management page"
  ```

### Task 8: 端到端回归、迁移和发布验证

**Files:**
- Modify: `backend/tests/test_invoice_generation.py`
- Modify: `backend/tests/test_invoice_api.py`
- Modify: `backend/tests/test_invoice_workflow.py`
- Modify: `frontend/src/views/invoice/index.test.js`
- Modify: `frontend/src/views/customer/index.test.js`
- Modify: `backend/README.md` with migration/template deployment commands
- Modify: `README.md` with invoice workflow operating notes

**Interfaces:**
- Migration is runnable against an existing database without losing legacy invoices.
- Production template paths are inside the backend package, not the developer desktop.

- [ ] **Step 1: Run all backend feature tests**

  ```bash
  cd backend
  .venv/Scripts/python.exe -m pytest tests/test_invoice_models.py tests/test_customer_schema.py tests/test_invoice_generation.py tests/test_invoice_api.py tests/test_invoice_workflow.py tests/test_ticket_ledger_invoice_sync.py tests/test_hotel_ledger_invoice_sync.py tests/test_scenic_config.py tests/test_hotel_scenic_config.py -q
  ```

- [ ] **Step 2: Run all frontend feature tests**

  ```bash
  npm run test -- --run frontend/src/views/invoice/index.test.js frontend/src/views/customer/index.test.js frontend/src/components/TicketLedger.test.js frontend/src/components/HotelLedger.test.js frontend/src/router/routes.test.js frontend/src/utils/businessAuthorization.test.js
  ```

- [ ] **Step 3: Apply and verify the SQL migration on a disposable database**

  Run `backend/migrations/20260927_invoice_ledger_integration.sql` twice, inspect the new columns/indexes/tables, and assert existing `biz_invoice` rows remain readable. Do not run destructive operations against the production database during local validation.

- [ ] **Step 4: Execute one ticket and one hotel acceptance flow**

  For each flow, upload/parse a period with at least two platforms, save rows, upload a confirmation letter, approve it as business review, verify one input/one output plus platform detail rows, edit output amount and reconcile details, generate/approve/print the DOCX, print the XLSX, upload multiple invoice files, and verify issued status. Re-upload the confirmation letter and verify old invoices/attachments/approvals are removed before the replacement records are created.

- [ ] **Step 5: Run build and repository checks**

  ```bash
  npm run build
  git diff --check
  git status --short
  ```

- [ ] **Step 6: Document deployment order and commit release notes**

  Document: apply SQL migration, deploy backend with templates, deploy frontend, restart services, then run a read-only invoice list smoke test. Commit only the README/test adjustments:

  ```bash
  git add backend/README.md README.md backend/tests frontend/src/views/invoice/index.test.js
  git commit -m "docs: add invoice integration rollout checks"
  ```
