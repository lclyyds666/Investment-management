from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DataScope, OrganizationType, PermissionAction, PositionCategory
from app.models.organization import Organization, Permission, Position, PositionPermission


ORGANIZATION_CATALOG = (
    {"code": "investment", "name": "山东出版投资有限公司", "type": "company", "parent": None, "company_code": "investment", "sort_order": 10},
    {"code": "investment.general", "name": "综合管理部", "type": "department", "parent": "investment", "company_code": "investment", "sort_order": 11},
    {"code": "investment.investment_management", "name": "投资管理部", "type": "department", "parent": "investment", "company_code": "investment", "sort_order": 12},
    {"code": "investment.legal_risk", "name": "法务风控部", "type": "department", "parent": "investment", "company_code": "investment", "sort_order": 13},
    {"code": "investment.asset_finance", "name": "资产财务部", "type": "department", "parent": "investment", "company_code": "investment", "sort_order": 14},
    {"code": "supplymanagement", "name": "山东出版供应链管理有限公司", "type": "company", "parent": "investment", "company_code": "supplymanagement", "sort_order": 20},
    {"code": "fundmanagement", "name": "山东出版股权基金管理有限公司", "type": "company", "parent": "investment", "company_code": "fundmanagement", "sort_order": 30},
    {"code": "zhanwei", "name": "山东展威科技有限公司", "type": "company", "parent": "investment", "company_code": "zhanwei", "sort_order": 40},
    {"code": "xinhuaproperty", "name": "山东新华置业有限公司", "type": "company", "parent": "investment", "company_code": "xinhuaproperty", "sort_order": 50},
    {"code": "external.legal", "name": "外聘法律顾问", "type": "external", "parent": None, "company_code": None, "sort_order": 90},
)


POSITION_CATALOG = (
    {"code": "investment.executive.chairman", "name": "董事长", "category": "executive"},
    {"code": "investment.executive.general_manager", "name": "总经理", "category": "executive"},
    {"code": "investment.executive.deputy_general_manager", "name": "副总经理", "category": "executive"},
    {"code": "investment.department.director", "name": "部门主任", "category": "department"},
    {"code": "investment.department.deputy_director", "name": "部门副主任", "category": "department"},
    {"code": "investment.department.senior_manager", "name": "高级经理", "category": "department"},
    {"code": "investment.department.middle_manager", "name": "中级经理", "category": "department"},
    {"code": "investment.department.junior_manager", "name": "初级经理", "category": "department"},
    {"code": "supply.business_handler", "name": "供管公司初级经理", "category": "business"},
    {"code": "supply.business_reviewer", "name": "供管公司中级经理", "category": "business"},
    {"code": "supply.senior_manager", "name": "供管公司高级经理", "category": "business"},
    {"code": "supply.company_leader", "name": "供管公司负责人", "category": "business"},
    {"code": "supply.finance_handler", "name": "投资公司资产财务部初级经理", "category": "business"},
    {"code": "investment.asset_finance.middle_manager", "name": "投资公司资产财务部中级经理", "category": "department"},
    {"code": "investment.asset_finance.senior_manager", "name": "投资公司资产财务部高级经理", "category": "department"},
    {"code": "investment.asset_finance.deputy_director", "name": "投资公司资产财务部副主任", "category": "department"},
    {"code": "governance.supply_leader", "name": "供管公司分管领导", "category": "governance"},
    {"code": "fund.chairman", "name": "基金公司董事长", "category": "executive"},
    {"code": "fund.general_manager", "name": "基金公司总经理", "category": "executive"},
    {"code": "governance.fund_leader", "name": "基金公司分管领导", "category": "governance"},
    {"code": "investment.duty.supply_risk_review", "name": "投资公司法务风控部主任", "category": "duty"},
    {"code": "investment.legal_risk.deputy_director", "name": "投资公司法务风控部副主任", "category": "department"},
    {"code": "investment.duty.supply_finance_review", "name": "投资公司资产财务部主任", "category": "duty"},
    {"code": "zhanwei.general_manager", "name": "总经理", "category": "executive"},
    {"code": "zhanwei.deputy_general_manager", "name": "副总经理", "category": "executive"},
    {"code": "zhanwei.senior_manager", "name": "高级经理", "category": "business"},
    {"code": "zhanwei.middle_manager", "name": "中级经理", "category": "business"},
    {"code": "zhanwei.junior_manager", "name": "初级经理", "category": "business"},
    {"code": "xinhuaproperty.chairman", "name": "董事长", "category": "executive"},
    {"code": "xinhuaproperty.general_manager", "name": "总经理", "category": "executive"},
    {"code": "xinhuaproperty.deputy_general_manager", "name": "副总经理", "category": "executive"},
    {"code": "xinhuaproperty.department.director", "name": "部门主任", "category": "department"},
    {"code": "xinhuaproperty.department.employee", "name": "部门员工", "category": "department"},
    {"code": "governance.zhanwei_leader", "name": "展威科技分管领导", "category": "governance"},
    {"code": "external.legal_counsel", "name": "外聘法律顾问", "category": "external"},
)


