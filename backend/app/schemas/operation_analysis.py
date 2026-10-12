"""Schemas for deterministic operation analysis responses."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class OperationMetricSummary(BaseModel):
    settlement_amount: Decimal = Decimal("0.00")
    writeoff_amount: Decimal = Decimal("0.00")
    order_count: int = 0
    capital_occupation: Decimal = Decimal("0.00")


class OperationTrendPoint(OperationMetricSummary):
    day: date


class MetricComparison(BaseModel):
    current: Decimal
    previous: Decimal
    last_year: Decimal
    mom_rate: Decimal | None = None
    yoy_rate: Decimal | None = None


class OperationComparisons(BaseModel):
    settlement: MetricComparison
    writeoff: MetricComparison
    orders: MetricComparison
    capital_occupation: MetricComparison


class DimensionMetric(BaseModel):
    dimension: Literal["scenic_id", "business_type", "platform"]
    value: str
    summary: OperationMetricSummary
    settlement_share: Decimal | None = None


class ContributionMetric(BaseModel):
    dimension: Literal["scenic_id", "business_type", "platform"]
    value: str
    settlement_change: Decimal
    contribution_rate: Decimal | None = None


class OperationAnomaly(BaseModel):
    metric: Literal["settlement_amount", "writeoff_amount", "order_count", "capital_occupation"]
    dimension: str = "all"
    severity: Literal["warning", "critical"]
    rule: Literal["mom_change", "standard_deviation"]
    current: Decimal
    baseline: Decimal
    evidence: Decimal


class DataQualityIssueOut(BaseModel):
    row_id: int | str | None = None
    business_type: str
    code: str


class OperationAnalysisOut(BaseModel):
    summary: OperationMetricSummary
    trends: list[OperationTrendPoint] = Field(default_factory=list)
    comparisons: OperationComparisons
    rankings: list[DimensionMetric] = Field(default_factory=list)
    contributions: list[ContributionMetric] = Field(default_factory=list)
    anomalies: list[OperationAnomaly] = Field(default_factory=list)
    quality_issues: list[DataQualityIssueOut] = Field(default_factory=list)
