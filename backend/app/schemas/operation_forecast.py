"""Shared request and response models for operation forecasting."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ForecastFactor(BaseModel):
    start_date: date
    end_date: date
    scenic_id: str = ""
    business_type: Literal["", "ticket", "hotel"] = ""
    platform: str = ""
    factor_type: Literal["天气", "节假日", "活动", "资讯"]
    name: str = Field(min_length=1, max_length=100)
    impact_rate: Decimal = Field(ge=Decimal("-0.80"), le=Decimal("2.00"))
    remark: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class ForecastFactorRowError(BaseModel):
    row_no: int
    message: str


class ForecastFactorParseResult(BaseModel):
    items: list[ForecastFactor] = Field(default_factory=list)
    errors: list[ForecastFactorRowError] = Field(default_factory=list)
