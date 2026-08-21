# 投资公司法务合同审批与组织权限改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将投资公司及子公司的合同和诉讼案件统一纳入投资公司法务风控平台，落地三套合同审批流程、组织岗位调整、中文权限模板和后端强制数据隔离。

**Architecture:** 业务记录持久化所属公司、发起组织和发起任职；统一归属服务校验创建主体，统一范围服务为合同和案件生成后端查询条件。合同工作流目录新增三套定义，候选人解析根据合同归属和节点规则动态限定组织、岗位与治理范围；前端继续使用指定审批链路弹窗，但流程节点由后端提交方案驱动。

**Tech Stack:** FastAPI、SQLAlchemy 2、Pydantic 2、MySQL 8、SQLite 测试、Vue 3、Pinia、Element Plus、Vitest。

## Global Constraints

- 执行前必须使用 `using-git-worktrees` 创建 `.worktrees/legal-contract-org-authorization`，基于包含设计提交 `e30a94f` 的 `main`；不得改写主工作区现有暂存和未跟踪文件。
- 投资公司其他部门流程固定为“经办部门负责人 → 外聘法律顾问 → 法务风控部 → 分管领导 → 总经理 → 单位主要负责人”。
- 子公司流程固定为“公司负责人 → 外聘法律顾问 → 法务风控部 → 分管领导”。
- 法务风控部流程固定为“经办部门负责人 → 外聘法律顾问 → 分管领导 → 总经理 → 单位主要负责人”。
- 页面显示“经办部门负责人”和“单位主要负责人”，候选人实际岗位分别为“部门主任”和“董事长”。
- 供管公司、基管公司、展威科技可创建合同和案件；新华置业只能创建案件。
- 投资公司普通部门按部门隔离，子公司按公司隔离，法务风控部和超级管理员查看全部。
- 已启动的 `supply.contract.v2` 实例保持原流程；不得改写历史节点、任务、动作和签名快照。
- 旧岗位内部编码保留，用户可见旧岗位名称必须消失。
- 所有数据范围校验必须在后端执行，前端隐藏按钮不能作为授权依据。

---

### Task 1: 组织岗位与中文权限目录

**Files:**
- Modify: `backend/app/core/enums.py`
- Modify: `backend/app/services/organization_catalog.py`
- Modify: `backend/app/services/organization_admin.py`
- Modify: `backend/app/schemas/organization_admin.py`
- Modify: `backend/app/api/v1/endpoints/organization.py`
- Modify: `backend/tests/test_organization_models.py`
- Modify: `backend/tests/test_organization_admin_api.py`
- Test: `backend/tests/test_company_permissions.py`

**Interfaces:**
- Produces: `CompanyCode.ZHANWEI`, `CompanyCode.XINHUA_PROPERTY`。
- Produces: `permission_catalog_item(code: str) -> dict[str, str]`，返回稳定英文编码和中文 `name`、`resource_name`。
- Produces: 新组织、岗位和岗位权限目录，供后续归属、工作流候选人及前端权限页使用。

- [ ] **Step 1: 写目录失败测试**

在 `backend/tests/test_organization_models.py` 增加目录断言：

```python
def test_legal_subsidiaries_and_position_names_are_canonical():
    organizations = {item["code"]: item for item in ORGANIZATION_CATALOG}
    positions = {item["code"]: item for item in POSITION_CATALOG}

    assert organizations["zhanwei"]["name"] == "山东展威科技有限公司"
    assert organizations["zhanwei"]["parent"] == "investment"
    assert organizations["xinhuaproperty"]["name"] == "山东新华置业有限公司"
    assert organizations["xinhuaproperty"]["parent"] == "investment"
    assert positions["investment.department.director"]["name"] == "部门主任"
    assert positions["investment.department.deputy_director"]["name"] == "部门副主任"
    assert positions["supply.company_leader"]["name"] == "供管公司负责人"
    assert positions["governance.supply_leader"]["name"] == "供管公司分管领导"
    assert "业务经办" not in {item["name"] for item in POSITION_CATALOG}
    assert "业务复核" not in {item["name"] for item in POSITION_CATALOG}
```

在 `backend/tests/test_organization_admin_api.py` 增加中文权限断言：

```python
def test_permission_catalog_exposes_chinese_names(client, superuser_headers):
    response = client.get("/api/v1/organizations/permissions", headers=superuser_headers)
    assert response.status_code == 200
    permissions = {item["code"]: item for item in response.json()["data"]}
    assert permissions["investment.legal.alerts.view"]["name"] == "法务预警查看"
    assert permissions["investment.legal.contracts.submit"]["name"] == "法务合同提交"
    assert permissions["investment.legal.contracts.submit"]["resource_name"] == "法务合同"
```

- [ ] **Step 2: 运行目录测试并确认失败**

Run: `cd backend && pytest tests/test_organization_models.py tests/test_organization_admin_api.py -q`

Expected: 新公司、新岗位或 `resource_name` 缺失导致失败。

- [ ] **Step 3: 实现目录、名称和新权限编码**

在 `backend/app/core/enums.py` 增加：

```python
class CompanyCode(str, Enum):
    INVESTMENT = "investment"
    SUPPLY_MANAGEMENT = "supplymanagement"
    FUND_MANAGEMENT = "fundmanagement"
    ZHANWEI = "zhanwei"
    XINHUA_PROPERTY = "xinhuaproperty"
```

在 `backend/app/services/organization_catalog.py` 使用中文资源和动作映射生成权限名称：

