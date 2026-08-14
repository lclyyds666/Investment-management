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
    {"code": "external.legal", "name": "外聘法律顾问", "type": "external", "parent": None, "company_code": None, "sort_order": 90},
)


POSITION_CATALOG = (
    {"code": "investment.executive.chairman", "name": "董事长", "category": "executive"},
    {"code": "investment.executive.general_manager", "name": "总经理", "category": "executive"},
    {"code": "investment.executive.deputy_general_manager", "name": "副总经理", "category": "executive"},
    {"code": "investment.department.director", "name": "部门总监", "category": "department"},
    {"code": "investment.department.deputy_director", "name": "部门副总监", "category": "department"},
    {"code": "investment.department.senior_manager", "name": "高级经理", "category": "department"},
    {"code": "investment.department.middle_manager", "name": "中级经理", "category": "department"},
    {"code": "investment.department.junior_manager", "name": "初级经理", "category": "department"},
    {"code": "supply.business_handler", "name": "业务经办", "category": "business"},
    {"code": "supply.business_reviewer", "name": "业务复核", "category": "business"},
    {"code": "supply.company_leader", "name": "供应链公司负责人", "category": "business"},
    {"code": "supply.finance_handler", "name": "供应链财务经办", "category": "business"},
    {"code": "governance.supply_leader", "name": "供应链分管领导", "category": "governance"},
    {"code": "fund.chairman", "name": "基金公司董事长", "category": "executive"},
    {"code": "fund.general_manager", "name": "基金公司总经理", "category": "executive"},
    {"code": "governance.fund_leader", "name": "基金公司分管领导", "category": "governance"},
    {"code": "investment.duty.supply_risk_review", "name": "供应链风控复核", "category": "duty"},
    {"code": "investment.duty.supply_finance_review", "name": "供应链财务复核", "category": "duty"},
    {"code": "external.legal_counsel", "name": "外聘法律顾问", "category": "external"},
)


PERMISSION_CODES = (
    "supply.portal.enter", "supply.dashboard.view", "supply.operation.view", "supply.operation.create", "supply.operation.export",
    "supply.scenic.view", "supply.scenic.create", "supply.scenic.update", "supply.scenic.delete", "supply.scenic.review", "supply.scenic.export",
    "supply.finance.view", "supply.finance.update", "supply.finance.review", "supply.finance.export",
    "supply.contract.view", "supply.contract.create", "supply.contract.update", "supply.contract.delete", "supply.contract.submit", "supply.contract.review", "supply.contract.approve", "supply.contract.return", "supply.contract.export",
    "supply.approval.view", "supply.approval.create", "supply.approval.update", "supply.approval.delete", "supply.approval.submit", "supply.approval.review", "supply.approval.approve", "supply.approval.return", "supply.approval.export",
    "supply.customer.view", "supply.customer.create", "supply.customer.update", "supply.customer.delete", "supply.customer.export",
    "supply.channel.view", "supply.channel.configure", "organization.directory.view", "investment.portal.enter", "fund.portal.enter",
)


def _permission_catalog_item(code: str) -> dict[str, str]:
    resource, action = code.rsplit(".", 1)
    return {
        "code": code,
        "name": code,
        "resource": resource,
        "action": PermissionAction.VIEW.value if action == "enter" else action,
    }


PERMISSION_CATALOG = tuple(_permission_catalog_item(code) for code in PERMISSION_CODES)


SUPPLY_VIEW_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.startswith("supply.") and code.endswith(".view"))
SUPPLY_EXPORT_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.startswith("supply.") and code.endswith(".export"))

INVESTMENT_EXECUTIVE_POSITION_CODES = (
    "investment.executive.chairman",
    "investment.executive.general_manager",
    "investment.executive.deputy_general_manager",
)

INVESTMENT_EXECUTIVE_READ_PERMISSIONS = frozenset({
    "investment.portal.enter",
    "supply.portal.enter",
    "fund.portal.enter",
    "organization.directory.view",
}) | SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS


def _supply_grants(position_code: str, permission_codes: set[str] | frozenset[str]):
    return tuple(
        {"position_code": position_code, "permission_code": code, "data_scope": "company", "scope_ref": "supplymanagement"}
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


def seed_authorization_catalog(db: Session) -> None:
    """Insert only missing catalog rows, preserving administrator customizations."""
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
            organizations[item["code"]] = organization

        positions: dict[str, Position] = {}
        for item in POSITION_CATALOG:
            position = db.scalar(select(Position).where(Position.code == item["code"]))
            if position is None:
                position = Position(code=item["code"], name=item["name"], category=PositionCategory(item["category"]))
                db.add(position)
                db.flush()
            positions[item["code"]] = position

        permissions: dict[str, Permission] = {}
        for item in PERMISSION_CATALOG:
            permission = db.scalar(select(Permission).where(Permission.code == item["code"]))
            if permission is None:
                permission = Permission(
                    code=item["code"], name=item["name"], resource=item["resource"],
                    action=PermissionAction(item["action"]),
                )
                db.add(permission)
                db.flush()
            permissions[item["code"]] = permission

        for grant in POSITION_GRANTS:
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
        db.commit()
    except Exception:
        db.rollback()
        raise
