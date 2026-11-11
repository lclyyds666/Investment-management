from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.operation_analysis import AnalysisFilters, DateRange, analyze
from app.services.operation_capital import capital_summary


def row(**changes):
    values = dict(id=1, confirmed=True, scenic_id="s", platform="a", payment_amount=Decimal(100), co_investment_amount=Decimal(20), pay_date=date(2026, 8, 30), payment_date=date(2026, 8, 30), repay_date=None, source_file="period")
    values.update(changes)
    return SimpleNamespace(**values)


def test_ticket_payment_per_row_and_hotel_once_per_period():
    period = DateRange(date(2026, 9, 1), date(2026, 9, 3))
    tickets = [row(), row(id=2, platform="b")]
    hotels = [row(), row(id=2, platform="b")]
    amount, days, issues = capital_summary(tickets, hotels, period, AnalysisFilters())
    assert amount == 240
    assert days == 3
    assert not issues
    assert capital_summary([], hotels, period, AnalysisFilters(platforms=["a", "b"]))[0] == 80


def test_repayment_boundary_clipping_and_invalid_dates():
    period = DateRange(date(2026, 9, 1), date(2026, 9, 3))
    amount, days, issues = capital_summary([row(repay_date=date(2026, 9, 3)), row(id=2, pay_date=None)], [], period, AnalysisFilters())
    assert amount == 0
    assert days == 2
    assert issues[0]["code"] == "invalid_financial_dates"
    assert capital_summary([row(pay_date=date(2026, 9, 4))], [], period, AnalysisFilters())[0] == 0
    result = analyze([], period, AnalysisFilters(), financial_rows=([row()], []))
    assert result.summary.capital_occupation == 80
    assert result.summary.capital_occupation_days == 3
    assert all(point.capital_occupation == 80 for point in result.trends)


def test_carried_principal_ranks_without_current_operational_points():
    period = DateRange(date(2026, 9, 1), date(2026, 9, 3))
    result = analyze([], period, AnalysisFilters(), financial_rows=([row()], [row(scenic_id="hotel", platform="b"), row(scenic_id="hotel", platform="c")]))
    rankings = {(item.dimension, item.value): item.summary.capital_occupation for item in result.rankings}
    assert result.summary.capital_occupation == 160
    assert rankings[("scenic_id", "s")] == 80
    assert rankings[("scenic_id", "hotel")] == 80
    assert rankings[("business_type", "ticket")] == 80
    assert rankings[("business_type", "hotel")] == 80
    assert rankings[("platform", "b")] == 80
    assert rankings[("platform", "c")] == 80  # Each references the same shared hotel period.
    filtered = analyze([], period, AnalysisFilters(platforms=["a"]), financial_rows=([row()], []))
    assert {item.value for item in filtered.rankings if item.dimension == "platform"} == {"a"}


def test_capital_sigma_uses_six_actual_snapshots_without_operational_points():
    current = date(2026, 9, 7)
    tickets = [row(id=i, payment_amount=Decimal(10), co_investment_amount=0,
                   pay_date=current-timedelta(days=7-i)) for i in range(1, 7)]
    tickets.append(row(id=7, payment_amount=Decimal(140), co_investment_amount=0, pay_date=current))
    # Previous six daily closing balances: 60, 50, 40, 30, 20, 10.
    result = analyze([], DateRange(current, current), AnalysisFilters(), financial_rows=(tickets, []))
    anomaly = next(item for item in result.anomalies if item.metric == "capital_occupation" and item.rule == "standard_deviation")
    assert anomaly.current == 200
    assert anomaly.baseline == Decimal("35.00")
    assert anomaly.evidence == Decimal("9.66")
