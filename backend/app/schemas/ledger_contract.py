from pydantic import BaseModel, Field


class LedgerConfirmApproveIn(BaseModel):
    contract_id: int


class LedgerEligibleContractOut(BaseModel):
    id: int
    contract_no: str
    title: str
    scenic_id: str | None = None
    customer_name: str = ""
    business_scopes: list[str] = Field(default_factory=list)
    is_preferred: bool = False
