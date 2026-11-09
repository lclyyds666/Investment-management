"""Shared request and response models for operation forecasting."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from app.schemas.operation_analysis import DataQualityIssueOut


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


class ForecastRequest(BaseModel):
    start_date: date
    end_date: date
    scenic_ids: list[str] = Field(default_factory=list)
    business_types: list[Literal["ticket", "hotel"]] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    factors: list[ForecastFactor] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        if (self.end_date - self.start_date).days + 1 > 90:
            raise ValueError("预测范围不能超过90天")
        return self


class ForecastComponent(BaseModel):
    value: Decimal
    weight: Decimal


class ForecastLine(BaseModel):
    metric: Literal["settlement_amount", "writeoff_amount", "order_count"] = "settlement_amount"
    scenic_id: str
    business_type: Literal["ticket", "hotel"]
    platform: str
    baseline: Decimal | None = None
    factor_adjustment: Decimal = Decimal("0.00")
    forecast: Decimal | None = None
    interval_low: Decimal | None = None
    interval_high: Decimal | None = None
    confidence: Literal["high", "medium", "low"] = "low"
    components: dict[str, ForecastComponent] = Field(default_factory=dict)
    max_daily_factor: Decimal = Decimal("0.00")
    reasons: list[str] = Field(default_factory=list)


class ForecastOut(BaseModel):
    start_date: date
    end_date: date
    lines: list[ForecastLine] = Field(default_factory=list)
    quality_issues: list[DataQualityIssueOut] = Field(default_factory=list)
    insights: dict = Field(default_factory=dict)
