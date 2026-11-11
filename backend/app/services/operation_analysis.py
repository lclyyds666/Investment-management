"""Pure, deterministic analysis over confirmed operation daily points."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import pstdev

from app.schemas.operation_analysis import (
    ContributionMetric,
    DimensionMetric,
    MetricComparison,
    OperationAnalysisOut,
    OperationAnomaly,
    OperationComparisons,
    OperationMetricSummary,
    OperationTrendPoint,
)

MOM_ALERT_RATE = Decimal("30.00")
STANDARD_DEVIATION_ALERT = Decimal("2.00")
MONEY = Decimal("0.01")
RATE = Decimal("0.01")
METRICS = ("settlement_amount", "writeoff_amount", "order_count", "capital_occupation")


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError("start date must not be after end date")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def shift(self, days: int) -> "DateRange":
        delta = timedelta(days=days)
        return DateRange(self.start + delta, self.end + delta)


@dataclass(frozen=True)
class AnalysisFilters:
    scenic_ids: tuple[str, ...] | list[str] = ()
    business_types: tuple[str, ...] | list[str] = ()
    platforms: tuple[str, ...] | list[str] = ()


def validated_date_range(start: date, end: date, max_days: int) -> DateRange:
    result = DateRange(start, end)
    if result.days > max_days:
        raise ValueError(f"date range must not exceed {max_days} days")
    return result


def percentage_change(current: Decimal, comparison: Decimal) -> Decimal | None:
    if comparison == 0:
        return None
    return ((current - comparison) / comparison * Decimal("100")).quantize(RATE, rounding=ROUND_HALF_UP)


def _last_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _filter_points(points, period: DateRange, filters: AnalysisFilters):
    scenic_ids = set(filters.scenic_ids)
    business_types = set(filters.business_types)
    platforms = set(filters.platforms)
    return [
        point for point in points
        if period.start <= point.day <= period.end
        and (not scenic_ids or point.scenic_id in scenic_ids)
        and (not business_types or point.business_type in business_types)
        and (not platforms or point.platform in platforms)
    ]


def _aggregate(points) -> OperationMetricSummary:
    settlement = sum((point.settlement_amount for point in points), Decimal("0")).quantize(MONEY)
    writeoff = sum((point.writeoff_amount for point in points), Decimal("0")).quantize(MONEY)
    orders = sum(point.order_count for point in points)
    return OperationMetricSummary(
        settlement_amount=settlement,
        writeoff_amount=writeoff,
        order_count=orders,
        capital_occupation=Decimal("0.00"),
    )


def _metric(summary: OperationMetricSummary, name: str) -> Decimal:
    return Decimal(getattr(summary, name))


def _comparison(current, previous, last_year, name: str) -> MetricComparison:
    current_value = _metric(current, name)
    previous_value = _metric(previous, name)
    last_year_value = _metric(last_year, name)
    return MetricComparison(
        current=current_value,
        previous=previous_value,
        last_year=last_year_value,
        mom_rate=percentage_change(current_value, previous_value),
        yoy_rate=percentage_change(current_value, last_year_value),
    )


def _build_trends(points, period: DateRange, filters: AnalysisFilters):
    filtered = _filter_points(points, period, filters)
    by_day = {}
    for point in filtered:
        by_day.setdefault(point.day, []).append(point)
    return [
        OperationTrendPoint(day=period.start + timedelta(days=index), **_aggregate(by_day.get(period.start + timedelta(days=index), [])).model_dump())
        for index in range(period.days)
    ]


def _build_rankings(current_points, current: OperationMetricSummary):
    rankings = []
    for dimension in ("scenic_id", "business_type", "platform"):
        grouped = {}
        for point in current_points:
            grouped.setdefault(getattr(point, dimension), []).append(point)
        for value, group in grouped.items():
            summary = _aggregate(group)
            share = None if current.settlement_amount == 0 else (
                summary.settlement_amount / current.settlement_amount * Decimal("100")
            ).quantize(RATE, rounding=ROUND_HALF_UP)
            rankings.append(DimensionMetric(dimension=dimension, value=value, summary=summary, settlement_share=share))
    return sorted(rankings, key=lambda item: (item.dimension, -item.summary.settlement_amount, item.value))


def _build_contributions(current_points, previous_points, current_total: Decimal):
    contributions = []
    for dimension in ("scenic_id", "business_type", "platform"):
        values = {getattr(point, dimension) for point in current_points + previous_points}
        for value in values:
            current = _aggregate([point for point in current_points if getattr(point, dimension) == value])
            previous = _aggregate([point for point in previous_points if getattr(point, dimension) == value])
            change = current.settlement_amount - previous.settlement_amount
            rate = None if current_total == 0 else (change / current_total * Decimal("100")).quantize(RATE, rounding=ROUND_HALF_UP)
            contributions.append(ContributionMetric(dimension=dimension, value=value, settlement_change=change, contribution_rate=rate))
    return sorted(contributions, key=lambda item: (item.dimension, -abs(item.settlement_change), item.value))


def _detect_anomalies(points, period, filters, current, previous, mom_rate, financial_rows=None):
    anomalies = []
    for metric in METRICS:
        rate = mom_rate[metric]
        if rate is not None and abs(rate) >= MOM_ALERT_RATE:
            anomalies.append(OperationAnomaly(
                metric=metric,
                severity="critical" if abs(rate) >= Decimal("50") else "warning",
                rule="mom_change",
                current=_metric(current, metric),
                baseline=_metric(previous, metric),
                evidence=rate,
            ))
        historical = []
        for index in range(1, 7):
            comparison_range = period.shift(days=-period.days * index)
            comparison_points = _filter_points(points, comparison_range, filters)
            if metric == "capital_occupation" and financial_rows is not None:
                from app.services.operation_capital import capital_summary
                historical.append(capital_summary(*financial_rows, comparison_range, filters)[0])
            elif comparison_points:
                historical.append(_metric(_aggregate(comparison_points), metric))
        if len(historical) == 6:
            mean = sum(historical, Decimal("0")) / Decimal(len(historical))
            sigma = Decimal(str(pstdev(historical)))
            if sigma > 0:
                score = ((_metric(current, metric) - mean) / sigma).quantize(RATE, rounding=ROUND_HALF_UP)
                if abs(score) >= STANDARD_DEVIATION_ALERT:
                    anomalies.append(OperationAnomaly(
                        metric=metric,
                        severity="critical" if abs(score) >= Decimal("3") else "warning",
                        rule="standard_deviation",
                        current=_metric(current, metric),
                        baseline=mean.quantize(MONEY),
                        evidence=score,
                    ))
    amount_rate, order_rate = mom_rate["settlement_amount"], mom_rate["order_count"]
    if amount_rate is not None and order_rate is not None and (
        (amount_rate > 0 and order_rate <= -MOM_ALERT_RATE)
        or (order_rate > 0 and amount_rate <= -MOM_ALERT_RATE)
    ):
        anomalies.append(OperationAnomaly(metric="settlement_amount", severity="warning",
            rule="amount_order_divergence", current=current.settlement_amount,
            baseline=previous.settlement_amount, evidence=amount_rate - order_rate,
            reason="结算金额与订单量方向相反，下降指标达到30%阈值。",
            suggestion="核对客单价、退款及平台结算周期。"))
    current_points = _filter_points(points, period, filters)
    previous_points = _filter_points(points, period.shift(-period.days), filters)
    if current.settlement_amount > 0 and previous.settlement_amount > 0:
        for platform in sorted({p.platform for p in current_points + previous_points}):
            now = sum((p.settlement_amount for p in current_points if p.platform == platform), Decimal(0)) / current.settlement_amount * 100
            before = sum((p.settlement_amount for p in previous_points if p.platform == platform), Decimal(0)) / previous.settlement_amount * 100
            if abs(now - before) >= Decimal(30):
                anomalies.append(OperationAnomaly(metric="settlement_amount", dimension=platform,
                    severity="warning", rule="platform_concentration", current=now.quantize(RATE),
                    baseline=before.quantize(RATE), evidence=(now-before).quantize(RATE),
                    reason="平台结算贡献占比变动达到30个百分点。", suggestion="核对渠道投放、结算完整性及平台依赖风险。"))
    for anomaly in anomalies:
        if not anomaly.reason:
            anomaly.reason = "环比变动达到30%阈值。" if anomaly.rule == "mom_change" else "偏离最近六周期均值达到2个标准差。"
            anomaly.suggestion = "核对台账覆盖、退款和结算周期后再调整经营安排。"
    return anomalies


def analyze(points, date_range: DateRange, filters: AnalysisFilters, *, financial_rows=None) -> OperationAnalysisOut:
    previous_range = date_range.shift(days=-date_range.days)
    last_year_range = DateRange(_last_year(date_range.start), _last_year(date_range.end))
    current_points = _filter_points(points, date_range, filters)
    previous_points = _filter_points(points, previous_range, filters)
    current = _aggregate(current_points)
    previous = _aggregate(previous_points)
    last_year = _aggregate(_filter_points(points, last_year_range, filters))
    quality = []
    if financial_rows is not None:
        from app.services.operation_capital import capital_summary
        for summary, period in ((current, date_range), (previous, previous_range), (last_year, last_year_range)):
            summary.capital_occupation, summary.capital_occupation_days, issues = capital_summary(*financial_rows, period, filters)
            if period == date_range:
                quality.extend(issues)
    comparisons = OperationComparisons(
        settlement=_comparison(current, previous, last_year, "settlement_amount"),
        writeoff=_comparison(current, previous, last_year, "writeoff_amount"),
        orders=_comparison(current, previous, last_year, "order_count"),
        capital_occupation=_comparison(current, previous, last_year, "capital_occupation"),
    )
    mom_rates = {
        "settlement_amount": comparisons.settlement.mom_rate,
        "writeoff_amount": comparisons.writeoff.mom_rate,
        "order_count": comparisons.orders.mom_rate,
        "capital_occupation": comparisons.capital_occupation.mom_rate,
    }
    result = OperationAnalysisOut(
        summary=current,
        trends=_build_trends(points, date_range, filters),
        comparisons=comparisons,
        rankings=_build_rankings(current_points, current),
        contributions=_build_contributions(current_points, previous_points, current.settlement_amount),
        anomalies=_detect_anomalies(points, date_range, filters, current, previous, mom_rates, financial_rows),
        quality_issues=quality,
    )
    if financial_rows is not None:
        existing = {(ranking.dimension, ranking.value) for ranking in result.rankings}
        # Financial dimensions may carry principal without current operational activity.
        for business, rows in zip(("ticket", "hotel"), financial_rows):
            for row in rows:
                if not row.confirmed:
                    continue
                for dimension, value in (("scenic_id", row.scenic_id), ("business_type", business), ("platform", row.platform)):
                    if (dimension, value) in existing:
                        continue
                    values = dict(scenic_ids=filters.scenic_ids, business_types=filters.business_types, platforms=filters.platforms)
                    field = {"scenic_id": "scenic_ids", "business_type": "business_types", "platform": "platforms"}[dimension]
                    if values[field] and value not in values[field]:
                        continue
                    values[field] = [value]
                    amount, days, _ = capital_summary(*financial_rows, date_range, AnalysisFilters(**values))
                    if amount > 0 or days is not None:
                        result.rankings.append(DimensionMetric(dimension=dimension, value=value, summary=OperationMetricSummary()))
                        existing.add((dimension, value))
        for trend in result.trends:
            trend.capital_occupation, trend.capital_occupation_days, _ = capital_summary(*financial_rows, DateRange(trend.day, trend.day), filters)
        for ranking in result.rankings:
            values = dict(scenic_ids=filters.scenic_ids, business_types=filters.business_types, platforms=filters.platforms)
            values[{"scenic_id": "scenic_ids", "business_type": "business_types", "platform": "platforms"}[ranking.dimension]] = [ranking.value]
            ranking.summary.capital_occupation, ranking.summary.capital_occupation_days, _ = capital_summary(*financial_rows, date_range, AnalysisFilters(**values))
        result.rankings.sort(key=lambda item: (item.dimension, -item.summary.settlement_amount, item.value))
    return result
