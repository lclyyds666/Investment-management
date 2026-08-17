# 投资公司法务风控模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在山东出版投资有限公司 Web 子平台交付案件草稿、正式建档、全生命周期明细、五类预警、钉钉通知、统计和标准 Excel 导入导出的法务风控模块。

**Architecture:** 在现有 FastAPI 单体服务内增加独立 `legal-risk` 数据域和 `/api/v1/legal-risk` 资源型 API，复用现有登录、公司角色、审计、上传目录和 MySQL。Vue 3 前端增加 `InvestmentLayout` 与法务工作台、案件、预警、统计页面；每日扫描和失败补偿由独立 systemd timer 调用后端 jobs，避免 Uvicorn 双 worker 重复调度。

**Tech Stack:** Python 3、FastAPI 0.115、SQLAlchemy 2.0、Pydantic 2、MySQL、openpyxl、Vue 3、Vite 6、Element Plus、ECharts 5、Vitest、systemd。

## Global Constraints

- 案件主状态只能是：审查立案、审理中、已判决、执行中、终本、已结案。
- 裁判/结果类型只能是：一审、二审、再审、调解、和解。
- `legal_case` 不得包含风险等级字段；风险点只保存在进展风险记录。
- 金额和统计口径不得出现“重大案件”指标或筛选。
- 普通业务人员与法务风控人员拥有相同法务权限和全部案件数据范围。
- 董事长、总经理、副总经理使用同一管理层只读权限；当前用 `invest_director` 兼容三类管理岗位。
- `is_superuser=true` 的信息维护超级管理员拥有法务模块最大权限。
- 外聘法律顾问仅能访问被指派案件，并只能维护授权范围内的法律意见、进展和附件。
- 草稿不生成案件编号、不进入统计、不生成预警、不发送钉钉消息。
- 钉钉消息不得包含当事人、案情、金额、风险正文或附件链接。
- 附件类型仅限 PDF、DOC、DOCX、XLS、XLSX、PNG、JPG、JPEG，单文件不超过 50 MB。
- 不猜测不存在的历史 Excel 台账格式，只提供版本化标准模板与两阶段事务导入。
- 保留 `frontend/src/views/approval/index.vue`、`frontend/src/views/contract/index.vue` 及其他现有未提交改动。
- 当前执行不自动创建 Git commit；只有用户明确要求时才提交。

---

## File Structure

### Backend domain

- `backend/app/models/legal_risk.py`: 法务案件、明细、附件、预警、投递、活动和导入 ORM。
- `backend/app/schemas/legal_risk.py`: 法务枚举、写入载荷、列表和详情响应。
- `backend/app/services/legal_permissions.py`: 投资公司准入、能力和案件数据范围。
- `backend/app/services/legal_cases.py`: 编号、正式建档、状态、归档、金额和共享查询条件。
- `backend/app/services/legal_alerts.py`: 五类预警生成、阶段计算、状态闭环和防重。
- `backend/app/services/dingtalk.py`: 加签、最小披露消息、发送和重试结果解析。
- `backend/app/services/legal_statistics.py`: 工作台、状态统计、列表与导出共享口径。
- `backend/app/services/legal_imports.py`: 模板、预检、逐行规范化、确认和错误报告。
- `backend/app/api/v1/endpoints/legal_risk.py`: 法务 API 路由编排，不承载领域计算。
- `backend/app/jobs/legal_alert_scan.py`: 每日扫描和投递入口。
- `backend/app/jobs/legal_alert_retry.py`: 五分钟失败投递补偿入口。

### Frontend domain

- `frontend/src/layout/InvestmentLayout.vue`: 投资公司工作界面、导航、角标和移动端折叠。
- `frontend/src/api/legalRisk.js`: `/legal-risk` API 客户端。
- `frontend/src/store/legalAlerts.js`: 30 秒角标刷新、重要预警弹窗已读状态。
- `frontend/src/views/legal-risk/DashboardView.vue`: 工作台指标和期限/风险清单。
- `frontend/src/views/legal-risk/CaseListView.vue`: 草稿和正式案件统一列表及筛选。
- `frontend/src/views/legal-risk/CaseEditorView.vue`: 草稿编辑与正式建档表单。
- `frontend/src/views/legal-risk/CaseDetailView.vue`: 案件概览和八标签详情。
- `frontend/src/views/legal-risk/AlertsView.vue`: 预警筛选、处理和投递记录。
- `frontend/src/views/legal-risk/StatisticsView.vue`: 固定六状态统计、下钻和导出。
- `frontend/src/views/legal-risk/ImportDialog.vue`: 模板下载、预检、警告确认和错误报告。

---

### Task 1: 投资公司资源权限、用户手机号与门户上线