LEGAL_CONTRACT_PERMISSION_CODES = (
    "investment.legal.contracts.view", "investment.legal.contracts.create",
    "investment.legal.contracts.update", "investment.legal.contracts.delete",
    "investment.legal.contracts.submit", "investment.legal.contracts.review",
    "investment.legal.contracts.approve", "investment.legal.contracts.return",
    "investment.legal.contracts.export",
)

LEGAL_CASE_PERMISSION_CODES = (
    "investment.legal.cases.view", "investment.legal.cases.create",
    "investment.legal.cases.update", "investment.legal.cases.delete",
    "investment.legal.cases.review", "investment.legal.cases.import",
    "investment.legal.cases.export",
)


PERMISSION_CODES = (
    "supply.portal.enter", "supply.dashboard.view", "supply.operation.view", "supply.operation.create", "supply.operation.export",
    "supply.scenic.view", "supply.scenic.create", "supply.scenic.update", "supply.scenic.delete", "supply.scenic.review", "supply.scenic.export",
    "supply.finance.view", "supply.finance.update", "supply.finance.review", "supply.finance.export",
    "supply.contract.view", "supply.contract.create", "supply.contract.update", "supply.contract.delete", "supply.contract.submit", "supply.contract.review", "supply.contract.approve", "supply.contract.return", "supply.contract.export",
    "supply.approval.view", "supply.approval.create", "supply.approval.update", "supply.approval.delete", "supply.approval.submit", "supply.approval.review", "supply.approval.approve", "supply.approval.return", "supply.approval.export",
    "supply.customer.view", "supply.customer.create", "supply.customer.update", "supply.customer.delete", "supply.customer.export",
    "supply.channel.view", "supply.channel.configure", "organization.directory.view", "investment.portal.enter", "fund.portal.enter",
    "investment.legal.dashboard.view", *LEGAL_CASE_PERMISSION_CODES,
    "investment.legal.alerts.view", "investment.legal.alerts.update",
    "investment.legal.statistics.view", "investment.legal.admin.view",
    *LEGAL_CONTRACT_PERMISSION_CODES,
)


PERMISSION_RESOURCE_NAMES = {
    "supply.portal": "供管平台", "supply.dashboard": "战略总览", "supply.operation": "经营数据",
    "supply.scenic": "文旅业务", "supply.finance": "智慧财务", "supply.contract": "旧供管合同",
    "supply.approval": "业务审批", "supply.customer": "客户档案", "supply.channel": "渠道配置",
    "investment.portal": "投资公司平台", "fund.portal": "基管公司平台",
    "investment.legal.dashboard": "法务工作台", "investment.legal.cases": "法务案件",
    "investment.legal.contracts": "法务合同", "investment.legal.alerts": "法务预警",
    "investment.legal.statistics": "法务统计", "investment.legal.admin": "法务管理",
    "organization.directory": "组织通讯录",
}

PERMISSION_ACTION_NAMES = {
    "view": "查看", "create": "新建", "update": "修改", "delete": "删除", "submit": "提交",
    "review": "审核", "approve": "通过", "return": "退回", "import": "导入", "export": "导出",
    "configure": "配置", "reassign": "改派", "audit": "审计", "enter": "进入",
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


PERMISSION_CATALOG = tuple(permission_catalog_item(code) for code in PERMISSION_CODES)


SUPPLY_VIEW_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.startswith("supply.") and code.endswith(".view"))
SUPPLY_EXPORT_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.startswith("supply.") and code.endswith(".export"))

