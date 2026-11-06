from datetime import date, timedelta
from decimal import Decimal

from .models import Dataset, rounded


def forecast(data: Dataset, reconciliation: dict, as_of: date, minimum: Decimal) -> dict:
    if minimum < 0:
        raise ValueError("minimum liquidity cannot be negative")
    rates = {}
    for currency in {a.currency for a in data.accounts}:
        choices = [r for r in data.rates if r.currency == currency and r.date <= as_of]
        if not choices:
            raise ValueError(f"missing {currency} FX rate on or before {as_of}")
        rate = max(choices, key=lambda r: r.date)
        if (as_of - rate.date).days > 14:
            raise ValueError(f"stale {currency} FX rate: over 14 days old")
        rates[currency] = rate
    by_account = {a.id: a for a in data.accounts}
    opening = sum(
        (
            rounded(c["bank_closing"] * rates[c["currency"]].cad_per_unit)
            for c in reconciliation["controls"]
        ),
        Decimal(0),
    )
    settled = {e.id for e in data.bank if e.date <= as_of}
    start, end = as_of + timedelta(days=1), as_of + timedelta(days=91)
    included, excluded = [], []
    for flow in data.flows:
        if flow.settled_bank_id in settled:
            excluded.append({"id": flow.id, "reason": "already_settled"})
            continue
        if flow.due > end:
            excluded.append({"id": flow.id, "reason": "outside_horizon"})
            continue
        planned = max(flow.due, start)
        currency = by_account[flow.account].currency
        rate = rates[currency].cad_per_unit
        included.append(
            {
                "id": flow.id,
                "account": flow.account,
                "due": flow.due,
                "planned_date": planned,
                "amount": flow.amount,
                "currency": currency,
                "rate": rate,
                "cad": rounded(flow.amount * rate),
                "overdue_days": max(0, (as_of - flow.due).days),
                "description": flow.description,
            }
        )
    weeks = []
    balance = opening
    for i in range(13):
        week_start = start + timedelta(days=7 * i)
        week_end = week_start + timedelta(days=6)
        flows = [f for f in included if week_start <= f["planned_date"] <= week_end]
        inflows = sum((f["cad"] for f in flows if f["cad"] > 0), Decimal(0))
        outflows = sum((f["cad"] for f in flows if f["cad"] < 0), Decimal(0))
        closing = balance + inflows + outflows
        # Daily net balances catch a midweek shortfall hidden by Friday receipts.
        running = balance
        low = balance
        for d in range(7):
            day = week_start + timedelta(days=d)
            running += sum((f["cad"] for f in flows if f["planned_date"] == day), Decimal(0))
            low = min(low, running)
        weeks.append(
            {
                "week": i + 1,
                "start": week_start,
                "end": week_end,
                "opening": balance,
                "inflows": inflows,
                "outflows": outflows,
                "closing": closing,
                "minimum": minimum,
                "headroom": closing - minimum,
                "daily_low": low,
                "breach": low < minimum,
            }
        )
        balance = closing
    return {
        "opening_cad": opening,
        "minimum_cad": minimum,
        "weeks": weeks,
        "flows": included,
        "excluded": excluded,
        "rates": [
            {"currency": r.currency, "date": r.date, "cad_per_unit": r.cad_per_unit}
            for r in sorted(rates.values(), key=lambda r: r.currency)
        ],
        "breach_weeks": sum(w["breach"] for w in weeks),
    }