```python
PERMISSION_RESOURCE_NAMES = {
    "supply.portal": "供管平台",
    "supply.dashboard": "战略总览",
    "supply.operation": "经营数据",
    "supply.scenic": "文旅业务",
    "supply.finance": "智慧财务",
    "supply.contract": "旧供管合同",
    "supply.approval": "业务审批",
    "supply.customer": "客户档案",
    "supply.channel": "渠道配置",
    "investment.portal": "投资公司平台",
    "fund.portal": "基管公司平台",
    "investment.legal.dashboard": "法务工作台",
    "investment.legal.cases": "法务案件",
    "investment.legal.contracts": "法务合同",
    "investment.legal.alerts": "法务预警",
    "investment.legal.statistics": "法务统计",
    "investment.legal.admin": "法务管理",
    "organization.directory": "组织通讯录",
}

PERMISSION_ACTION_NAMES = {
    "view": "查看",
    "create": "新建",
    "update": "修改",
    "delete": "删除",
    "submit": "提交",
    "review": "审核",
    "approve": "通过",
    "return": "退回",
    "import": "导入",
    "export": "导出",
    "configure": "配置",
    "reassign": "改派",
    "audit": "审计",
    "enter": "进入",
}

def permission_catalog_item(code: str) -> dict[str, str]:
    resource, action = code.rsplit(".", 1)
    resource_name = PERMISSION_RESOURCE_NAMES.get(resource, resource)
    return {
        "code": code,
        "name": f"{resource_name}{PERMISSION_ACTION_NAMES[action]}",
        "resource": resource,
        "resource_name": resource_name,
        "action": PermissionAction.VIEW.value if action == "enter" else action,
    }
```

将法务合同权限加入目录：

```python
LEGAL_CONTRACT_PERMISSION_CODES = (
    "investment.legal.contracts.view",
    "investment.legal.contracts.create",
    "investment.legal.contracts.update",
    "investment.legal.contracts.delete",
    "investment.legal.contracts.submit",
    "investment.legal.contracts.review",
    "investment.legal.contracts.approve",
    "investment.legal.contracts.return",
    "investment.legal.contracts.export",
)
```

增加两家公司、展威五个岗位、新华五个岗位和设计文档列出的补充岗位。播种时只同步本目录明确管理的组织名称、岗位名称、权限名称和资源名称，不覆盖管理员自定义岗位授权。

新岗位编码固定为 `supply.senior_manager`、`investment.asset_finance.middle_manager`、`investment.asset_finance.senior_manager`、`investment.asset_finance.deputy_director`、`investment.legal_risk.deputy_director`、`zhanwei.general_manager`、`zhanwei.deputy_general_manager`、`zhanwei.senior_manager`、`zhanwei.middle_manager`、`zhanwei.junior_manager`、`xinhuaproperty.chairman`、`xinhuaproperty.general_manager`、`xinhuaproperty.deputy_general_manager`、`xinhuaproperty.department.director`、`xinhuaproperty.department.employee`、`governance.zhanwei_leader`。组织权限接口根据权限资源编码返回 `resource_name`，不向 `sys_permission` 增加重复列。

- [ ] **Step 4: 验证目录播种幂等性和现有授权兼容**

Run: `cd backend && pytest tests/test_organization_models.py tests/test_organization_admin_api.py tests/test_company_permissions.py -q`

Expected: PASS；连续两次调用 `seed_authorization_catalog` 后组织、岗位、权限和授权数量不变。

- [ ] **Step 5: 提交目录改造**

```bash
git add backend/app/core/enums.py backend/app/services/organization_catalog.py backend/app/services/organization_admin.py backend/app/schemas/organization_admin.py backend/app/api/v1/endpoints/organization.py backend/tests/test_organization_models.py backend/tests/test_organization_admin_api.py backend/tests/test_company_permissions.py
git commit -m "feat: seed legal organizations and Chinese permissions"
```

### Task 2: 合同与案件归属模型

**Files:**
- Create: `backend/app/services/legal_ownership.py`
- Modify: `backend/app/models/contract.py`
- Modify: `backend/app/models/legal_risk.py`
- Modify: `backend/app/schemas/contract.py`
- Modify: `backend/app/schemas/legal_risk.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Modify: `backend/tests/test_legal_models.py`
- Create: `backend/tests/test_legal_ownership.py`

**Interfaces:**
- Produces: `LegalResource = Literal["contract", "case"]`。
- Produces: `LegalInitiatorOption` 和 `LegalOwnership` 数据类。
- Produces: `legal_initiator_options(db, user, resource) -> list[LegalInitiatorOption]`。
- Produces: `resolve_legal_ownership(db, user, resource, initiator_assignment_id, organization_code) -> LegalOwnership`。
- Persists: `company_code`, `organization_code`, `initiator_assignment_id` on `Contract` and `LegalCase`。

- [ ] **Step 1: 写归属解析失败测试**

创建 `backend/tests/test_legal_ownership.py`：

```python
def test_subsidiary_contract_and_case_options_follow_company_policy(db, assigned_users):
    supply_user = assigned_users["supply_manager"]
    xinhua_user = assigned_users["xinhua_employee"]

    supply_contracts = legal_initiator_options(db, supply_user, "contract")
    supply_cases = legal_initiator_options(db, supply_user, "case")
    xinhua_contracts = legal_initiator_options(db, xinhua_user, "contract")
    xinhua_cases = legal_initiator_options(db, xinhua_user, "case")

    assert [item.company_code for item in supply_contracts] == ["supplymanagement"]
    assert [item.company_code for item in supply_cases] == ["supplymanagement"]
    assert xinhua_contracts == []
    assert [item.company_code for item in xinhua_cases] == ["xinhuaproperty"]


