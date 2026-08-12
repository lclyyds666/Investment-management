from dataclasses import dataclass

from app.core.enums import WorkflowTargetType


@dataclass(frozen=True)
class WorkflowCatalogNode:
    code: str
    name: str
    position_code: str
    mode: str
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
    auto_complete_on_submit: bool = False,
    allow_reject: bool = True,
) -> WorkflowCatalogNode:
    return WorkflowCatalogNode(
        code=code,
        name=name,
        position_code=position_code,
        mode=mode,
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
)

WORKFLOW_CATALOG = {definition.code: definition.nodes for definition in WORKFLOW_DEFINITIONS}
