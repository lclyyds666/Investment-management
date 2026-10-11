from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ContractStatus, InvoiceSourceKind
from app.models.contract import Contract
from app.models.ledger_contract import LedgerContractLink, ScenicContractPreference


class ContractLinkError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def remember_contract_preference(
    db: Session,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    contract_id: int,
) -> ScenicContractPreference:
    preference = db.scalar(
        select(ScenicContractPreference)
        .where(
            ScenicContractPreference.scenic_id == scenic_id,
            ScenicContractPreference.source_kind == source_kind,
        )
        .with_for_update()
    )
    if preference is None:
        preference = ScenicContractPreference(
            scenic_id=scenic_id,
            source_kind=source_kind,
            last_contract_id=contract_id,
        )
        db.add(preference)
    else:
        preference.last_contract_id = contract_id
    return preference


def link_period_contract(
    db: Session,
    scenic_id: str,
    source_kind: InvoiceSourceKind,
    period_key: str,
    contract_id: int,
    user_id: int,
) -> LedgerContractLink:
    existing = db.scalar(
        select(LedgerContractLink)
        .where(
            LedgerContractLink.scenic_id == scenic_id,
            LedgerContractLink.source_kind == source_kind,
            LedgerContractLink.period_key == period_key,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.contract_id != contract_id:
            raise ContractLinkError("confirmed_period_contract_locked")
        return existing

    contract = db.get(Contract, contract_id)
    if contract is None or contract.status != ContractStatus.APPROVED:
        raise ContractLinkError("contract_not_approved")
    if contract.scenic_id != scenic_id:
        raise ContractLinkError("contract_scenic_mismatch")
    if source_kind.value not in (contract.business_scopes or []):
        raise ContractLinkError("contract_scope_mismatch")

    link = LedgerContractLink(
        scenic_id=scenic_id,
        source_kind=source_kind,
        period_key=period_key,
        contract_id=contract.id,
        contract_no_snapshot=contract.contract_no,
        selected_by=user_id,
    )
    db.add(link)
    remember_contract_preference(db, scenic_id, source_kind, contract.id)
    db.flush()
    return link
