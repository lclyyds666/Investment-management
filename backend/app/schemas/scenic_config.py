"""景区默认配置读写 schema。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScenicConfigUpdate(BaseModel):
    default_ticket_product: str = Field(min_length=1, max_length=200)
    ticket_rate_hexiao: Decimal = Field(ge=0, le=1)
    ticket_rate_settle: Decimal = Field(ge=0, le=1)
    ticket_commission_rate: Decimal = Field(ge=0, le=1)
    ticket_default_commission: Decimal | None = Field(default=None, ge=0)

    @field_validator("default_ticket_product")
    @classmethod
    def strip_ticket_product(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("默认门票名称不能为空")
        return value


class ScenicConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenic_id: str
    scenic_name: str
    sort_order: int = 0
    default_ticket_product: str
    ticket_rate_hexiao: Decimal
    ticket_rate_settle: Decimal
    ticket_commission_rate: Decimal
    ticket_default_commission: Decimal | None = None
    configured: bool = True
    updated_by: int | None = None
    updated_at: datetime | None = None