**Files:**
- Modify: `backend/app/core/enums.py`
- Modify: `backend/app/services/permissions.py`
- Modify: `backend/app/services/portal.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/api/v1/endpoints/user.py`
- Create: `backend/migrations/20260814_legal_risk_foundation.sql`
- Modify: `backend/tests/test_company_permissions.py`
- Modify: `backend/tests/test_portal_api.py`

**Interfaces:**
- Produces: `ResourceCode.INVEST_LEGAL_DASHBOARD|CASES|ALERTS|STATISTICS|ADMIN`。
- Produces: `allowed_resources(db, user, CompanyCode.INVESTMENT) -> frozenset[ResourceCode]`。
- Produces: `User.mobile: str | None`、`User.legal_alert_enabled: bool`。
- Produces: `UserUpdate.mobile` 和 `UserUpdate.legal_alert_enabled`，仍由 `require_superuser` 保护。

- [ ] **Step 1: 写权限与用户字段失败测试**

```python
def test_investment_business_and_risk_roles_have_full_legal_resources(self):
    for role in (Role.BUSINESS_HANDLER, Role.RISK_AUDITOR):
        db = Mock(); db.scalar.return_value = role
        resources = allowed_resources(db, SimpleNamespace(id=7, is_superuser=False), CompanyCode.INVESTMENT)
        self.assertIn(ResourceCode.INVEST_LEGAL_CASES, resources)
        self.assertIn(ResourceCode.INVEST_LEGAL_STATISTICS, resources)

def test_user_mobile_fields_are_superuser_managed(self):
    payload = UserUpdate(mobile="13800138000", legal_alert_enabled=True)
    self.assertEqual(payload.mobile, "13800138000")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_company_permissions tests.test_portal_api -v`

Expected: FAIL，提示投资公司法务资源或 `mobile` 字段不存在。

- [ ] **Step 3: 实现资源、门户和用户字段**

```python
INVEST_RESOURCE_ROLES = {
    ResourceCode.INVEST_LEGAL_DASHBOARD: frozenset(Role),
    ResourceCode.INVEST_LEGAL_CASES: frozenset(Role),
    ResourceCode.INVEST_LEGAL_ALERTS: frozenset(Role),
    ResourceCode.INVEST_LEGAL_STATISTICS: frozenset(Role),
    ResourceCode.INVEST_LEGAL_ADMIN: frozenset({Role.INFO_MAINTAINER}),
}

mobile: Mapped[str | None] = mapped_column(String(11), nullable=True)
legal_alert_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

将 `APPLICATIONS` 中投资公司状态改为 `online`；权限快照聚合用户在三家公司各自允许的资源，不再只查询供管公司。迁移使用 `ADD COLUMN IF NOT EXISTS` 的项目兼容写法并给手机号增加格式约束前的应用层校验。

- [ ] **Step 4: 运行权限和门户测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_company_permissions tests.test_portal_api -v`

Expected: PASS；供管资源回归测试仍通过，投资公司应用状态为 `online`。

- [ ] **Step 5: 暂存变更检查点（不提交）**

Run: `git diff --check -- backend/app/core/enums.py backend/app/services/permissions.py backend/app/services/portal.py backend/app/models/user.py backend/app/schemas/user.py backend/app/api/v1/endpoints/user.py backend/migrations/20260814_legal_risk_foundation.sql backend/tests/test_company_permissions.py backend/tests/test_portal_api.py`

Expected: 无空白错误。

### Task 2: 法务核心 ORM、枚举和 Schema

**Files:**
- Create: `backend/app/models/legal_risk.py`
- Create: `backend/app/schemas/legal_risk.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260814_legal_risk_domain.sql`
- Create: `backend/tests/test_legal_models.py`

**Interfaces:**
- Produces: `LegalCaseStage`, `LegalCaseStatus`, `LegalJudgmentType`, `LegalAlertStatus` 等字符串枚举。
- Produces: `LegalCase` 及 `LegalCaseParty|Collaborator|Judgment|Asset|Recovery|Progress|Deadline|Attachment|Alert|AlertDelivery|Activity|ImportBatch|ImportRow`。
- Produces: `LegalCaseCreate`, `LegalCaseUpdate`, `LegalCaseDetailOut`, `LegalPage[T]`。

- [ ] **Step 1: 写模型约束失败测试**

```python
def test_case_status_and_judgment_type_are_fixed(self):
    self.assertEqual([item.value for item in LegalCaseStatus], [
        "review_filing", "in_trial", "judged", "enforcement", "terminal", "closed",
    ])
    self.assertEqual([item.value for item in LegalJudgmentType], [
        "first_instance", "second_instance", "retrial", "mediation", "settlement",
    ])
    self.assertNotIn("risk_level", LegalCase.__table__.columns)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_models -v`

