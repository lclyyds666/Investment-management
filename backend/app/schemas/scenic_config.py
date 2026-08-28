"""景区默认配置读写 schema。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


HOTEL_PLATFORMS = ("抖音", "美团", "携程")


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


class HotelScenicConfigUpdate(BaseModel):
    default_hotel_name: str = Field(min_length=1, max_length=255)
    hotel_rate_hexiao: Decimal = Field(ge=0, le=1)
    hotel_rate_settle: Decimal = Field(ge=0, le=1)
    hotel_commission_rate: Decimal = Field(ge=0, le=1)
    hotel_fee_per_night: Decimal = Field(ge=0)
    hotel_fee_algo: int = Field(ge=1, le=2)
    hotel_platforms: tuple[str, ...] = Field(min_length=1)

    @field_validator("default_hotel_name")
    @classmethod
    def strip_hotel_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("默认酒店名称不能为空")
        return value

    @field_validator("hotel_platforms")
    @classmethod
    def validate_hotel_platforms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(platform.strip() for platform in value)
        if any(not platform for platform in normalized):
            raise ValueError("酒店启用平台不能为空")
        if len(set(normalized)) != len(normalized):
            raise ValueError("酒店启用平台不能重复")
        invalid = set(normalized).difference(HOTEL_PLATFORMS)
        if invalid:
            raise ValueError("酒店平台仅支持抖音、美团、携程")
        return normalized


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
    default_hotel_name: str
    hotel_rate_hexiao: Decimal
    hotel_rate_settle: Decimal
    hotel_commission_rate: Decimal
    hotel_fee_per_night: Decimal
    hotel_fee_algo: int
    hotel_platforms: tuple[str, ...]
    configured: bool = True
    updated_by: int | None = None
    updated_at: datetime | None = None
