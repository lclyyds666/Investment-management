"""全局枚举定义（生产商用级 · 7 级组织角色与审批链）。"""
from enum import Enum


class Role(str, Enum):
    """系统角色。

    合同审批流的逐级流转顺序见 :data:`APPROVAL_CHAIN`（业务经办→供管公司负责人→
    法律顾问→投资公司法务风控→投资公司分管领导）。其余角色（业务复核/财务经办/
    财务复核）保留用于模块级页面权限，不在合同审批链上。
    """

    BUSINESS_HANDLER = "business_handler"      # 业务经办：合同源头录入与提交
    BUSINESS_REVIEWER = "business_reviewer"    # 业务复核
    RISK_AUDITOR = "risk_auditor"              # 投资公司法务风控（原“风控审核”，值不变）
    FINANCE_HANDLER = "finance_handler"        # 财务经办
    FINANCE_REVIEWER = "finance_reviewer"      # 投资公司财务复核（原“财务复核”，值不变）
    SCM_DIRECTOR = "scm_director"              # 供管公司负责人
    INVEST_DIRECTOR = "invest_director"        # 投资公司分管领导（原“投资公司负责人”，值不变）
    LEGAL_COUNSEL = "legal_counsel"            # 法律顾问：仅看合同管理 + 审批中心给意见
    INFO_MAINTAINER = "info_maintainer"        # 信息维护：超管账号身份，不在 7 级审批链，权限来自 is_superuser

    @property
    def label(self) -> str:
        return ROLE_LABELS[self]


# 角色中文名（重命名仅改此处显示名，角色值保持不变，避免历史数据迁移）
ROLE_LABELS: dict[Role, str] = {
    Role.BUSINESS_HANDLER: "业务经办",
    Role.BUSINESS_REVIEWER: "业务复核",
    Role.RISK_AUDITOR: "投资公司法务风控",
    Role.FINANCE_HANDLER: "财务经办",
    Role.FINANCE_REVIEWER: "投资公司财务复核",
    Role.SCM_DIRECTOR: "供管公司负责人",
    Role.INVEST_DIRECTOR: "投资公司分管领导",
    Role.LEGAL_COUNSEL: "法律顾问",
    Role.INFO_MAINTAINER: "信息维护",
}

# 合同审批链：列表顺序 == 逐级流转顺序（index 即 step）
#   业务经办 → 供管公司负责人 → 法律顾问 → 投资公司法务风控 → 投资公司分管领导
APPROVAL_CHAIN: list[Role] = [
    Role.BUSINESS_HANDLER,
    Role.SCM_DIRECTOR,
    Role.LEGAL_COUNSEL,
    Role.RISK_AUDITOR,
    Role.INVEST_DIRECTOR,
]

# 常用角色分组（用于粗粒度页面级鉴权）
FINANCE_ROLES: list[Role] = [Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER]
DIRECTOR_ROLES: list[Role] = [Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR]

# --------------------------------------------------------------------------- #
# 审批中心：两套独立工作流的审批链（与上方合同审批链 APPROVAL_CHAIN 互不干扰）
# 顺序即逐级流转顺序（index 即 step），与 xlsx 打印模板的签批栏顺序一一对应。
# --------------------------------------------------------------------------- #
# Type A 业务付款审批单（7 节点）
PAYMENT_APPROVAL_CHAIN: list[Role] = [
    Role.BUSINESS_HANDLER,   # 业务经办
    Role.BUSINESS_REVIEWER,  # 业务复核
    Role.FINANCE_HANDLER,    # 供管公司财务审核（财务经办）
    Role.SCM_DIRECTOR,       # 供管公司负责人
    Role.RISK_AUDITOR,       # 投资公司法务风控部
    Role.FINANCE_REVIEWER,   # 投资公司财务负责人（财务复核）
    Role.INVEST_DIRECTOR,    # 投资公司分管领导
]

# Type B 业务审批单（5 节点）
BUSINESS_APPROVAL_CHAIN: list[Role] = [
    Role.BUSINESS_HANDLER,   # 业务经办
    Role.BUSINESS_REVIEWER,  # 业务复核
    Role.SCM_DIRECTOR,       # 供管公司负责人
    Role.RISK_AUDITOR,       # 投资公司法务风控部
    Role.INVEST_DIRECTOR,    # 投资公司分管领导
]


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

# 审批单类型 → 对应审批链（两套独立工作流的分派表）
FORM_CHAINS: dict[str, list[Role]] = {
    ContractType.PAYMENT.value: PAYMENT_APPROVAL_CHAIN,
    ContractType.BUSINESS.value: BUSINESS_APPROVAL_CHAIN,
}


def form_chain(form_type) -> list[Role]:
    """按审批单类型返回其审批链；未知类型回退业务审批链。"""
    key = form_type.value if isinstance(form_type, ContractType) else str(form_type or "")
    return FORM_CHAINS.get(key, BUSINESS_APPROVAL_CHAIN)


def form_role_at_step(form_type, step: int):
    """返回某审批单类型在某步序对应的角色；越界返回 None。"""
    chain = form_chain(form_type)
    if 0 <= step < len(chain):
        return chain[step]
    return None


def form_is_final_step(form_type, step: int) -> bool:
    """是否为该审批单类型审批链的最后一级。"""
    return step == len(form_chain(form_type)) - 1


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