Expected: FAIL，提示 `app.models.legal_risk` 不存在。

- [ ] **Step 3: 定义法务模型和类型安全 Schema**

```python
class LegalCaseStatus(str, Enum):
    REVIEW_FILING = "review_filing"
    IN_TRIAL = "in_trial"
    JUDGED = "judged"
    ENFORCEMENT = "enforcement"
    TERMINAL = "terminal"
    CLOSED = "closed"

class LegalJudgmentType(str, Enum):
    FIRST_INSTANCE = "first_instance"
    SECOND_INSTANCE = "second_instance"
    RETRIAL = "retrial"
    MEDIATION = "mediation"
    SETTLEMENT = "settlement"
```

数据库唯一约束包括 `legal_case.case_no`、预警业务唯一键 `(case_id, source_type, source_id, alert_type, cycle_key)`、投递唯一键 `(alert_id, channel, stage_key, recipient_scope)`。所有金额使用 `Numeric(18, 2)`，所有业务明细含逻辑删除时间，正式状态允许为空但由应用层保证仅草稿为空。

- [ ] **Step 4: 执行模型测试和元数据导入检查**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_models -v`

Expected: PASS；`python -c "import app.models.legal_risk"` 退出码为 0。

- [ ] **Step 5: 校验 SQL 与 ORM 字段一致**

Run: `rg -n "risk_level|major_case|重大案件" backend/app/models/legal_risk.py backend/app/schemas/legal_risk.py backend/migrations/20260814_legal_risk_domain.sql`

Expected: 无匹配。

### Task 3: 法务权限服务、草稿、正式建档和生命周期 API

**Files:**
- Create: `backend/app/services/legal_permissions.py`
- Create: `backend/app/services/legal_cases.py`
- Create: `backend/app/api/v1/endpoints/legal_risk.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_legal_permissions.py`
- Create: `backend/tests/test_legal_cases_api.py`

**Interfaces:**
- Consumes: `LegalCase`、投资公司资源和 `get_company_role()`。
- Produces: `LegalCapability`、`LegalAccessContext`、`require_legal_capability(capability)`。
- Produces: `next_case_no(db, year) -> str`、`activate_case(db, case, actor) -> LegalCase`、`calculate_case_money(db, case_id) -> LegalMoneySummary`。
- Produces: `GET/POST /api/v1/legal-risk/cases`、`GET/PUT /cases/{id}`、`POST /cases/{id}/activate|status|archive|unarchive`。

- [ ] **Step 1: 写五身份权限矩阵和建档失败测试**

```python
def test_business_and_risk_have_same_full_scope(self):
    self.assertEqual(capabilities_for(Role.BUSINESS_HANDLER), capabilities_for(Role.RISK_AUDITOR))

def test_activate_requires_plaintiff_and_defendant(self):
    case = self._draft(parties=[self._party("plaintiff")])
    with self.assertRaises(LegalValidationError):
        activate_case(self.db, case, self.actor)

def test_management_role_is_read_only(self):
    self.assertNotIn(LegalCapability.EDIT_CASE, capabilities_for(Role.INVEST_DIRECTOR))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_permissions tests.test_legal_cases_api -v`

Expected: FAIL，提示服务或路由不存在。

- [ ] **Step 3: 实现能力矩阵、统一 403、建档和生命周期**

```python
FULL_CAPABILITIES = frozenset({
    LegalCapability.VIEW_CASE, LegalCapability.EDIT_CASE,
    LegalCapability.ACTIVATE_CASE, LegalCapability.MANAGE_DETAIL,
    LegalCapability.MANAGE_ALERT, LegalCapability.IMPORT_EXPORT,
})

def capabilities_for(role: Role | None, *, is_superuser: bool = False):
    if is_superuser or role in {Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER,
                               Role.RISK_AUDITOR, Role.FINANCE_HANDLER,
                               Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR}:
        return FULL_CAPABILITIES
    if role == Role.INVEST_DIRECTOR:
        return frozenset({LegalCapability.VIEW_CASE, LegalCapability.VIEW_STATISTICS,
                          LegalCapability.EXPORT_MANAGEMENT})
    return LEGAL_COUNSEL_CAPABILITIES if role == Role.LEGAL_COUNSEL else frozenset()
```

正式建档在事务中锁定当年编号序列、校验必填字段和原被告、生成 `AJ-YYYY-NNNN`，状态设为 `review_filing`。更新要求 `version` 相同后原子加一；归档检查已结案、结案资料和无活动预警；解除归档仅超管且强制原因。

- [ ] **Step 4: 运行案件与权限测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_permissions tests.test_legal_cases_api -v`

Expected: PASS；管理层写请求为 403，法律顾问未指派案件为 403，版本冲突和归档写入为 409。

