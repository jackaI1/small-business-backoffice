from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from cashforecast.forecast import forecast
from cashforecast.models import Flow, Rate, rounded
from cashforecast.reconcile import reconcile

AS_OF = date(2026, 10, 31)


def build(sample, minimum=D("15000")):
    recon = reconcile(sample.accounts, sample.bank, sample.ledger, AS_OF)
    return forecast(sample, recon, AS_OF, minimum)


def test_conversion_uses_as_of_rate_and_rounds_cents(sample):
    result = build(sample)
    assert result["opening_cad"] == D("60406.88")
    rate = next(r for r in result["rates"] if r["currency"] == "USD")
    assert rate["cad_per_unit"] == D("1.375000")
    assert rounded(D("0.01") * D("1.5")) == D("0.02")
    assert rounded(D("-0.01") * D("1.5")) == D("-0.02")


def test_paid_cash_excluded_and_future_bank_not_double_counted(sample):
    result = build(sample)
    assert {f["id"] for f in result["flows"]}.isdisjoint({"PAID-100", "LATER"})
    assert {f["id"] for f in result["flows"]} >= {"FUTURE-700"}
    overdue = next(f for f in result["flows"] if f["id"] == "OVERDUE-VENDOR")
    assert overdue["planned_date"] == AS_OF + timedelta(days=1)
    assert overdue["overdue_days"] == 11


def test_thirteen_weeks_roll_forward_without_gaps(sample):
    result = build(sample)
    assert len(result["weeks"]) == 13
    assert result["weeks"][0]["start"] == date(2026, 11, 1)
    assert result["weeks"][-1]["end"] == date(2027, 1, 30)
    assert result["weeks"][-1]["closing"] == result["opening_cad"] + sum(
        f["cad"] for f in result["flows"]
    )
    for before, after in zip(result["weeks"], result["weeks"][1:]):
        assert before["closing"] == after["opening"]
        assert before["end"] + timedelta(days=1) == after["start"]


def test_midweek_shortfall_even_when_week_closes_above_minimum(sample):
    result = build(sample)
    first = result["weeks"][0]
    assert first["closing"] > D("15000")
    assert first["daily_low"] < D("15000")
    assert first["breach"]


def test_exact_liquidity_threshold_is_not_a_breach(sample):
    empty = replace(sample, flows=())
    result = build(empty, build(empty)["opening_cad"])
    assert result["breach_weeks"] == 0


@pytest.mark.parametrize("offset,included", [(0, True), (1, True), (91, True), (92, False)])
def test_horizon_boundaries(sample, offset, included):
    flow = Flow("edge", "operating-cad", AS_OF + timedelta(days=offset), D("1"), "Boundary")
    result = build(replace(sample, flows=(flow,)))
    assert bool(result["flows"]) is included


@pytest.mark.parametrize(
    "rates",
    [
        (),
        (Rate("CAD", AS_OF, D(1)),),
        (Rate("CAD", AS_OF, D(1)), Rate("USD", AS_OF - timedelta(days=15), D("1.3"))),
    ],
)
def test_missing_or_stale_fx_fails_instead_of_assuming_one(sample, rates):
    with pytest.raises(ValueError, match="missing|stale"):
        build(replace(sample, rates=rates))


def test_empty_flows_still_produces_thirteen_balances(sample):
    result = build(replace(sample, flows=()))
    assert all(w["closing"] == result["opening_cad"] for w in result["weeks"])


def test_negative_minimum_rejected(sample):
    with pytest.raises(ValueError, match="minimum"):
        build(sample, D("-1"))
