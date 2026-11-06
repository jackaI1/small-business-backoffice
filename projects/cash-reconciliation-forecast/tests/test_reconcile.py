from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from cashforecast.models import Account, Entry
from cashforecast.reconcile import age_band, reconcile

AS_OF = date(2026, 10, 31)
ACCOUNTS = (
    Account("cad", "CAD", date(2026, 7, 31), D("100"), D("100")),
    Account("usd", "USD", date(2026, 7, 31), D("100"), D("100")),
)


def entry(id, amount="10.00", ref="INV-1", day=10, account="cad"):
    return Entry(id, account, date(2026, 10, day), D(amount), ref)


def match(bank, ledger, **kwargs):
    return reconcile(ACCOUNTS, tuple(bank), tuple(ledger), AS_OF, **kwargs)


def test_normalized_reference_and_boundary():
    result = match([entry("b", ref="inv / 1")], [entry("l", day=13)])
    assert result["pairs"][0]["rule"] == "reference_amount"
    assert result["pairs"][0]["date_gap"] == 3


def test_outside_window_stays_open():
    result = match([entry("b")], [entry("l", day=14)])
    assert result["pairs"] == []
    assert len(result["unmatched"]) == 2


def test_blank_reference_amount_fallback():
    result = match([entry("b", ref="")], [entry("l")])
    assert result["pairs"][0]["rule"] == "amount_date"


def test_conflicting_nonempty_references_not_cleared():
    result = match([entry("b")], [entry("l", ref="OTHER")])
    assert result["pairs"] == []
    assert all(r["reason"] == "ambiguous_or_conflicting" for r in result["unmatched"])


@pytest.mark.parametrize("bank_side", [True, False])
def test_duplicate_candidates_never_arbitrarily_consumed(bank_side):
    single, duplicate = [entry("single")], [entry("d1"), entry("d2")]
    result = match(duplicate if bank_side else single, single if bank_side else duplicate)
    assert result["pairs"] == []
    assert len(result["unmatched"]) == 3
    assert all(c["unexplained"] == 0 for c in result["controls"])


def test_reference_disambiguates_same_amount():
    result = match([entry("b1"), entry("b2", ref="INV-2")], [entry("l2", ref="INV-2"), entry("l1")])
    assert {(p["bank_id"], p["ledger_id"]) for p in result["pairs"]} == {("b1", "l1"), ("b2", "l2")}


def test_variance_is_flagged_and_balances_bridge():
    result = match([entry("b", "-100.05")], [entry("l", "-100")])
    pair = result["pairs"][0]
    assert pair["rule"] == "variance_review"
    assert pair["variance"] == D("-0.05")
    assert result["controls"][0]["paired_variance"] == D("-0.05")
    assert result["controls"][0]["unexplained"] == 0


def test_accounts_and_currencies_never_cross_match():
    result = match([entry("b")], [entry("l", account="usd")])
    assert len(result["unmatched"]) == 2


def test_future_rows_do_not_leak_into_period():
    future = Entry("future", "cad", AS_OF + timedelta(days=1), D("10"), "INV-1")
    result = match([entry("b")], [future])
    assert result["ledger_count"] == 0
    assert result["controls"][0]["ledger_closing"] == D("100")


def test_opening_difference_is_explicit():
    accounts = (Account("cad", "CAD", date(2026, 7, 31), D("100"), D("90")),)
    result = reconcile(accounts, (), (), AS_OF)
    assert result["controls"][0]["opening_difference"] == 10
    assert result["controls"][0]["unexplained"] == 0


@pytest.mark.parametrize(
    "days,expected",
    [(0, "0-7"), (7, "0-7"), (8, "8-30"), (30, "8-30"), (31, "31-60"), (60, "31-60"), (61, "61+")],
)
def test_age_bucket_boundaries(days, expected):
    assert age_band(days) == expected


@pytest.mark.parametrize("window", [-1, 32])
def test_bad_windows_rejected(window):
    with pytest.raises(ValueError, match="window"):
        match([], [], window=window)


def test_sample_reconciliation(sample):
    result = reconcile(sample.accounts, sample.bank, sample.ledger, AS_OF)
    assert sum(p["variance"] == 0 for p in result["pairs"]) == 8
    assert sum(p["variance"] != 0 for p in result["pairs"]) == 1
    assert len(result["unmatched"]) == 7
    assert all(c["unexplained"] == 0 for c in result["controls"])
    assert next(i for i in result["unmatched"] if i["id"] == "L015")["age_band"] == "61+"
    shuffled = reconcile(
        sample.accounts, tuple(reversed(sample.bank)), tuple(reversed(sample.ledger)), AS_OF
    )
    assert result == shuffled