def test_normal_user_cannot_forge_initiator_assignment(db, assigned_users):
    with pytest.raises(LegalOwnershipError) as error:
        resolve_legal_ownership(
            db,
            assigned_users["supply_manager"],
            "contract",
            assigned_users["zhanwei_manager_assignment"].id,
            None,
        )
    assert error.value.code == "invalid_initiator_assignment"
```

- [ ] **Step 2: 运行归属测试并确认失败**

Run: `cd backend && pytest tests/test_legal_ownership.py tests/test_legal_models.py -q`

Expected: `legal_ownership` 模块和归属字段不存在。

- [ ] **Step 3: 实现归属字段和解析服务**

在两个模型中增加：

```python
company_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
organization_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
initiator_assignment_id: Mapped[int | None] = mapped_column(
    ForeignKey("sys_user_assignment.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
```

在 `backend/app/services/legal_ownership.py` 定义稳定接口：

```python
@dataclass(frozen=True)
class LegalInitiatorOption:
    assignment_id: int
    company_code: str
    company_name: str
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


@dataclass(frozen=True)
class LegalOwnership:
    company_code: str
    organization_code: str
    initiator_assignment_id: int | None


CONTRACT_COMPANIES = frozenset({"investment", "supplymanagement", "fundmanagement", "zhanwei"})
CASE_COMPANIES = CONTRACT_COMPANIES | frozenset({"xinhuaproperty"})
```

普通用户只能从本人有效任职生成选项；超级管理员可以通过 `organization_code` 选择有效业务组织，`initiator_assignment_id` 保持 `None`。增加 `GET /legal-risk/initiator-options?resource=contract|case`，返回当前用户可用发起任职。合同和案件创建接口在同一任务中调用归属服务，确保新增非空模型字段后既有接口测试仍能创建记录。

- [ ] **Step 4: 运行模型和归属测试**

Run: `cd backend && pytest tests/test_legal_models.py tests/test_legal_ownership.py -q`

Expected: PASS；新华置业合同选项为空，案件选项存在；伪造任职被拒绝。

- [ ] **Step 5: 提交归属基础**

```bash
git add backend/app/services/legal_ownership.py backend/app/models/contract.py backend/app/models/legal_risk.py backend/app/schemas/contract.py backend/app/schemas/legal_risk.py backend/app/api/v1/endpoints/contract.py backend/app/api/v1/endpoints/legal_risk.py backend/tests/test_legal_models.py backend/tests/test_legal_ownership.py
git commit -m "feat: persist legal record ownership"
```

### Task 3: 后端统一数据范围

**Files:**
- Create: `backend/app/services/legal_record_scope.py`
- Modify: `backend/app/services/legal_permissions.py`
- Modify: `backend/app/services/organization_catalog.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Modify: `backend/tests/test_legal_permissions.py`
- Modify: `backend/tests/test_legal_cases.py`
- Create: `backend/tests/test_contract_legal_scope.py`
- Modify: `backend/tests/test_legal_attachments.py`
- Modify: `backend/tests/test_legal_statistics.py`

**Interfaces:**
- Consumes: `LegalOwnership` fields from Task 2。
- Produces: `LegalRecordScope` with `global_access`, `company_codes`, `organization_codes`, `user_id`。
- Produces: `legal_record_scope(db, user) -> LegalRecordScope`。
- Produces: `contract_access_predicate(scope)`、`case_access_predicate(scope)`、`can_access_contract(db, contract, scope)`、`can_access_case(db, case, scope)`。

- [ ] **Step 1: 写合同和案件访问矩阵失败测试**

创建 `backend/tests/test_contract_legal_scope.py`：

```python
@pytest.mark.parametrize(
    ("actor_key", "visible_contracts"),
    [
        ("legal_risk_manager", {"INV-1", "SUP-1", "FUND-1", "ZW-1"}),
        ("investment_general_manager", {"INV-1"}),
        ("supply_manager", {"SUP-1"}),
        ("fund_manager", {"FUND-1"}),
        ("zhanwei_manager", {"ZW-1"}),
    ],
)
def test_contract_list_is_scoped_by_department_or_company(
    client, headers_by_actor, seeded_legal_contracts, actor_key, visible_contracts
):
    response = client.get("/api/v1/contracts", headers=headers_by_actor[actor_key])
    assert response.status_code == 200
    assert {item["contract_no"] for item in response.json()["data"]} == visible_contracts
```

在 `backend/tests/test_legal_cases.py` 增加同样的部门、公司和法务全量矩阵，并在 `backend/tests/test_legal_attachments.py` 断言跨公司附件下载返回 `404`。

- [ ] **Step 2: 运行范围测试并确认失败**

Run: `cd backend && pytest tests/test_contract_legal_scope.py tests/test_legal_cases.py tests/test_legal_attachments.py tests/test_legal_statistics.py -q`

Expected: 当前合同固定供管上下文、案件业务岗位全量可见，导致矩阵失败。

- [ ] **Step 3: 实现统一范围和能力到权限映射**

在 `backend/app/services/legal_record_scope.py` 定义：

```python
@dataclass(frozen=True)
class LegalRecordScope:
    user_id: int
    global_access: bool
    company_codes: frozenset[str]
    organization_codes: frozenset[str]


def legal_record_scope(db: Session, user: User) -> LegalRecordScope:
    assignments = active_assignments(db, user.id)
    legal_department = any(
        assignment.organization.code == "investment.legal_risk"
        for assignment in assignments
    )
    company_codes = frozenset(
        assignment.organization.company_code
        for assignment in assignments
        if assignment.organization.company_code and assignment.organization.code != "investment.legal_risk"
    )
    organization_codes = frozenset(
        assignment.organization.code
        for assignment in assignments
        if assignment.organization.organization_type == OrganizationType.DEPARTMENT
        and assignment.organization.code != "investment.legal_risk"
    )
    return LegalRecordScope(
        user_id=user.id,
        global_access=bool(user.is_active and user.is_superuser) or legal_department,
        company_codes=company_codes,
        organization_codes=organization_codes,
    )
```

合同范围额外包含提交人、指定审批人和已参与审批人；外聘法律顾问只能通过指定或参与条件进入。案件范围额外保留有效案件协同人员。所有合同和案件的列表、详情、附件、导出、统计、预警和写接口调用同一范围函数。

将 `LegalCapability` 映射到新的中文权限目录编码，能力判断通过 `has_permission` 聚合有效岗位授权，不再通过旧角色字符串授予全量案件能力。

- [ ] **Step 4: 运行范围与越权回归测试**

Run: `cd backend && pytest tests/test_legal_permissions.py tests/test_legal_cases.py tests/test_legal_attachments.py tests/test_legal_statistics.py tests/test_contract_legal_scope.py -q`

Expected: PASS；法务全量、部门按部门、子公司按公司、参与人按任务访问，跨范围详情和附件不可见。

- [ ] **Step 5: 提交范围服务**

```bash
git add backend/app/services/legal_record_scope.py backend/app/services/legal_permissions.py backend/app/services/organization_catalog.py backend/app/api/v1/endpoints/contract.py backend/app/api/v1/endpoints/legal_risk.py backend/tests/test_legal_permissions.py backend/tests/test_legal_cases.py backend/tests/test_contract_legal_scope.py backend/tests/test_legal_attachments.py backend/tests/test_legal_statistics.py
git commit -m "feat: enforce legal record data scopes"
```

### Task 4: 三套合同工作流与动态候选人

**Files:**
- Modify: `backend/app/models/workflow.py`
- Modify: `backend/app/schemas/workflow.py`
- Modify: `backend/app/services/workflow_catalog.py`
- Create: `backend/app/services/contract_workflow.py`
- Modify: `backend/app/services/workflow_engine.py`
- Modify: `backend/app/api/v1/endpoints/workflow.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Modify: `backend/tests/test_workflow_models.py`
- Modify: `backend/tests/test_workflow_engine.py`
- Modify: `backend/tests/test_workflow_api.py`
- Create: `backend/tests/test_contract_workflow_routing.py`

**Interfaces:**
- Consumes: 合同归属字段和范围服务。
- Produces: `investment.contract.department.v1`、`investment.contract.subsidiary.v1`、`investment.contract.legal-risk.v1`。
- Produces: `contract_workflow_code(contract: Contract) -> str`。
- Produces: `submission_plan(db, contract, submitter) -> WorkflowSubmissionPlan`。
- Changes: `start_workflow(..., workflow_code: str | None = None) -> WorkflowInstance`，旧目标不传时继续使用原映射。

- [ ] **Step 1: 写流程路由和候选人失败测试**

创建 `backend/tests/test_contract_workflow_routing.py`：

```python
@pytest.mark.parametrize(
    ("organization_code", "workflow_code", "node_names"),
    [
        (
            "investment.general",
            "investment.contract.department.v1",
            ["经办部门负责人", "外聘法律顾问", "法务风控部", "分管领导", "总经理", "单位主要负责人"],
        ),
        (
            "investment.legal_risk",
            "investment.contract.legal-risk.v1",
            ["经办部门负责人", "外聘法律顾问", "分管领导", "总经理", "单位主要负责人"],
        ),
        (
            "supplymanagement",
            "investment.contract.subsidiary.v1",
            ["公司负责人", "外聘法律顾问", "法务风控部", "分管领导"],
        ),
    ],
)
def test_contract_submission_plan_matches_owner(
    db, contract_factory, submitter_factory, organization_code, workflow_code, node_names
):
    contract, submitter = contract_factory(organization_code), submitter_factory(organization_code)
    plan = submission_plan(db, contract, submitter)
    assert plan.workflow_code == workflow_code
    assert [node.name for node in plan.nodes] == node_names
```

增加候选人测试，确保部门主任来自同一部门、法务节点来自 `investment.legal_risk`、治理岗位的 `scope_ref` 等于发起部门或公司、总经理和董事长来自投资公司。

- [ ] **Step 2: 运行工作流测试并确认失败**

Run: `cd backend && pytest tests/test_contract_workflow_routing.py tests/test_workflow_engine.py tests/test_workflow_api.py -q`

Expected: 三个流程代码、候选规则和提交方案不存在。

- [ ] **Step 3: 实现工作流目录和候选规则**

扩展目录节点：

```python
@dataclass(frozen=True)
class WorkflowCatalogNode:
    code: str
    name: str
    position_code: str
    mode: str
    candidate_rule: str = "position"
    candidate_position_codes: tuple[str, ...] = ()
    auto_complete_on_submit: bool = False
    allow_reject: bool = True
```

`WorkflowNode` 持久化 `candidate_rule: VARCHAR(32)` 和 `candidate_position_codes: JSON`。三套定义都包含序号 `0` 的隐藏发起节点 `initiator`，提交时使用合同的 `initiator_assignment_id` 快照真实组织和岗位；页面提交方案过滤该隐藏节点。

在 `backend/app/services/contract_workflow.py` 定义：

```python
DEPARTMENT_WORKFLOW = "investment.contract.department.v1"
SUBSIDIARY_WORKFLOW = "investment.contract.subsidiary.v1"
LEGAL_RISK_WORKFLOW = "investment.contract.legal-risk.v1"


def contract_workflow_code(contract: Contract) -> str:
    if contract.organization_code == "investment.legal_risk":
        return LEGAL_RISK_WORKFLOW
    if contract.company_code == "investment":
        return DEPARTMENT_WORKFLOW
    if contract.company_code in {"supplymanagement", "fundmanagement", "zhanwei"}:
        return SUBSIDIARY_WORKFLOW
    raise WorkflowValidationError(
        "contract_workflow_not_available",
        "该发起组织不能提交合同审批。",
        {"organization_code": contract.organization_code},
    )
```

候选规则固定支持 `same_department_head`、`external_legal_counsel`、`legal_risk_department`、`department_governance`、`company_head`、`company_governance`、`investment_general_manager`、`investment_chairman`。最终提交重新解析每个 `user_id` 的有效任职并验证与提交方案一致。

新增 `GET /workflows/submission-plan?target_type=contract&target_id={id}`，返回流程代码、流程名称、发起组织和可见节点；候选人接口增加 `target_type`、`target_id` 参数用于范围解析。

- [ ] **Step 4: 运行新旧工作流兼容测试**

Run: `cd backend && pytest tests/test_workflow_models.py tests/test_workflow_engine.py tests/test_workflow_api.py tests/test_contract_workflow_routing.py -q`

Expected: PASS；三套新流程正确，`supply.payment.v2`、`supply.business.v2` 和已启动的 `supply.contract.v2` 测试继续通过。

- [ ] **Step 5: 提交工作流改造**

```bash
git add backend/app/models/workflow.py backend/app/schemas/workflow.py backend/app/services/workflow_catalog.py backend/app/services/contract_workflow.py backend/app/services/workflow_engine.py backend/app/api/v1/endpoints/workflow.py backend/app/api/v1/endpoints/contract.py backend/tests/test_workflow_models.py backend/tests/test_workflow_engine.py backend/tests/test_workflow_api.py backend/tests/test_contract_workflow_routing.py
git commit -m "feat: route legal contract approval workflows"
```

### Task 5: 法务合同页面与指定审批链路

**Files:**
- Modify: `frontend/src/api/contract.js`
- Modify: `frontend/src/api/workflow.js`
- Modify: `frontend/src/api/legalRisk.js`
- Modify: `frontend/src/components/workflow/DesignatedApproverFields.vue`
- Modify: `frontend/src/components/workflow/DesignatedApproverFields.test.js`
- Modify: `frontend/src/views/contract/index.vue`
- Modify: `frontend/src/views/contract/index.test.js`
- Modify: `frontend/src/constants/business.js`

**Interfaces:**
- Consumes: `/legal-risk/initiator-options` and `/workflows/submission-plan`。
- Produces: `listLegalInitiatorOptions(resource)`。
- Produces: `getWorkflowSubmissionPlan(targetType, targetId)`。
- Changes: `DesignatedApproverFields` accepts `nodes`, `targetType`, `targetId` and emits the same `designated_users` map。

- [ ] **Step 1: 写合同归属和三流程弹窗失败测试**

在 `frontend/src/views/contract/index.test.js` 增加：

```javascript
it('requires an initiator assignment when several legal origins are available', async () => {
  legalApi.listLegalInitiatorOptions.mockResolvedValue([
    { assignment_id: 11, organization_code: 'investment.general', organization_name: '综合管理部', company_code: 'investment' },
    { assignment_id: 12, organization_code: 'supplymanagement', organization_name: '山东出版供应链管理有限公司', company_code: 'supplymanagement' }
  ])
  const wrapper = mountContractView()
  await flushPromises()
  wrapper.vm.openCreate()
  expect(wrapper.vm.form.initiator_assignment_id).toBeNull()
  expect(wrapper.vm.rules.initiator_assignment_id[0].required).toBe(true)
})


it('loads the server submission plan before opening the designated chain', async () => {
  workflowApi.getWorkflowSubmissionPlan.mockResolvedValue({
    workflow_code: 'investment.contract.department.v1',
    workflow_name: '投资公司部门合同审批',
    organization_name: '综合管理部',
    nodes: [
      { code: 'department_head', name: '经办部门负责人', position_name: '部门主任' },
      { code: 'chairman', name: '单位主要负责人', position_name: '董事长' }
    ]
  })
  const wrapper = mountContractView()
  await wrapper.vm.onSubmit({ id: 7, status: 'draft', workflow_instance_id: null })
  expect(workflowApi.getWorkflowSubmissionPlan).toHaveBeenCalledWith('contract', 7)
  expect(wrapper.vm.submitVisible).toBe(true)
  expect(wrapper.vm.submitNodes.map(node => node.name)).toEqual(['经办部门负责人', '单位主要负责人'])
})
```

- [ ] **Step 2: 运行合同组件测试并确认失败**

Run: `cd frontend && npm test -- --run src/views/contract/index.test.js src/components/workflow/DesignatedApproverFields.test.js`

Expected: 发起任职字段和服务器提交方案接口不存在。

- [ ] **Step 3: 实现归属表单和动态审批链**

合同新建表单增加 `initiator_assignment_id`。单个选项自动选择并只读展示；多个选项显示必选下拉。选择后将甲方名称默认更新为发起组织所属公司中文名，但用户仍可编辑合同甲方字段。

提交时执行：

```javascript
async function onSubmit(row) {
  if (row.workflow_instance_id && row.active_task?.node_code === 'initiator') {
    await submitContract(row.id)
    await load()
    return
  }
  submitCurrent.value = row
  submitPlan.value = await getWorkflowSubmissionPlan('contract', row.id)
  submitDesignatedUsers.value = {}
  submitVisible.value = true
}
```

确认提交继续发送：

```javascript
await submitContract(submitCurrent.value.id, {
  designated_users: { ...submitDesignatedUsers.value }
})
```

`DesignatedApproverFields` 不再硬编码三套新合同流程节点；合同节点来自 `submissionPlan.nodes`，付款和业务审批继续使用原有节点定义。

- [ ] **Step 4: 运行合同和工作流前端测试**

Run: `cd frontend && npm test -- --run src/views/contract/index.test.js src/components/workflow/DesignatedApproverFields.test.js src/api/workflow.test.js`

Expected: PASS；三类节点由后端方案展示，人员映射提交不变，候选人请求带目标记录。

- [ ] **Step 5: 提交合同前端**

```bash
git add frontend/src/api/contract.js frontend/src/api/workflow.js frontend/src/api/legalRisk.js frontend/src/components/workflow/DesignatedApproverFields.vue frontend/src/components/workflow/DesignatedApproverFields.test.js frontend/src/views/contract/index.vue frontend/src/views/contract/index.test.js frontend/src/constants/business.js
git commit -m "feat: submit legal contracts by organization"
```

### Task 6: 子公司案件创建与范围展示

**Files:**
- Modify: `backend/app/api/v1/endpoints/legal_risk.py`
- Modify: `backend/app/services/legal_cases.py`
- Modify: `backend/tests/test_legal_cases.py`
- Modify: `backend/tests/test_legal_imports.py`
- Modify: `frontend/src/api/legalRisk.js`
- Modify: `frontend/src/views/legal-risk/CaseEditorView.vue`
- Create: `frontend/src/views/legal-risk/CaseEditorView.test.js`
- Modify: `frontend/src/views/legal-risk/ImportDialog.vue`
- Modify: `frontend/src/views/legal-risk/CaseListView.vue`
- Modify: `frontend/src/views/legal-risk/CaseListView.test.js`

**Interfaces:**
- Consumes: Task 2 initiator options and Task 3 scope service。
- Changes: `LegalCaseCreate` requires a valid normal-user `initiator_assignment_id`; superuser submits `organization_code`。
- Produces: case list fields `company_name` and `organization_name`。

- [ ] **Step 1: 写案件发起组织前后端失败测试**

在 `frontend/src/views/legal-risk/CaseEditorView.test.js` 增加：

```javascript
it('auto-selects one case origin and submits its assignment id', async () => {
  api.listLegalInitiatorOptions.mockResolvedValue([
    { assignment_id: 51, company_code: 'xinhuaproperty', company_name: '山东新华置业有限公司', organization_code: 'xinhuaproperty', organization_name: '山东新华置业有限公司' }
  ])
  api.createCase.mockResolvedValue({ id: 9 })
  const wrapper = mountCaseEditor()
  await flushPromises()
  expect(wrapper.vm.form.initiator_assignment_id).toBe(51)
  await wrapper.vm.save()
  expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({ initiator_assignment_id: 51 }))
})
```

在 `backend/tests/test_legal_cases.py` 增加新华置业新建成功、合同新建失败和跨公司案件详情 `404` 测试。

- [ ] **Step 2: 运行案件测试并确认失败**

Run: `cd backend && pytest tests/test_legal_cases.py tests/test_legal_imports.py -q`

Run: `cd frontend && npm test -- --run src/views/legal-risk/CaseEditorView.test.js src/views/legal-risk/CaseListView.test.js`

Expected: 案件表单尚未提交归属，列表尚未显示组织名称。

- [ ] **Step 3: 实现案件创建、导入和列表归属**

创建案件时调用：

```python
ownership = resolve_legal_ownership(
    db,
    current_user,
    "case",
    payload.initiator_assignment_id,
    payload.organization_code,
)
case = LegalCase(
    **payload.model_dump(exclude={"initiator_assignment_id", "organization_code", "responsible_user_name"}),
    company_code=ownership.company_code,
    organization_code=ownership.organization_code,
    initiator_assignment_id=ownership.initiator_assignment_id,
    created_by=current_user.id,
)
```

Excel 导入弹窗先选择一个案件发起归属，并在预检与正式导入请求中传递该归属。导入批次为每行使用同一发起归属；预检和正式导入都重新校验。案件编辑不得更改已正式案件归属。案件列表增加所属公司和发起组织列，法务全量用户可按两列筛选。

- [ ] **Step 4: 运行案件完整相关测试**

Run: `cd backend && pytest tests/test_legal_cases.py tests/test_legal_imports.py tests/test_legal_attachments.py tests/test_legal_alerts.py tests/test_legal_statistics.py -q`

Run: `cd frontend && npm test -- --run src/views/legal-risk/CaseEditorView.test.js src/views/legal-risk/CaseListView.test.js src/views/legal-risk/legalRisk.test.js`

Expected: PASS；新华置业可建案件，子公司只见本公司，法务可见全部，导入数据具有归属。

- [ ] **Step 5: 提交案件归属界面**

```bash
git add backend/app/api/v1/endpoints/legal_risk.py backend/app/services/legal_cases.py backend/tests/test_legal_cases.py backend/tests/test_legal_imports.py frontend/src/api/legalRisk.js frontend/src/views/legal-risk/CaseEditorView.vue frontend/src/views/legal-risk/CaseEditorView.test.js frontend/src/views/legal-risk/ImportDialog.vue frontend/src/views/legal-risk/CaseListView.vue frontend/src/views/legal-risk/CaseListView.test.js
git commit -m "feat: scope subsidiary legal cases"
```

### Task 7: 法务导航和中文岗位权限页面

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/router/legacyRedirects.js`
- Modify: `frontend/src/router/routes.test.js`
- Modify: `frontend/src/layout/InvestmentLayout.vue`
- Modify: `frontend/src/layout/InvestmentLayout.test.js`
- Modify: `frontend/src/layout/index.test.js`
- Modify: `frontend/src/permission.js`
- Modify: `frontend/src/permission.test.js`
- Modify: `frontend/src/views/system/positions.vue`
- Modify: `frontend/src/views/system/positions.test.js`
- Modify: `frontend/src/store/organization.js`

**Interfaces:**
- Consumes: 法务合同资源 `invest.legal.contracts` 和中文 `resource_name`。
- Produces: `/investment/legal-risk/contracts` 正式路由。
- Produces: `/supplymanagement/contract` 到法务合同的兼容重定向。
- Produces: 中文类别、数据范围、业务域和权限资源标签。

- [ ] **Step 1: 写导航和中文权限失败测试**

在 `frontend/src/router/routes.test.js` 增加：

```javascript
it('moves contract management to the legal-risk application', () => {
  const legalContract = router.getRoutes().find(route => route.path === '/investment/legal-risk/contracts')
  const supplyContract = router.getRoutes().find(route => route.path === '/supplymanagement/contract')
  assert.equal(legalContract.meta.resource, 'invest.legal.contracts')
  assert.equal(supplyContract.redirect, '/investment/legal-risk/contracts')
})
```

在 `frontend/src/views/system/positions.test.js` 增加：

```javascript
it('renders Chinese category scope and resource labels', async () => {
  const wrapper = mount(PositionsView, { global: { stubs } })
  await flushPromises()
  expect(wrapper.text()).toContain('业务')
  expect(wrapper.text()).toContain('公司')
  expect(wrapper.text()).toContain('法务合同')
  expect(wrapper.text()).not.toContain('business_domain')
})
```

- [ ] **Step 2: 运行路由和权限页测试并确认失败**

Run: `cd frontend && npm test -- --run src/router/routes.test.js src/layout/InvestmentLayout.test.js src/layout/index.test.js src/permission.test.js src/views/system/positions.test.js`

Expected: 法务合同正式路由、旧地址跳转或中文标签至少一项缺失。

- [ ] **Step 3: 实现菜单归并和中文标签**

路由元数据使用：

```javascript
{
  path: 'legal-risk/contracts',
  name: 'LegalRiskContracts',
  component: () => import('@/views/contract/index.vue'),
  meta: {
    title: '合同管理',
    company: COMPANY_CODES.INVESTMENT,
    resource: RESOURCE_CODES.INVEST_LEGAL_CONTRACTS
  }
}
```

供管子路由不再注册合同页面，`legacyRedirects` 注册绝对路径重定向。`positions.vue` 使用下列映射，不直接显示英文枚举：

```javascript
const categoryLabels = {
  executive: '高管', department: '部门', business: '业务',
  governance: '治理', external: '外聘', duty: '职责'
}
const scopeLabels = {
  platform: '平台', company: '公司', department: '部门',
  business_domain: '业务域', own: '本人创建',
  participated: '本人参与', assigned: '指定给本人'
}
const businessDomainLabels = {
  investment: '投资公司', supply: '供管业务', fund: '基管业务'
}
```

- [ ] **Step 4: 运行导航、权限守卫和岗位页测试**

Run: `cd frontend && npm test -- --run src/router/routes.test.js src/layout/InvestmentLayout.test.js src/layout/index.test.js src/permission.test.js src/views/system/positions.test.js`

Expected: PASS；供管菜单无合同，法务菜单有合同，旧地址跳转，模板标签全中文。

- [ ] **Step 5: 提交导航和本地化**

```bash
git add frontend/src/router/index.js frontend/src/router/legacyRedirects.js frontend/src/router/routes.test.js frontend/src/layout/InvestmentLayout.vue frontend/src/layout/InvestmentLayout.test.js frontend/src/layout/index.test.js frontend/src/permission.js frontend/src/permission.test.js frontend/src/views/system/positions.vue frontend/src/views/system/positions.test.js frontend/src/store/organization.js
git commit -m "feat: move contracts into legal-risk navigation"
```

### Task 8: 数据库迁移、迁移报告与完整验证

**Files:**
- Create: `backend/migrations/20260821_legal_contract_organization_authorization.sql`
- Create: `backend/scripts/migrate_legal_contract_authorization.py`
- Create: `backend/tests/test_migrate_legal_contract_authorization.py`
- Modify: `backend/app/db/init_db.py`
- Modify: `backend/README.md`
- Modify: `README.md`
- Test: `backend/tests/test_init_db.py`

**Interfaces:**
- Consumes: Tasks 1–7 的模型、目录和工作流定义。
- Produces: 可重复执行的 MySQL 8 迁移。
- Produces: `python -m scripts.migrate_legal_contract_authorization --report PATH [--apply]`。
- Produces: JSON 报告字段 `organizations`, `positions`, `permissions`, `ownership_backfill`, `workflow_versions`, `blocking_issues`。

- [ ] **Step 1: 写迁移报告失败测试**

创建 `backend/tests/test_migrate_legal_contract_authorization.py`：

```python
def test_migration_preview_reports_backfill_without_writing(db, legacy_contract, legacy_case):
    report = build_report(db)
    assert report["ownership_backfill"] == {
        "contracts": 1,
        "cases": 1,
    }
    assert legacy_contract.company_code == ""
    assert legacy_case.company_code == ""


def test_migration_apply_is_idempotent(db, legacy_contract, legacy_case, publisher):
    first = apply_migration(db, publisher.id)
    second = apply_migration(db, publisher.id)
    assert first["blocking_issues"] == []
    assert second["ownership_backfill"] == {"contracts": 0, "cases": 0}
    assert legacy_contract.company_code == "supplymanagement"
    assert legacy_case.organization_code == "investment.legal_risk"
```

- [ ] **Step 2: 运行迁移测试并确认失败**

Run: `cd backend && pytest tests/test_migrate_legal_contract_authorization.py tests/test_init_db.py -q`

Expected: 迁移脚本和 SQL 尚不存在。

- [ ] **Step 3: 实现幂等 SQL 和预览/应用脚本**

SQL 必须通过 `information_schema` 守卫增加：

```sql
ALTER TABLE `biz_contract`
  ADD COLUMN `company_code` VARCHAR(64) NULL,
  ADD COLUMN `organization_code` VARCHAR(64) NULL,
  ADD COLUMN `initiator_assignment_id` INT NULL;

ALTER TABLE `legal_case`
  ADD COLUMN `company_code` VARCHAR(64) NULL,
  ADD COLUMN `organization_code` VARCHAR(64) NULL,
  ADD COLUMN `initiator_assignment_id` INT NULL;

ALTER TABLE `wf_node`
  ADD COLUMN `candidate_rule` VARCHAR(32) NOT NULL DEFAULT 'position',
  ADD COLUMN `candidate_position_codes` JSON NULL;

UPDATE `biz_contract`
SET `company_code` = 'supplymanagement', `organization_code` = 'supplymanagement'
WHERE `company_code` IS NULL OR `company_code` = '' OR `organization_code` IS NULL OR `organization_code` = '';

UPDATE `legal_case`
SET `company_code` = 'investment', `organization_code` = 'investment.legal_risk'
WHERE `company_code` IS NULL OR `company_code` = '' OR `organization_code` IS NULL OR `organization_code` = '';
```

实际迁移文件将每个 `ALTER` 拆为可重复执行的受保护语句，并在回填完成后把 `company_code`、`organization_code` 改为 `NOT NULL`，增加索引和 `initiator_assignment_id` 外键。脚本先生成预览报告；仅 `--apply` 时同步目录、回填归属并发布三套工作流。存在缺少超级管理员发布人、目录冲突或无法确认的活动任职时写入 `blocking_issues` 并拒绝应用。

- [ ] **Step 4: 运行完整验证**

Run: `cd backend && pytest -q`

Expected: 全部后端测试 PASS。

Run: `cd frontend && npm test -- --run`

Expected: 全部前端测试 PASS。

Run: `cd frontend && npm run build`

Expected: Vite 生产构建 PASS。

Run: `git diff --check`

Expected: 无空白错误。

- [ ] **Step 5: 提交迁移和文档**

```bash
git add backend/migrations/20260821_legal_contract_organization_authorization.sql backend/scripts/migrate_legal_contract_authorization.py backend/tests/test_migrate_legal_contract_authorization.py backend/app/db/init_db.py backend/README.md README.md
git commit -m "feat: migrate legal contract authorization"
```

### Task 9: 最终需求审查与交付准备

**Files:**
- Review: `docs/superpowers/specs/2026-08-21-investment-legal-contract-organization-authorization-design.md`
- Review: all files changed by Tasks 1–8

**Interfaces:**
- Consumes: 所有实现提交和测试结果。
- Produces: 需求覆盖清单、测试证据、迁移预览报告和部署说明。

- [ ] **Step 1: 对照设计逐项检查覆盖**

检查以下结果均有自动化测试和实现文件：三套流程、两个新组织、展威五岗、新华五岗、旧岗位中文名称替换、四家公司创建矩阵、部门/公司/法务数据范围、供管合同入口删除、中文权限模板、旧工作流兼容。

- [ ] **Step 2: 审查权限和数据泄露风险**

逐个检查合同和案件的列表、详情、附件、导出、统计、预警、修改、删除和提交接口，确认每个入口都调用 Task 3 的统一范围服务；搜索不得存在仅依赖前端 `v-if` 或固定 `supplymanagement` 上下文的法务合同授权。

Run: `rg -n "supply\.contract|PermissionContext\(company_code=.*supplymanagement|accessible_case_predicate|can_access_case" backend/app frontend/src`

Expected: 旧代码只出现在兼容逻辑、旧工作流和业务审批，不作为新法务合同入口授权。

- [ ] **Step 3: 生成迁移预览报告**

Run: `cd backend && python -m scripts.migrate_legal_contract_authorization --report ../.release-artifacts/legal-contract-authorization-preview.json`

Expected: `blocking_issues` 为空；报告只读，不改变数据库。

- [ ] **Step 4: 请求代码审查**

使用 `requesting-code-review` 技能审查设计符合性、数据隔离、历史兼容和测试覆盖；修复审查发现的本需求问题，并重新运行受影响测试。

- [ ] **Step 5: 完成分支收尾**

使用 `finishing-a-development-branch` 技能确认测试、构建、迁移预览和工作树状态，再由用户选择合并、推送或保留分支。不得自动提交或部署生产，除非用户明确要求。