INVESTMENT_EXECUTIVE_POSITION_CODES = (
    "investment.executive.chairman",
    "investment.executive.general_manager",
    "investment.executive.deputy_general_manager",
)

LEGAL_BUSINESS_VIEW_PERMISSIONS = frozenset({
    "investment.legal.dashboard.view",
    "investment.legal.cases.view",
    "investment.legal.alerts.view",
    "investment.legal.statistics.view",
})
LEGAL_COUNSEL_VIEW_PERMISSIONS = frozenset({
    "investment.legal.cases.view",
    "investment.legal.alerts.view",
})

LEGAL_BUSINESS_POSITION_CODES = (
    "investment.department.director",
    "investment.department.deputy_director",
    "investment.department.senior_manager",
    "investment.department.middle_manager",
    "investment.department.junior_manager",
    "supply.business_handler",
    "supply.business_reviewer",
    "supply.finance_handler",
    "supply.company_leader",
    "investment.duty.supply_risk_review",
    "investment.duty.supply_finance_review",
    "investment.asset_finance.middle_manager",
    "investment.asset_finance.senior_manager",
    "investment.asset_finance.deputy_director",
    "investment.legal_risk.deputy_director",
    "supply.senior_manager",
    "fund.chairman",
    "fund.general_manager",
    "zhanwei.general_manager",
    "zhanwei.deputy_general_manager",
    "zhanwei.senior_manager",
    "zhanwei.middle_manager",
    "zhanwei.junior_manager",
    "xinhuaproperty.chairman",
    "xinhuaproperty.general_manager",
    "xinhuaproperty.deputy_general_manager",
    "xinhuaproperty.department.director",
    "xinhuaproperty.department.employee",
)
LEGAL_MANAGEMENT_POSITION_CODES = (
    *INVESTMENT_EXECUTIVE_POSITION_CODES,
    "governance.supply_leader",
    "governance.fund_leader",
    "governance.zhanwei_leader",
)
LEGAL_COUNSEL_POSITION_CODES = ("external.legal_counsel",)
LEGAL_ACCESS_POSITION_CODES = tuple(dict.fromkeys(
    (*LEGAL_BUSINESS_POSITION_CODES, *LEGAL_MANAGEMENT_POSITION_CODES, *LEGAL_COUNSEL_POSITION_CODES)
))

LEGAL_CASE_BUSINESS_PERMISSIONS = frozenset(LEGAL_CASE_PERMISSION_CODES) | frozenset({
    "investment.legal.dashboard.view",
    "investment.legal.alerts.view",
    "investment.legal.alerts.update",
    "investment.legal.statistics.view",
})
LEGAL_CASE_MANAGEMENT_PERMISSIONS = frozenset({
    "investment.legal.dashboard.view",
    "investment.legal.cases.view",
    "investment.legal.cases.export",
    "investment.legal.alerts.view",
    "investment.legal.statistics.view",
})
LEGAL_CASE_COUNSEL_PERMISSIONS = frozenset({
    "investment.legal.cases.view",
    "investment.legal.cases.review",
    "investment.legal.alerts.view",
    "investment.legal.alerts.update",
})

LEGAL_CONTRACT_CREATOR_POSITION_CODES = tuple(
    position_code
    for position_code in LEGAL_BUSINESS_POSITION_CODES
    if not position_code.startswith("xinhuaproperty.")
)


def _legal_grants(position_codes, permission_codes, *, data_scope="company"):
    return tuple(
        {
            "position_code": position_code,
            "permission_code": permission_code,
            "data_scope": data_scope,
            "scope_ref": "investment" if data_scope == "company" else "",
        }
        for position_code in position_codes
        for permission_code in sorted(permission_codes)
    )

INVESTMENT_EXECUTIVE_READ_PERMISSIONS = frozenset({
    "investment.portal.enter",
    "supply.portal.enter",
    "fund.portal.enter",
    "organization.directory.view",
}) | SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS | LEGAL_BUSINESS_VIEW_PERMISSIONS