- [ ] **Step 5: 检查路由注册和响应结构**

Run: `cd backend; ..\.venv\Scripts\python.exe -c "from app.main import create_app; print(any(r.path == '/api/v1/legal-risk/cases' for r in create_app().routes))"`

Expected: 输出 `True`。

### Task 4: 当事人、协同、裁判、资产、回款、进展和期限明细

**Files:**
- Modify: `backend/app/services/legal_cases.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Create: `backend/tests/test_legal_case_details.py`
- Create: `backend/tests/test_legal_money.py`

**Interfaces:**
- Produces: `/cases/{id}/parties|collaborators|judgments|assets|recoveries|progress|deadlines` CRUD。
- Produces: `set_current_enforcement_basis(db, case_id, judgment_id) -> None`。
- Produces: `LegalMoneySummary(subject_amount, executable_amount, recovered_amount, avoided_loss_amount, outstanding_amount)`。
- Produces: `mark_deadline_completed(db, deadline, result, actor) -> None`。

- [ ] **Step 1: 写裁判枚举、执行依据和金额口径失败测试**

```python
def test_settlement_is_supported_and_only_one_basis_exists(self):
    first = self.add_judgment("first_instance", Decimal("100.00"), True)
    settlement = self.add_judgment("settlement", Decimal("80.00"), True)
    self.db.flush()
    self.assertFalse(first.is_current_enforcement_basis)
    self.assertTrue(settlement.is_current_enforcement_basis)

def test_outstanding_uses_basis_and_never_goes_negative(self):
    summary = calculate_case_money(self.db, self.case.id)
    self.assertEqual(summary.outstanding_amount, Decimal("0.00"))
```

- [ ] **Step 2: 运行明细测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_case_details tests.test_legal_money -v`

Expected: FAIL，提示明细端点或金额函数不存在。

- [ ] **Step 3: 实现通用对象状态校验与明细 CRUD**

```python
def ensure_case_writable(case: LegalCase) -> None:
    if case.archived_at is not None:
        raise HTTPException(status_code=409, detail="案件已归档，不能修改")

outstanding = max((executable_amount or subject_amount) - recovered_amount, Decimal("0.00"))
```

所有写接口先执行能力、数据范围和归档检查。删除采用 `deleted_at`；当前执行依据切换在同一事务先清除旧值再设置新值；完成期限时同步完成同来源活动预警。

- [ ] **Step 4: 运行明细和金额测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_case_details tests.test_legal_money -v`

Expected: PASS；和解可写入且可成为执行依据，避免损失不计入累计回款。

- [ ] **Step 5: 全局扫描禁用口径**

Run: `rg -n "重大案件|major_case|risk_level" backend/app backend/tests`

Expected: 法务域无匹配；若旧模块存在同名文本，不修改旧模块。

### Task 5: 多附件鉴权存储和案件活动审计

**Files:**
- Create: `backend/app/services/legal_attachments.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Create: `backend/tests/test_legal_attachments.py`

**Interfaces:**
- Produces: `save_legal_attachment(db, upload, metadata, actor) -> LegalAttachment`。
- Produces: `authorized_attachment_path(db, attachment_id, actor) -> tuple[LegalAttachment, Path]`。
- Produces: `POST /legal-risk/attachments`、`GET /attachments/{id}/preview|download`、`DELETE /attachments/{id}`。

- [ ] **Step 1: 写类型、大小、路径和删除权限失败测试**

```python
def test_rejects_disallowed_extension_before_writing(self):
    with self.assertRaises(HTTPException) as raised:
        save_legal_attachment(self.db, fake_upload("payload.exe"), self.meta, self.actor)
    self.assertEqual(raised.exception.status_code, 400)

def test_counsel_can_only_delete_own_file_on_unarchived_assigned_case(self):
    self.assertFalse(can_delete_attachment(self.counsel, self.other_users_file, self.case))
```

- [ ] **Step 2: 运行附件测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_attachments -v`

Expected: FAIL，提示附件服务不存在。

- [ ] **Step 3: 实现分块写入、SHA-256 和鉴权响应**

```python
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024

storage_name = f"{uuid4().hex}{suffix}"
target = (legal_upload_root / storage_name).resolve()
if legal_upload_root.resolve() not in target.parents:
    raise HTTPException(status_code=400, detail="非法文件路径")
```

仅 PDF 和图片返回 `inline`，Word/Excel 预览端点返回 415 并提示下载。数据库提交失败删除本次新文件；逻辑删除不物理删除历史文件。预览和下载响应设置 `Cache-Control: no-store` 并写 `LegalCaseActivity`。

- [ ] **Step 4: 运行附件测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_attachments -v`

