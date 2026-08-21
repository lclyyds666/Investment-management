from dataclasses import dataclass

from app.core.enums import WorkflowTargetType


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


@dataclass(frozen=True)
class WorkflowCatalogDefinition:
    code: str
    name: str
    target_type: WorkflowTargetType
    version: int
    nodes: tuple[WorkflowCatalogNode, ...]


def node(
    code: str,
    name: str,
    position_code: str,
    mode: str,
    *,
    candidate_rule: str = "position",
    candidate_position_codes: tuple[str, ...] = (),
    auto_complete_on_submit: bool = False,
    allow_reject: bool = True,
) -> WorkflowCatalogNode:
    return WorkflowCatalogNode(
        code=code,
        name=name,
        position_code=position_code,
        mode=mode,
        candidate_rule=candidate_rule,
        candidate_position_codes=candidate_position_codes,
        auto_complete_on_submit=auto_complete_on_submit,
        allow_reject=allow_reject,
    )


WORKFLOW_DEFINITIONS = (
    WorkflowCatalogDefinition(
        code="supply.contract.v2",
        name="供应链合同审批",
        target_type=WorkflowTargetType.CONTRACT,
        version=2,
        nodes=(
            node("handler", "业务经办", "supply.business_handler", "shared_position", auto_complete_on_submit=True, allow_reject=False),
            node("company_leader", "供管公司负责人", "supply.company_leader", "designated_user"),
            node("legal_counsel", "法律顾问", "external.legal_counsel", "designated_user"),
            node("supply_risk_review", "供应链法务风控复核", "investment.duty.supply_risk_review", "shared_position"),
            node("supply_governance_leader", "供应链分管领导", "governance.supply_leader", "designated_user"),
        ),
    ),
    WorkflowCatalogDefinition(
        code="supply.payment.v2",
        name="供应链付款审批",
        target_type=WorkflowTargetType.PAYMENT_APPROVAL,
        version=2,
        nodes=(
            node("handler", "业务经办", "supply.business_handler", "shared_position", auto_complete_on_submit=True, allow_reject=False),
            node("reviewer", "业务复核", "supply.business_reviewer", "shared_position"),
            node("finance_handler", "财务经办", "supply.finance_handler", "shared_position"),
            node("company_leader", "供管公司负责人", "supply.company_leader", "designated_user"),
            node("supply_risk_review", "供应链法务风控复核", "investment.duty.supply_risk_review", "shared_position"),
            node("supply_finance_review", "供应链财务复核", "investment.duty.supply_finance_review", "shared_position"),
            node("supply_governance_leader", "供应链分管领导", "governance.supply_leader", "designated_user"),
        ),
    ),
    WorkflowCatalogDefinition(
        code="supply.business.v2",
        name="供应链业务审批",
        target_type=WorkflowTargetType.BUSINESS_APPROVAL,
        version=2,
        nodes=(
            node("handler", "业务经办", "supply.business_handler", "shared_position", auto_complete_on_submit=True, allow_reject=False),
            node("reviewer", "业务复核", "supply.business_reviewer", "shared_position"),
            node("company_leader", "供管公司负责人", "supply.company_leader", "designated_user"),
            node("supply_risk_review", "供应链法务风控复核", "investment.duty.supply_risk_review", "shared_position"),
            node("supply_governance_leader", "供应链分管领导", "governance.supply_leader", "designated_user"),
        ),
    ),
    WorkflowCatalogDefinition(
        code="investment.contract.department.v1",
        name="投资公司部门合同审批",
        target_type=WorkflowTargetType.CONTRACT,
        version=1,
        nodes=(
            node(
                "initiator", "发起人", "", "designated_user",
                candidate_rule="initiator",
                auto_complete_on_submit=True,
                allow_reject=False,
            ),
            node(
                "department_head", "经办部门负责人", "investment.department.director", "designated_user",
                candidate_rule="same_department_head",
                candidate_position_codes=(
                    "investment.department.director",
                    "investment.duty.supply_risk_review",
                ),
            ),
            node(
                "legal_counsel", "外聘法律顾问", "external.legal_counsel", "designated_user",
                candidate_rule="external_legal_counsel",
                candidate_position_codes=("external.legal_counsel",),
            ),
            node(
                "legal_risk", "法务风控部", "investment.duty.supply_risk_review", "designated_user",
                candidate_rule="legal_risk_department",
                candidate_position_codes=(
                    "investment.duty.supply_risk_review",
                    "investment.legal_risk.deputy_director",
                    "investment.department.director",
                    "investment.department.deputy_director",
                    "investment.department.senior_manager",
                    "investment.department.middle_manager",
                    "investment.department.junior_manager",
                ),
            ),
            node(
                "governance_leader", "分管领导", "investment.executive.deputy_general_manager", "designated_user",
                candidate_rule="department_governance",
                candidate_position_codes=("investment.executive.deputy_general_manager",),
            ),
            node(
                "general_manager", "总经理", "investment.executive.general_manager", "designated_user",
                candidate_rule="investment_general_manager",
                candidate_position_codes=("investment.executive.general_manager",),
            ),
            node(
                "chairman", "单位主要负责人", "investment.executive.chairman", "designated_user",
                candidate_rule="investment_chairman",
                candidate_position_codes=("investment.executive.chairman",),
            ),
        ),
    ),
    WorkflowCatalogDefinition(
        code="investment.contract.subsidiary.v1",
        name="子公司合同审批",
        target_type=WorkflowTargetType.CONTRACT,
        version=1,
        nodes=(
            node(
                "initiator", "发起人", "", "designated_user",
                candidate_rule="initiator",
                auto_complete_on_submit=True,
                allow_reject=False,
            ),
            node(
                "company_head", "公司负责人", "supply.company_leader", "designated_user",
                candidate_rule="company_head",
                candidate_position_codes=(
                    "supply.company_leader",
                    "fund.chairman",
                    "fund.general_manager",
                    "zhanwei.general_manager",
                ),
            ),
            node(
                "legal_counsel", "外聘法律顾问", "external.legal_counsel", "designated_user",
                candidate_rule="external_legal_counsel",
                candidate_position_codes=("external.legal_counsel",),
            ),
            node(
                "legal_risk", "法务风控部", "investment.duty.supply_risk_review", "designated_user",
                candidate_rule="legal_risk_department",
                candidate_position_codes=(
                    "investment.duty.supply_risk_review",
                    "investment.legal_risk.deputy_director",
                    "investment.department.director",
                    "investment.department.deputy_director",
                    "investment.department.senior_manager",
                    "investment.department.middle_manager",
                    "investment.department.junior_manager",
                ),
            ),
            node(
                "governance_leader", "分管领导", "governance.supply_leader", "designated_user",
                candidate_rule="company_governance",
                candidate_position_codes=(
                    "governance.supply_leader",
                    "governance.fund_leader",
                    "governance.zhanwei_leader",
                ),
            ),
        ),
    ),
    WorkflowCatalogDefinition(
        code="investment.contract.legal-risk.v1",
        name="法务风控部合同审批",
        target_type=WorkflowTargetType.CONTRACT,
        version=1,
        nodes=(
            node(
                "initiator", "发起人", "", "designated_user",
                candidate_rule="initiator",
                auto_complete_on_submit=True,
                allow_reject=False,
            ),
            node(
                "department_head", "经办部门负责人", "investment.department.director", "designated_user",
                candidate_rule="same_department_head",
                candidate_position_codes=(
                    "investment.department.director",
                    "investment.duty.supply_risk_review",
                ),
            ),
            node(
                "legal_counsel", "外聘法律顾问", "external.legal_counsel", "designated_user",
                candidate_rule="external_legal_counsel",
                candidate_position_codes=("external.legal_counsel",),
            ),
            node(
                "governance_leader", "分管领导", "investment.executive.deputy_general_manager", "designated_user",
                candidate_rule="department_governance",
                candidate_position_codes=("investment.executive.deputy_general_manager",),
            ),
            node(
                "general_manager", "总经理", "investment.executive.general_manager", "designated_user",
                candidate_rule="investment_general_manager",
                candidate_position_codes=("investment.executive.general_manager",),
            ),
            node(
                "chairman", "单位主要负责人", "investment.executive.chairman", "designated_user",
                candidate_rule="investment_chairman",
                candidate_position_codes=("investment.executive.chairman",),
            ),
        ),
    ),
)

WORKFLOW_CATALOG = {definition.code: definition.nodes for definition in WORKFLOW_DEFINITIONS}
