"""全局枚举定义（生产商用级 · 7 级组织角色与审批链）。"""
from enum import Enum


class Role(str, Enum):
    """系统角色（7 级严格权限）。

    角色顺序即合规审批流的逐级流转顺序，见 :data:`APPROVAL_CHAIN`。
    """

    BUSINESS_HANDLER = "business_handler"      # 业务经办：合同源头录入与提交
    BUSINESS_REVIEWER = "business_reviewer"    # 业务复核
    RISK_AUDITOR = "risk_auditor"              # 风控审核
    FINANCE_HANDLER = "finance_handler"        # 财务经办
    FINANCE_REVIEWER = "finance_reviewer"      # 财务复核
    SCM_DIRECTOR = "scm_director"              # 供管公司负责人
    INVEST_DIRECTOR = "invest_director"        # 投资公司负责人

    @property
    def label(self) -> str:
        return ROLE_LABELS[self]


# 角色中文名
ROLE_LABELS: dict[Role, str] = {
    Role.BUSINESS_HANDLER: "业务经办",
    Role.BUSINESS_REVIEWER: "业务复核",
    Role.RISK_AUDITOR: "风控审核",
    Role.FINANCE_HANDLER: "财务经办",
    Role.FINANCE_REVIEWER: "财务复核",
    Role.SCM_DIRECTOR: "供管公司负责人",
    Role.INVEST_DIRECTOR: "投资公司负责人",
}

# 7 级审批链：列表顺序 == 逐级流转顺序（index 即 step）
APPROVAL_CHAIN: list[Role] = [
    Role.BUSINESS_HANDLER,
    Role.BUSINESS_REVIEWER,
    Role.RISK_AUDITOR,
    Role.FINANCE_HANDLER,
    Role.FINANCE_REVIEWER,
    Role.SCM_DIRECTOR,
    Role.INVEST_DIRECTOR,
]

# 常用角色分组（用于粗粒度页面级鉴权）
FINANCE_ROLES: list[Role] = [Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER]
DIRECTOR_ROLES: list[Role] = [Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR]


def role_label(value) -> str:
    """将角色值（字符串或 Role）转为中文名，未知则原样返回。"""
    try:
        return Role(value).label if not isinstance(value, Role) else value.label
    except (ValueError, KeyError):
        return str(value or "")


def role_at_step(step: int):
    """返回某审批步序对应的角色；越界返回 None。"""
    if 0 <= step < len(APPROVAL_CHAIN):
        return APPROVAL_CHAIN[step]
    return None


def is_final_step(step: int) -> bool:
    """是否为审批链最后一级。"""
    return step == len(APPROVAL_CHAIN) - 1


class ContractStatus(str, Enum):
    """合同状态。"""

    DRAFT = "draft"          # 草稿
    PENDING = "pending"      # 审批中
    APPROVED = "approved"    # 已通过
    REJECTED = "rejected"    # 已驳回


CONTRACT_STATUS_LABELS: dict[str, str] = {
    "draft": "草稿",
    "pending": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
}


class ApprovalAction(str, Enum):
    """审批动作。"""

    APPROVE = "approve"      # 通过
    REJECT = "reject"        # 驳回


class ContractType(str, Enum):
    """合同/审批单类型，决定打印时渲染的单据模板。"""

    PAYMENT = "payment"      # 业务付款审批单
    BUSINESS = "business"    # 业务审批单


CONTRACT_TYPE_LABELS: dict[str, str] = {
    "payment": "业务付款审批单",
    "business": "业务审批单",
}


class InvoiceStatus(str, Enum):
    """发票开票状态。"""

    PENDING = "pending"      # 待开票
    ISSUED = "issued"        # 已开票
    VOID = "void"            # 已作废


INVOICE_STATUS_LABELS: dict[str, str] = {
    "pending": "待开票",
    "issued": "已开票",
    "void": "已作废",
}


# 渠道平台类别标签（多渠道数据集成）
CHANNEL_CATEGORY_LABELS: dict[str, str] = {
    "ticket": "景区门票",
    "hotel": "酒店数据",
    "ota": "综合 OTA",
    "other": "其他平台",
}