Expected: PASS；越权为 403，路径穿越被拒绝，数据库失败不残留新文件。

- [ ] **Step 5: 检查上传目录未被 Git 跟踪**

Run: `git check-ignore backend/uploads/legal-risk/probe.pdf`

Expected: 输出被忽略路径；若未输出，仅更新 `.gitignore` 增加 `backend/uploads/`，不删除任何现有上传文件。

### Task 6: 五类预警、钉钉加签投递和调度任务

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/legal_alerts.py`
- Create: `backend/app/services/dingtalk.py`
- Create: `backend/app/jobs/legal_alert_scan.py`
- Create: `backend/app/jobs/legal_alert_retry.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Create: `backend/tests/test_legal_alerts.py`
- Create: `backend/tests/test_dingtalk.py`
- Create: `deploy/sd-scm-legal-alert-scan.service`
- Create: `deploy/sd-scm-legal-alert-scan.timer`
- Create: `deploy/sd-scm-legal-alert-retry.service`
- Create: `deploy/sd-scm-legal-alert-retry.timer`

**Interfaces:**
- Produces: `scan_alerts(db, today: date) -> AlertScanResult`。
- Produces: `sync_source_alerts(db, source_type, source_id, today) -> list[LegalCaseAlert]`。
- Produces: `delivery_stages(alert, today) -> list[str]`。
- Produces: `DingTalkClient.send_alert(alert, case, responsible_user) -> DeliveryResult`。
- Produces: `/alerts`、`/alerts/counts`、`/alerts/{id}/start|complete|close|resend`、`/admin/scan-alerts|test-dingtalk`。

- [ ] **Step 1: 写五规则、防重、日期变更和钉钉失败测试**

```python
def test_overdue_delivery_repeats_every_seven_days(self):
    self.assertEqual(delivery_stages(self.alert, self.due + timedelta(days=1)), ["overdue-1"])
    self.assertEqual(delivery_stages(self.alert, self.due + timedelta(days=8)), ["overdue-2"])

def test_dingtalk_message_minimizes_case_information(self):
    body = build_alert_message(self.alert, self.case, days_left=3)
    self.assertIn(self.case.case_no, body)
    self.assertNotIn(self.case.case_name, body)
    self.assertNotIn(str(self.case.subject_amount), body)
```

- [ ] **Step 2: 运行预警测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_alerts tests.test_dingtalk -v`

Expected: FAIL，提示预警或钉钉服务不存在。

- [ ] **Step 3: 实现预警生成、阶段幂等、签名和重试**

```python
def sign_webhook(secret: str, timestamp_ms: int) -> str:
    raw = f"{timestamp_ms}\n{secret}".encode()
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return quote_plus(base64.b64encode(digest).decode())

RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=30), timedelta(minutes=120))
```

预警唯一键使用来源周期；来源日期修改时关闭未完成旧预警并生成新周期。日扫生成资产、执行、开庭、缴费/材料和终本月度预警；草稿直接跳过。投递先建立唯一阶段记录再发送，钉钉未配置记录 `channel_unconfigured`，不回滚业务事务。

- [ ] **Step 4: 运行预警和钉钉测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_alerts tests.test_dingtalk -v`

Expected: PASS；同阶段重复扫描不重复投递，手机号关闭时群消息仍发送但 `atMobiles=[]`。

- [ ] **Step 5: 校验 timer 时间与双 worker 隔离**

Run: `rg -n "OnCalendar|OnUnitActiveSec|legal_alert" deploy backend/app/main.py`

Expected: 日扫 timer 为 `*-*-* 09:00:00 Asia/Shanghai`，补偿 timer 为 5 分钟；`app/main.py` 不启动常驻调度器。

### Task 7: 工作台、状态统计、下钻和管理 Excel 导出

**Files:**
- Create: `backend/app/services/legal_statistics.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Create: `backend/tests/test_legal_statistics.py`

**Interfaces:**
- Produces: `LegalCaseFilters` 和 `build_case_query(filters, access)`，供列表、统计和导出共用。
- Produces: `dashboard_statistics(db, filters, access) -> LegalDashboardOut`。
- Produces: `status_statistics(db, filters, access) -> list[LegalStatusStatisticsOut]`。
- Produces: `GET /statistics/dashboard|status`、`GET /exports/cases.xlsx`。

- [ ] **Step 1: 写状态全集、草稿排除和口径一致性失败测试**

```python
def test_status_statistics_always_returns_six_statuses_and_total(self):
    rows = status_statistics(self.db, LegalCaseFilters(), self.access)
    self.assertEqual([row.status for row in rows[:-1]], list(LegalCaseStatus))
    self.assertEqual(rows[-1].status, "total")

