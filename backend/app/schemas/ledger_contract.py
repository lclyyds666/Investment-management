from pydantic import BaseModel


class LedgerConfirmApproveIn(BaseModel):
    contract_id: int