def _supply_grants(position_code: str, permission_codes: set[str] | frozenset[str]):
    return tuple(
        {"position_code": position_code, "permission_code": code, "data_scope": "company", "scope_ref": "supplymanagement"}
        for code in sorted(permission_codes)
    )


def _legal_view_grants(position_codes, permission_codes):
    return tuple(
        {
            "position_code": position_code,
            "permission_code": code,
            "data_scope": "company",
            "scope_ref": "investment",
        }
        for position_code in position_codes
        for code in sorted(permission_codes)
    )


def _investment_executive_grants():
    portal_scopes = {
        "investment.portal.enter": "investment",
        "supply.portal.enter": "supplymanagement",
        "fund.portal.enter": "fundmanagement",
    }
    return tuple(
        {
            "position_code": position_code,
            "permission_code": permission_code,
            "data_scope": "platform",
            "scope_ref": scope_ref,
        }
        for position_code in INVESTMENT_EXECUTIVE_POSITION_CODES
        for permission_code, scope_ref in portal_scopes.items()
    ) + tuple(
        {
            "position_code": position_code,
            "permission_code": permission_code,
            "data_scope": "company",
            "scope_ref": "supplymanagement",
        }
        for position_code in INVESTMENT_EXECUTIVE_POSITION_CODES
        for permission_code in sorted(SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS)
    )


POSITION_GRANTS = (
    *(
        {
            "position_code": position_code,
            "permission_code": "supply.portal.enter",
            "data_scope": "platform",
            "scope_ref": "supplymanagement",
        }
        for position_code in (
            "supply.business_handler",
            "supply.business_reviewer",
            "supply.finance_handler",
            "supply.company_leader",
            "governance.supply_leader",
            "investment.duty.supply_risk_review",
            "investment.duty.supply_finance_review",
            "external.legal_counsel",
        )
    ),
    *_supply_grants("supply.business_handler", SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS | {
        "supply.operation.create",
        "supply.scenic.create", "supply.scenic.update", "supply.scenic.delete",
        "supply.contract.create", "supply.contract.update", "supply.contract.delete", "supply.contract.submit",
        "supply.approval.create", "supply.approval.update", "supply.approval.delete", "supply.approval.submit",
        "supply.customer.create", "supply.customer.update", "supply.customer.delete", "supply.finance.update",
    }),
    *_supply_grants("supply.business_reviewer", SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS | {
        "supply.scenic.review", "supply.approval.review", "supply.approval.return",
    }),
    *_supply_grants("supply.finance_handler", SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS | {
        "supply.finance.update", "supply.finance.review", "supply.approval.review", "supply.approval.return",
    }),
    *_supply_grants("supply.company_leader", SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS | {
        "supply.contract.approve", "supply.contract.return", "supply.approval.approve", "supply.approval.return", "supply.channel.configure",
    }),
    *_supply_grants("governance.supply_leader", SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS | {
        "supply.contract.approve", "supply.contract.return", "supply.approval.approve", "supply.approval.return", "supply.channel.configure",
    }),
    *_supply_grants("investment.duty.supply_risk_review", {
        "supply.dashboard.view", "supply.operation.view", "supply.contract.view", "supply.approval.view", "supply.customer.view",
        "supply.contract.review", "supply.contract.approve", "supply.contract.return", "supply.approval.review", "supply.approval.approve", "supply.approval.return",
    }),
    *_supply_grants("investment.duty.supply_finance_review", {
        "supply.dashboard.view", "supply.operation.view", "supply.finance.view", "supply.contract.view", "supply.approval.view",
        "supply.finance.review", "supply.approval.review", "supply.approval.approve", "supply.approval.return",
    }),
    {"position_code": "external.legal_counsel", "permission_code": "supply.contract.view", "data_scope": "assigned", "scope_ref": ""},
    {"position_code": "external.legal_counsel", "permission_code": "supply.contract.review", "data_scope": "assigned", "scope_ref": ""},
    *_investment_executive_grants(),
    *(
        {
            "position_code": position_code,
            "permission_code": "investment.portal.enter",
            "data_scope": "platform",
            "scope_ref": "investment",
        }
        for position_code in LEGAL_ACCESS_POSITION_CODES
        if position_code not in INVESTMENT_EXECUTIVE_POSITION_CODES
    ),
    *_legal_grants(LEGAL_BUSINESS_POSITION_CODES, LEGAL_CASE_BUSINESS_PERMISSIONS),
    *_legal_grants(LEGAL_MANAGEMENT_POSITION_CODES, LEGAL_CASE_MANAGEMENT_PERMISSIONS),
    *_legal_grants(LEGAL_COUNSEL_POSITION_CODES, LEGAL_CASE_COUNSEL_PERMISSIONS, data_scope="assigned"),
    *_legal_grants(LEGAL_CONTRACT_CREATOR_POSITION_CODES, LEGAL_CONTRACT_PERMISSION_CODES),
    *_legal_grants(LEGAL_MANAGEMENT_POSITION_CODES, {
        "investment.legal.contracts.view", "investment.legal.contracts.export",
        "investment.legal.contracts.review", "investment.legal.contracts.approve",
        "investment.legal.contracts.return",
    }),
    *_legal_grants(LEGAL_COUNSEL_POSITION_CODES, {
        "investment.legal.contracts.view", "investment.legal.contracts.review",
        "investment.legal.contracts.return",
    }, data_scope="assigned"),
    {"position_code": "fund.chairman", "permission_code": "fund.portal.enter", "data_scope": "platform", "scope_ref": "fundmanagement"},
    {"position_code": "fund.general_manager", "permission_code": "fund.portal.enter", "data_scope": "platform", "scope_ref": "fundmanagement"},
    *(
        {
            "position_code": item["code"],
            "permission_code": "organization.directory.view",
            "data_scope": "company",
            "scope_ref": "supplymanagement",
        }
        for item in POSITION_CATALOG
        if item["category"] != PositionCategory.EXTERNAL.value
    ),
)