def test_draft_is_excluded_from_dashboard(self):
    self.assertEqual(dashboard_statistics(self.db, LegalCaseFilters(), self.access).case_count, 0)
```

- [ ] **Step 2: 运行统计测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_statistics -v`

Expected: FAIL，提示统计服务不存在。

- [ ] **Step 3: 实现共享筛选查询和 Excel 审计页**

```python
STATUS_ORDER = tuple(LegalCaseStatus)
ratio = Decimal("0") if total_count == 0 else (Decimal(count) / Decimal(total_count))
```

工作台返回案件总量、审查立案、累计回款、待回款、未来 45 天资产、活动预警及时间清单。状态表固定六状态加合计，无数据补零。导出复用 `build_case_query`，工作簿新增“导出说明”表记录导出人、北京时间和筛选 JSON，并记录活动日志。

- [ ] **Step 4: 运行统计测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_statistics -v`

Expected: PASS；统计和明细 ID 集合一致，不含风险等级或重大案件列。

- [ ] **Step 5: 检查导出表头**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_statistics.LegalExportTest.test_export_headers -v`

Expected: PASS；表头包含案件编号、主状态、标的额、累计回款、待回款，不包含重大案件。

### Task 8: 标准 Excel 模板、预检和事务确认导入

**Files:**
- Create: `backend/app/services/legal_imports.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Create: `backend/tests/test_legal_imports.py`

**Interfaces:**
- Produces: `build_import_template() -> BytesIO`。
- Produces: `preview_import(db, file, actor) -> LegalCaseImportBatch`。
- Produces: `confirm_import(db, batch_id, actor, confirmed_warning_rows) -> ImportConfirmResult`。
- Produces: `GET /imports/template`、`POST /imports/preview`、`GET /imports/{id}`、`POST /imports/{id}/confirm`、`GET /imports/{id}/errors.xlsx`。

- [ ] **Step 1: 写模板工作表、跨表关联、警告和回滚失败测试**

```python
def test_template_contains_versioned_eight_sheets(self):
    workbook = load_workbook(build_import_template())
    self.assertEqual(workbook.sheetnames, [
        "案件基本信息", "当事人", "裁判结果", "查扣冻资产",
        "清回止损", "进展风险", "期限事件", "填写说明与枚举值",
    ])

def test_confirm_is_idempotent(self):
    confirm_import(self.db, self.batch.id, self.actor, [])
    with self.assertRaises(HTTPException) as raised:
        confirm_import(self.db, self.batch.id, self.actor, [])
    self.assertEqual(raised.exception.status_code, 409)
```

- [ ] **Step 2: 运行导入测试并确认失败**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_imports -v`

Expected: FAIL，提示导入服务不存在。

- [ ] **Step 3: 实现版本化模板、规范化和单事务确认**

```python
TEMPLATE_VERSION = "legal-case-v1"
SHEET_NAMES = ("案件基本信息", "当事人", "裁判结果", "查扣冻资产", "清回止损", "进展风险", "期限事件")

def normalize_text(value):
    return " ".join(str(value or "").strip().split())
```

预检只写批次和逐行 JSON，不写业务表；重复法院案号为警告，缺少名称、主状态或关联键为错误；确认前校验批次归属、状态和所有警告确认项，使用 `with db.begin_nested()` 写完整案件树，任一失败回滚整批。未确认批次清理函数按 7 天删除预检行和批次。

- [ ] **Step 4: 运行导入测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest tests.test_legal_imports -v`

Expected: PASS；无真实历史台账专用映射器，错误报告可被 openpyxl 打开。

- [ ] **Step 5: 扫描历史台账猜测代码**

Run: `rg -n "legacy|旧台账|合并单元格|split.*[,，、]" backend/app/services/legal_imports.py`

Expected: 无历史文件专用规则。

### Task 9: 投资公司布局、路由、API 客户端和预警状态

**Files:**
- Create: `frontend/src/layout/InvestmentLayout.vue`
- Create: `frontend/src/api/legalRisk.js`
- Create: `frontend/src/store/legalAlerts.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/router/routes.test.js`
- Create: `frontend/src/store/legalAlerts.test.js`

**Interfaces:**
- Consumes: `invest.legal.*` 资源和 `/api/v1/legal-risk` API。
- Produces: `useLegalAlertsStore()` 的 `count`, `importantAlerts`, `startPolling()`, `stopPolling()`, `refresh()`。
- Produces: `/investment/legal-risk/dashboard|cases|cases/:caseId|alerts|statistics` 路由。

- [ ] **Step 1: 读取前端设计技能并写路由/轮询失败测试**

Run: `Get-Content -Raw -Encoding UTF8 C:\Users\dell\.codex\skills\frontend-design\SKILL.md`

```javascript
it('mounts legal routes under InvestmentLayout', () => {
  expect(findRoute('/investment/legal-risk/cases').component).toBeDefined()
})

