"""Confirmed financial snapshots; money outstanding at end, weighted days in range."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from app.services.scenic_analytics import decimal_value, hotel_period_key, occupation_values


def capital_summary(tickets, hotels, period, filters):
    groups = defaultdict(list)
    facts, issues = [], []
    for row in tickets:
        if row.confirmed:
            facts.append(("ticket", [row], row, getattr(row, "pay_date", None), getattr(row, "repay_date", None)))
    for row in hotels:
        if row.confirmed:
            groups[hotel_period_key(row)].append(row)
    for rows in groups.values():
        representative = max(rows, key=lambda row: decimal_value(getattr(row, "payment_amount", 0)))
        facts.append(("hotel", rows, representative,
                      next((row.payment_date for row in rows if getattr(row, "payment_date", None)), None),
                      next((row.repay_date for row in rows if getattr(row, "repay_date", None)), None)))
    amount, weight, denominator = Decimal(0), Decimal(0), Decimal(0)
    for business, rows, row, start, end in facts:
        if ((filters.scenic_ids and row.scenic_id not in filters.scenic_ids)
                or (filters.business_types and business not in filters.business_types)
                or (filters.platforms and not any(r.platform in filters.platforms for r in rows))):
            continue
        net = decimal_value(getattr(row, "payment_amount", 0)) - decimal_value(getattr(row, "co_investment_amount", 0))
        if net <= 0:
            continue
        if not start or (end and end < start):
            issues.append(dict(row_id=row.id, business_type=business, code="invalid_financial_dates"))
            continue
        if start <= period.end and (not end or end > period.end):
            amount += net
        clipped_start = max(start, period.start)
        clipped_end = min(end or (period.end + timedelta(days=1)), period.end + timedelta(days=1))
        if clipped_end > clipped_start:
            occupied, principal = occupation_values(net, clipped_start, clipped_end, period.end)
            weight += occupied
            denominator += principal
    return amount.quantize(Decimal("0.01")), (weight / denominator).quantize(Decimal("0.01")) if denominator else None, issues
