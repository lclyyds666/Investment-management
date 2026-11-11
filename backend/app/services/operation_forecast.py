"""Pure, explainable forecasts over confirmed operation daily points."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import product
from statistics import pstdev

from app.schemas.operation_forecast import (
    ForecastComponent,
    ForecastLine,
    ForecastOut,
    ForecastRequest,
)

BASE_WEIGHTS = {
    "same_period": Decimal("0.40"),
    "recent": Decimal("0.40"),
    "trend": Decimal("0.20"),
}
MONEY = Decimal("0.01")
RATE = Decimal("0.01")


@dataclass(frozen=True)
class ForecastKey:
    scenic_id: str
    business_type: str
    platform: str


def _last_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _matches(point, key: ForecastKey, include_all_platforms: bool = False) -> bool:
    return (
        point.scenic_id == key.scenic_id
        and point.business_type == key.business_type
        and (include_all_platforms or point.platform == key.platform)
    )


def _daily_totals(series, key: ForecastKey, include_all_platforms: bool = False) -> dict[date, Decimal]:
    totals: dict[date, Decimal] = {}
    for point in series:
        if _matches(point, key, include_all_platforms):
            totals[point.day] = totals.get(point.day, Decimal("0")) + point.settlement_amount
    return totals


def _period_total(totals: dict[date, Decimal], start: date, days: int) -> Decimal | None:
    dates = [start + timedelta(days=offset) for offset in range(days)]
    if not all(day in totals for day in dates):
        return None
    return sum((totals[day] for day in dates), Decimal("0"))


def _recent_periods(totals: dict[date, Decimal], target_start: date, days: int, count: int) -> list[Decimal | None]:
    return [
        _period_total(totals, target_start - timedelta(days=days * index), days)
        for index in range(1, count + 1)
    ]


def normalized_components(values: dict[str, Decimal | None]) -> dict[str, ForecastComponent]:
    available = {name: value for name, value in values.items() if value is not None}
    weight_total = sum((BASE_WEIGHTS[name] for name in available), Decimal("0"))
    if not weight_total:
        return {}
    return {
        name: ForecastComponent(
            value=value,
            weight=(BASE_WEIGHTS[name] / weight_total).quantize(Decimal("0.0001")),
        )
        for name, value in available.items()
    }


def _weighted_recent(periods: list[Decimal | None]) -> Decimal | None:
    if len(periods) < 3 or any(value is None for value in periods[:3]):
        return None
    values = periods[:3]
    return sum((value * weight for value, weight in zip(values, (3, 2, 1))), Decimal("0")) / Decimal("6")


def _bounded_trend(periods: list[Decimal | None], recent: Decimal | None) -> Decimal | None:
    if recent is None:
        return None
    complete = [value for value in reversed(periods[:6]) if value is not None]
    if len(complete) < 3:
        return None
    count = Decimal(len(complete))
    x_mean = Decimal(len(complete) - 1) / Decimal("2")
    y_mean = sum(complete, Decimal("0")) / count
    numerator = sum(
        (Decimal(index) - x_mean) * (value - y_mean)
        for index, value in enumerate(complete)
    )
    denominator = sum((Decimal(index) - x_mean) ** 2 for index in range(len(complete)))
    projected = y_mean + (numerator / denominator) * Decimal(len(complete))
    return min(max(projected, recent * Decimal("0.50")), recent * Decimal("2.00"))


def _baseline(totals: dict[date, Decimal], request: ForecastRequest):
    days = (request.end_date - request.start_date).days + 1
    same_start = _last_year(request.start_date)
    same_period = _period_total(totals, same_start, days)
    periods = _recent_periods(totals, request.start_date, days, 12)
    recent = _weighted_recent(periods)
    trend = _bounded_trend(periods, recent)
    components = normalized_components({
        "same_period": same_period,
        "recent": recent,
        "trend": trend,
    })
    baseline = sum(
        (component.value * component.weight for component in components.values()),
        Decimal("0"),
    )
    return baseline.quantize(MONEY, rounding=ROUND_HALF_UP), components, periods


def _platform_share(series, key: ForecastKey, before: date) -> Decimal | None:
    platform_days = [point.day for point in series if point.day < before and _matches(point, key)]
    if not platform_days:
        return None
    latest = max(platform_days)
    latest_points = [
        point for point in series
        if point.day == latest
        and point.day < before
        and point.scenic_id == key.scenic_id
        and point.business_type == key.business_type
    ]
    total = sum((point.settlement_amount for point in latest_points), Decimal("0"))
    platform_total = sum(
        (point.settlement_amount for point in latest_points if point.platform == key.platform),
        Decimal("0"),
    )
    return platform_total / total if total else None


def _factor_rate(day: date, key: ForecastKey, factors) -> Decimal:
    rate = sum(
        (
            factor.impact_rate
            for factor in factors
            if factor.start_date <= day <= factor.end_date
            and (not factor.scenic_id or factor.scenic_id == key.scenic_id)
            and (not factor.business_type or factor.business_type == key.business_type)
            and (not factor.platform or factor.platform == key.platform)
        ),
        Decimal("0"),
    )
    return min(max(rate, Decimal("-0.80")), Decimal("2.00"))


def _split_money(total: Decimal, days: int) -> list[Decimal]:
    unit = (total / Decimal(days)).quantize(MONEY, rounding=ROUND_HALF_UP)
    values = [unit] * days
    values[-1] += total - sum(values, Decimal("0"))
    return values


def _sigma(periods: list[Decimal | None], baseline: Decimal) -> Decimal:
    complete = [value for value in periods if value is not None]
    if len(complete) < 2:
        return Decimal("0")
    return Decimal(str(pstdev([float(value - baseline) for value in complete])))


def _confidence(periods: list[Decimal | None], fallback_used: bool) -> str:
    period_count = sum(value is not None for value in periods)
    coverage = Decimal(period_count) / Decimal(len(periods))
    if fallback_used or period_count < 3:
        return "low"
    if period_count >= 12 and coverage >= Decimal("0.90"):
        return "high"
    return "medium"


def _calendar_profile(totals, request):
    """Learn weekdays only from prior observations; never infer statutory holidays."""
    history = {day: value for day, value in totals.items()
               if request.start_date - timedelta(days=366) <= day < request.start_date}
    groups = [[value for day, value in history.items() if day.weekday() == weekday]
              for weekday in range(7)]
    if any(len(values) < 2 for values in groups):
        return None
    means = [sum(values, Decimal(0)) / len(values) for values in groups]
    historical_mean = sum(history.values(), Decimal(0)) / len(history)
    if historical_mean <= 0:
        return None
    return [value / historical_mean for value in means]


def _contributions(series, request, key, daily, rates):
    raw = [Decimal(0) for _ in request.factors]
    for offset, value in enumerate(daily):
        day = request.start_date + timedelta(days=offset)
        applicable = [i for i, factor in enumerate(request.factors)
                      if _factor_rate(day, key, [factor]) != 0]
        total = sum((request.factors[i].impact_rate for i in applicable), Decimal(0))
        scale = rates[offset] / total if total else Decimal(1)
        for i in applicable:
            raw[i] += value * request.factors[i].impact_rate * scale
    return raw


def _rounded_contributions(raw, target, quantum):
    # Largest-remainder apportionment also works for signed, cancelling factors.
    values = [value.quantize(quantum, rounding=ROUND_HALF_UP) for value in raw]
    remainder = target - sum(values, Decimal(0))
    while remainder and values:
        direction = quantum if remainder > 0 else -quantum
        eligible = [i for i in range(len(values)) if raw[i] != 0]
        if not eligible:
            break
        index = max(eligible, key=lambda i: ((raw[i] - values[i]) * direction, -i))
        values[index] += direction
        remainder -= direction
    return values


def _requested_keys(series, request: ForecastRequest) -> list[ForecastKey]:
    if request.scenic_ids and request.business_types and request.platforms:
        return [
            ForecastKey(*values)
            for values in product(request.scenic_ids, request.business_types, request.platforms)
        ]
    return sorted(
        {
            ForecastKey(point.scenic_id, point.business_type, point.platform)
            for point in series
            if point.day < request.start_date
            and (not request.scenic_ids or point.scenic_id in request.scenic_ids)
            and (not request.business_types or point.business_type in request.business_types)
            and (not request.platforms or point.platform in request.platforms)
        },
        key=lambda key: (key.scenic_id, key.business_type, key.platform),
    )


def _insufficient_line(key: ForecastKey) -> ForecastLine:
    return ForecastLine(
        scenic_id=key.scenic_id,
        business_type=key.business_type,
        platform=key.platform,
        reasons=["insufficient_data"],
    )


def _forecast_line(series, request: ForecastRequest, key: ForecastKey) -> ForecastLine:
    own_totals = _daily_totals(series, key)
    own_recent = _recent_periods(
        own_totals,
        request.start_date,
        (request.end_date - request.start_date).days + 1,
        12,
    )
    fallback_used = sum(value is not None for value in own_recent) < 3
    reasons = []
    share = Decimal("1")
    totals = own_totals
    if fallback_used:
        share = _platform_share(series, key, request.start_date)
        peer_totals = _daily_totals(series, key, include_all_platforms=True)
        if share is None or not peer_totals:
            return _insufficient_line(key)
        totals = {day: value * share for day, value in peer_totals.items()}
        reasons.append("same_scenic_business_fallback")

    baseline, components, periods = _baseline(totals, request)
    if not components:
        return _insufficient_line(key)

    days = (request.end_date - request.start_date).days + 1
    daily_baseline = _split_money(baseline, days)
    profile = _calendar_profile(totals, request)
    calendar = {"statutory_holiday_source": None, "weekday_applied": profile is not None,
                "holiday_adjustment": "explicit_factors_only"}
    reasons.append("statutory_calendar_unavailable: 未配置法定节假日日历，仅应用手工或导入的节假日因素")
    if profile is not None:
        weights = [profile[(request.start_date + timedelta(days=i)).weekday()] for i in range(days)]
        adjusted = (baseline * sum(weights, Decimal(0)) / days).quantize(MONEY, rounding=ROUND_HALF_UP)
        calendar.update(weekday_factor=str(adjusted / baseline if baseline else Decimal(1)),
                        adjustment=str(adjusted - baseline), weekday_weights=[str(value) for value in profile])
        baseline = adjusted
        weight_total = sum(weights, Decimal(0))
        daily_baseline = [(baseline * weight / weight_total).quantize(MONEY, rounding=ROUND_HALF_UP)
                          for weight in weights] if weight_total else _split_money(baseline, days)
        daily_baseline[-1] += baseline - sum(daily_baseline, Decimal(0))
    else:
        reasons.append("weekday_history_insufficient: 星期样本不足，未作日历调整")
    rates = [
        _factor_rate(request.start_date + timedelta(days=index), key, request.factors)
        for index in range(days)
    ]
    forecast_value = sum(
        (
            max(value * (Decimal("1") + rate), Decimal("0")).quantize(MONEY, rounding=ROUND_HALF_UP)
            for value, rate in zip(daily_baseline, rates)
        ),
        Decimal("0"),
    ).quantize(MONEY)
    sigma = _sigma(periods, baseline)
    confidence = _confidence(periods, fallback_used)
    complete = [value for value in periods if value is not None]
    mean = sum(complete, Decimal(0)) / len(complete) if complete else Decimal(0)
    if mean > 0 and _sigma(periods, mean) / mean >= Decimal("0.50"):
        confidence = "low"
        reasons.append("high_history_volatility: 历史周期变异系数不低于50%")
    history_start = request.start_date - timedelta(days=days * 12)
    coverage = Decimal(sum(history_start <= day < request.start_date for day in totals)) / (days * 12)
    calendar["history_date_coverage"] = str(coverage)
    if coverage < Decimal("0.75"):
        confidence = "low"
        reasons.append("missing_history_dates: 最近12周期日期覆盖不足75%")
    raw = _contributions(series, request, key, daily_baseline, rates)
    contributions = _rounded_contributions(raw, forecast_value - baseline, MONEY)
    spread = sigma * Decimal("1.96")
    return ForecastLine(
        scenic_id=key.scenic_id,
        business_type=key.business_type,
        platform=key.platform,
        baseline=baseline,
        factor_adjustment=(forecast_value - baseline).quantize(MONEY),
        forecast=forecast_value,
        interval_low=max(forecast_value - spread, Decimal("0")).quantize(MONEY),
        interval_high=(forecast_value + spread).quantize(MONEY),
        confidence=confidence,
        components=components,
        max_daily_factor=max(rates, default=Decimal("0")).quantize(RATE),
        reasons=reasons,
        calendar=calendar,
        factor_contributions=[{"factor_index": i, "name": factor.name, "contribution": str(value)}
                              for i, (factor, value) in enumerate(zip(request.factors, contributions))],
    )


def forecast(series, request: ForecastRequest, *, all_metrics: bool = False) -> ForecastOut:
    # Reuse the established scalar estimator independently for each measure.
    series = list(series)
    lines = []
    metrics = ("settlement_amount", "writeoff_amount", "order_count") if all_metrics else ("settlement_amount",)
    for metric in metrics:
        metric_series = [replace(point, settlement_amount=Decimal(getattr(point, metric))) for point in series]
        for key in _requested_keys(metric_series, request):
            line = _forecast_line(metric_series, request, key)
            line.metric = metric
            if metric == "order_count":
                for field in ("baseline", "forecast", "interval_low", "interval_high"):
                    value = getattr(line, field)
                    if value is not None:
                        setattr(line, field, value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                if line.forecast is not None:
                    line.factor_adjustment = line.forecast - line.baseline
                    values = _rounded_contributions([Decimal(item["contribution"]) for item in line.factor_contributions], line.factor_adjustment, Decimal(1))
                    for item, value in zip(line.factor_contributions, values):
                        item["contribution"] = str(value)
            lines.append(line)
    return ForecastOut(
        start_date=request.start_date,
        end_date=request.end_date,
        lines=lines,
    )