it('never creates duplicate polling timers', () => {
  store.startPolling(); store.startPolling()
  expect(vi.getTimerCount()).toBe(1)
})
```

- [ ] **Step 2: 运行前端测试并确认失败**

Run: `cd frontend; npm test -- --run src/router/routes.test.js src/store/legalAlerts.test.js`

Expected: FAIL，提示布局、路由或 store 不存在。

- [ ] **Step 3: 实现安静、密集的业务布局和请求封装**

```javascript
const LEGAL_BASE = '/legal-risk'
export const listCases = params => request.get(`${LEGAL_BASE}/cases`, { params })
export const getAlertCounts = () => request.get(`${LEGAL_BASE}/alerts/counts`)
```

布局使用现有色彩与 8px 以下圆角，侧栏导航使用 Element Plus 图标；桌面固定侧栏，窄屏为抽屉。角标每 30 秒刷新，仅进入投资应用时启动，组件卸载和登出时停止。

- [ ] **Step 4: 运行路由和 store 测试**

Run: `cd frontend; npm test -- --run src/router/routes.test.js src/store/legalAlerts.test.js`

Expected: PASS；无权限路由由现有导航守卫阻止。

- [ ] **Step 5: 构建检查**

Run: `cd frontend; npm run build`

Expected: Vite build 成功，无未解析模块。

### Task 10: 案件列表、草稿编辑和八标签详情

**Files:**
- Create: `frontend/src/views/legal-risk/CaseListView.vue`
- Create: `frontend/src/views/legal-risk/CaseEditorView.vue`
- Create: `frontend/src/views/legal-risk/CaseDetailView.vue`
- Create: `frontend/src/views/legal-risk/caseDetailTabs.js`
- Create: `frontend/src/views/legal-risk/CaseListView.test.js`
- Create: `frontend/src/views/legal-risk/CaseDetailView.test.js`

**Interfaces:**
- Consumes: `listCases`, `createCase`, `updateCase`, `activateCase`, 明细和附件 API。
- Produces: 统一草稿/正式案件筛选列表、版本冲突刷新提示、归档只读详情。

- [ ] **Step 1: 写固定状态、草稿行为、和解与归档只读失败测试**

```javascript
it('renders exactly six formal statuses', () => {
  expect(CASE_STATUS_OPTIONS.map(item => item.label)).toEqual([
    '审查立案', '审理中', '已判决', '执行中', '终本', '已结案'
  ])
})

it('includes settlement in judgment types and no risk level control', () => {
  expect(JUDGMENT_TYPE_OPTIONS.some(item => item.label === '和解')).toBe(true)
  expect(wrapper.text()).not.toContain('风险等级')
})
```

- [ ] **Step 2: 运行案件页面测试并确认失败**

Run: `cd frontend; npm test -- --run src/views/legal-risk/CaseListView.test.js src/views/legal-risk/CaseDetailView.test.js`

Expected: FAIL，提示页面文件不存在。

- [ ] **Step 3: 实现列表、分段表单和八标签详情**

```javascript
export const CASE_STATUS_OPTIONS = Object.freeze([
  { value: 'review_filing', label: '审查立案' },
  { value: 'in_trial', label: '审理中' },
  { value: 'judged', label: '已判决' },
  { value: 'enforcement', label: '执行中' },
  { value: 'terminal', label: '终本' },
  { value: 'closed', label: '已结案' }
])
```

草稿最少只要求案件名称，正式建档按钮展示缺失项；详情顶部固定关键指标，标签为基本信息、裁判结果、查扣冻资产、清回止损、进展风险、期限事件、案件材料、操作记录。子记录使用抽屉，金额右对齐，归档时隐藏所有写按钮。

- [ ] **Step 4: 运行案件页面测试**

Run: `cd frontend; npm test -- --run src/views/legal-risk/CaseListView.test.js src/views/legal-risk/CaseDetailView.test.js`

Expected: PASS；页面无“重大案件”和“风险等级”。

- [ ] **Step 5: 响应式布局静态检查**

Run: `rg -n "minmax|overflow-x|@media|letter-spacing" frontend/src/views/legal-risk frontend/src/layout/InvestmentLayout.vue`

Expected: 固定格式控件含稳定约束，`letter-spacing` 仅为 `0`，窄屏表格可滚动且按钮文本不溢出。

### Task 11: 工作台、预警、统计、导入和用户手机号界面

**Files:**
- Create: `frontend/src/views/legal-risk/DashboardView.vue`
- Create: `frontend/src/views/legal-risk/AlertsView.vue`
- Create: `frontend/src/views/legal-risk/StatisticsView.vue`
- Create: `frontend/src/views/legal-risk/ImportDialog.vue`
- Modify: `frontend/src/views/system/users.vue`
- Modify: `frontend/src/api/user.js`
- Create: `frontend/src/views/legal-risk/legalViews.test.js`

**Interfaces:**
- Consumes: 工作台、预警、统计、导入导出和管理员测试 API。
- Produces: 卡片下钻查询、预警处理闭环、钉钉测试、固定六状态表、两阶段导入交互。

- [ ] **Step 1: 写统计口径、预警处理和手机号权限失败测试**

```javascript
it('does not expose major-case metric or risk-level filters', () => {
  expect(wrapper.text()).not.toContain('重大案件')
  expect(wrapper.text()).not.toContain('风险等级')
})