def seed_authorization_catalog(db: Session, *, commit: bool = True) -> None:
    """Seed catalog rows and refresh managed labels without replacing grants."""
    try:
        organizations: dict[str, Organization] = {}
        for item in ORGANIZATION_CATALOG:
            organization = db.scalar(select(Organization).where(Organization.code == item["code"]))
            if organization is None:
                organization = Organization(
                    code=item["code"], name=item["name"], organization_type=OrganizationType(item["type"]),
                    parent_id=organizations[item["parent"]].id if item["parent"] else None,
                    company_code=item["company_code"], sort_order=item["sort_order"],
                )
                db.add(organization)
                db.flush()
            else:
                organization.name = item["name"]
            organizations[item["code"]] = organization

        positions: dict[str, Position] = {}
        created_position_codes: set[str] = set()
        for item in POSITION_CATALOG:
            position = db.scalar(select(Position).where(Position.code == item["code"]))
            if position is None:
                position = Position(code=item["code"], name=item["name"], category=PositionCategory(item["category"]))
                db.add(position)
                db.flush()
                created_position_codes.add(position.code)
            else:
                position.name = item["name"]
            positions[item["code"]] = position

        permissions: dict[str, Permission] = {}
        created_permission_codes: set[str] = set()
        for item in PERMISSION_CATALOG:
            permission = db.scalar(select(Permission).where(Permission.code == item["code"]))
            if permission is None:
                permission = Permission(
                    code=item["code"], name=item["name"], resource=item["resource"],
                    action=PermissionAction(item["action"]),
                )
                db.add(permission)
                db.flush()
                created_permission_codes.add(permission.code)
            else:
                permission.name = item["name"]
                permission.resource = item["resource"]
            permissions[item["code"]] = permission

        for grant in POSITION_GRANTS:
            if (
                grant["position_code"] not in created_position_codes
                and grant["permission_code"] not in created_permission_codes
            ):
                continue
            position = positions[grant["position_code"]]
            permission = permissions[grant["permission_code"]]
            existing = db.scalar(select(PositionPermission).where(
                PositionPermission.position_id == position.id,
                PositionPermission.permission_id == permission.id,
                PositionPermission.data_scope == DataScope(grant["data_scope"]),
                PositionPermission.scope_ref == grant["scope_ref"],
            ))
            if existing is None:
                db.add(PositionPermission(
                    position_id=position.id, permission_id=permission.id,
                    data_scope=DataScope(grant["data_scope"]), scope_ref=grant["scope_ref"],
                ))
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise
