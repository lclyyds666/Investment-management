from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ContractStatus, InvoiceSourceKind
from app.models.contract import Contract
from app.models.user import User
from app.services.legal_record_scope import contract_access_predicate, legal_record_scope


class ContractEligibilityError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def eligible_contracts_for_user(
    db: Session,
    current_user: User,
    *,
    scenic_id: str | None = None,
    source_kind: InvoiceSourceKind | None = None,
) -> list[Contract]:
    statement = select(Contract).where(
        Contract.status == ContractStatus.APPROVED,
        contract_access_predicate(legal_record_scope(db, current_user)),
    )
    if scenic_id is not None:
        statement = statement.where(Contract.scenic_id == scenic_id)
    contracts = db.scalars(statement.order_by(Contract.id.asc())).all()
    if source_kind is None:
        return contracts
    return [
        contract
        for contract in contracts
        if source_kind.value in (contract.business_scopes or [])
    ]


def eligible_contract_for_user(
    db: Session,
    current_user: User,
    contract_id: int,
    *,
    scenic_id: str | None = None,
    source_kind: InvoiceSourceKind | None = None,
    for_update: bool = False,
) -> Contract:
    statement = select(Contract).where(
        Contract.id == contract_id,
        Contract.status == ContractStatus.APPROVED,
        contract_access_predicate(legal_record_scope(db, current_user)),
    )
    if for_update:
        statement = statement.with_for_update()
    contract = db.scalar(statement.execution_options(populate_existing=True))
    if contract is None:
        raise ContractEligibilityError("contract_not_approved")
    if scenic_id is not None and contract.scenic_id != scenic_id:
        raise ContractEligibilityError("contract_scenic_mismatch")
    if (
        source_kind is not None
        and source_kind.value not in (contract.business_scopes or [])
    ):
        raise ContractEligibilityError("contract_scope_mismatch")
    return contract
