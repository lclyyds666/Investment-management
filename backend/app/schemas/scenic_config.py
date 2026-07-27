"""景区核销台账默认配置 schema。"""
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScenicConfigPutIn(BaseModel):
    scenic_name: str = Field(min_length=1, max_length=128)
    image_url: Optional[str] = Field(default=None, max_length=500)
    ticket_enabled: Optional[bool] = None
    hotel_enabled: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0)
    default_ticket_product: str = Field(default="", max_length=200)
    default_hotel_name: str = Field(default="", max_length=255)
    rate_hexiao: Decimal = Field(ge=0, le=1)
    rate_settle: Decimal = Field(ge=0, le=1)
    commission_rate: Decimal = Field(ge=0, le=1)
    hotel_fee_algo: Literal[1, 2]
    fee_per_night: Decimal = Field(ge=0)
    enabled: bool = True


class ScenicConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenic_id: str
    scenic_name: str = ""
    image_url: str = ""
    ticket_enabled: bool = True
    hotel_enabled: bool = True
    sort_order: int = 0
    default_ticket_product: str = ""
    default_hotel_name: str = ""
    rate_hexiao: Decimal = Decimal("0.9000")
    rate_settle: Decimal = Decimal("0.9400")
    commission_rate: Decimal = Decimal("0.0600")
    hotel_fee_algo: int = 1
    fee_per_night: Decimal = Decimal("44.00")
    enabled: bool = True
    configured: bool = True
    source: Literal["database", "fallback"] = "database"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScenicSpotOut(BaseModel):
    id: str
    name: str
    image: str = ""
    ticket_enabled: bool = True
    hotel_enabled: bool = True