it('requires a result before completing an alert', async () => {
  await wrapper.get('[data-test="complete-alert"]').trigger('click')
  expect(completeAlert).not.toHaveBeenCalled()
})
```

- [ ] **Step 2: 运行页面测试并确认失败**

Run: `cd frontend; npm test -- --run src/views/legal-risk/legalViews.test.js`

Expected: FAIL，提示视图不存在。

- [ ] **Step 3: 实现页面与超管手机号维护**

```javascript
const mobileRule = {
  validator: (_, value, callback) => !value || /^1[3-9]\d{9}$/.test(value)
    ? callback() : callback(new Error('请输入 11 位中国大陆手机号')),
  trigger: 'blur'
}
```

工作台卡片点击时带相同筛选跳转；预警完成/关闭必须填写处理结果；统计表固定六状态和合计；导入先展示可导入、警告、错误，再允许逐项确认警告。用户管理仅超管页面显示完整手机号编辑框和钉钉接收开关，非超管接口输出脱敏手机号。

- [ ] **Step 4: 运行页面和用户管理测试**

Run: `cd frontend; npm test -- --run src/views/legal-risk/legalViews.test.js src/router/routes.test.js`

Expected: PASS；钉钉配置缺失有明确反馈但不阻断站内预警。

- [ ] **Step 5: 完整前端测试和构建**

Run: `cd frontend; npm test -- --run; npm run build`

Expected: Vitest 全部通过，Vite 构建成功。

### Task 12: 回归、部署文档和验收证据

**Files:**
- Modify: `backend/README.md`
- Modify: `README.md`
- Modify: `deploy/sd-scm-backend.service`
- Create: `docs/legal-risk-operations.md`
- Create: `backend/tests/test_legal_risk_smoke.py`

**Interfaces:**
- Consumes: 前述全部 API、jobs、timer 和环境变量。
- Produces: 可重复的迁移、配置、扫描、重试、测试消息、回滚和验收命令。

- [ ] **Step 1: 写跨域烟雾测试**

```python
def test_draft_activate_alert_statistics_flow(self):
    draft_id = self.create_complete_draft()
    self.activate(draft_id)
    self.create_hearing(draft_id, days_from_now=5)
    self.scan_alerts()
    self.assertEqual(self.alert_count(), 1)
    self.assertEqual(self.statistics_total(), 1)
```

- [ ] **Step 2: 运行后端全量测试**

Run: `cd backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: 全部 PASS，无现有供管合同、审批、文旅台账回归。

- [ ] **Step 3: 写部署和运维文档**

```ini
Environment=DINGTALK_LEGAL_ALERT_ENABLED=false
Environment=DINGTALK_LEGAL_ALERT_WEBHOOK=
Environment=DINGTALK_LEGAL_ALERT_SECRET=
Environment=LEGAL_ALERT_TIMEZONE=Asia/Shanghai
```

`docs/legal-risk-operations.md` 必须给出数据库备份、两份 SQL 迁移顺序、systemd service/timer 安装、`daemon-reload`、启停、手工扫描、测试钉钉、日志查询和禁用钉钉回退步骤。README 将投资公司状态从建设中改为法务风控模块已上线。

- [ ] **Step 4: 运行最终静态与构建检查**

Run: `git diff --check`

Expected: 无空白错误。

Run: `rg -n "重大案件|major_case|risk_level" backend/app/models/legal_risk.py backend/app/schemas/legal_risk.py backend/app/services/legal_statistics.py frontend/src/views/legal-risk`

Expected: 无匹配。

Run: `cd frontend; npm run build`

Expected: 构建成功。

- [ ] **Step 5: 记录未执行的外部验收项**

```text
外部验收仅包括：生产 MySQL 迁移、真实钉钉机器人 webhook/secret 测试、生产 systemd timer 启用。
这些操作需要生产凭据或部署授权，不在本地代码完成过程中假设已执行。
```

Expected: 本地代码、单元测试、前端构建和静态检查全部完成；外部验收项在交付说明中明确列出。
