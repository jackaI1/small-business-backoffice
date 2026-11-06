from dataclasses import replace
from decimal import Decimal as D

import pytest

from ifrs_consolidation.model import (
    CloseError,
    Entry,
    consolidate,
    number,
    roll_up_plan,
    translate,
)


def amounts(rows):
    return {r["line"]: r["amount"] for r in rows}


def test_hand_calculated_group_statements_and_cta(config, entries):
    result = consolidate(entries, config)
    income, position = amounts(result.income), amounts(result.position)
    assert income["revenue"] == D("41700")
    assert income["profit_loss"] == D("15040")
    assert income["translation_oci"] == D("2885")
    assert income["total_comprehensive_income"] == D("17925")
    assert position["total_assets"] == D("73125")
    assert position["total_equity"] == D("73125")
    assert position["share_capital"] == D("50000")  # Only parent capital remains.
    assert position["closing_retained_earnings"] == D("19440")
    assert position["translation_reserve"] == D("3685")
    assert {r["entity"]: r["closing_cta"] for r in result.reserves} == {
        "CA": D(0),
        "US": D(2000),
        "EU": D(900),
        "UK": D(785),
    }
    assert len(result.checks) == 14
    assert all(c["difference"] == 0 for c in result.checks)


def test_explicit_translation_bases(config, entries):
    translated = translate(entries, config, "Actual", config["period"])
    lookup = {(r.entry.entity, r.entry.account): r for r in translated}
    assert lookup["US", "cash"].amount == D("20250")
    assert lookup["US", "revenue"].amount == D("-14400")
    assert lookup["US", "share_capital"].amount == D("-11000")
    assert lookup["US", "opening_retained_earnings"].amount == D("-2200")
    assert lookup["CA", "cash"].rate == 1


def test_eliminations_are_balanced_and_do_not_change_profit(config, entries):
    result = consolidate(entries, config)
    assert len(result.journals) == 14  # Four reciprocal pairs and three capital offsets.
    assert sum(j["amount"] for j in result.journals) == 0
    assert sum(j["amount"] for j in result.journals if j["reason"] == "intercompany") == 0
    for account in (
        "investment",
        "ic_receivable",
        "ic_payable",
        "ic_service_revenue",
        "ic_service_expense",
    ):
        assert result.balances[account] == 0
    assert amounts(result.income)["profit_loss"] == D("15040")


def test_nonzero_external_liabilities_still_reconcile(config, entries):
    entries += [Entry("CA", "cash", D(2000)), Entry("CA", "debt", D(-2000))]
    position = amounts(consolidate(entries, config).position)
    assert position["total_assets"] == D(75125)
    assert position["total_liabilities"] == D(2000)
    assert position["total_liabilities_and_equity"] == D(75125)


def test_realised_fx_loss_remains_in_profit_not_elimination(config, entries):
    entries += [Entry("US", "finance_expense", D(100)), Entry("US", "cash", D(-100))]
    result = consolidate(entries, config)
    assert amounts(result.income)["profit_loss"] == D(14920)
    assert amounts(result.income)["finance_expense"] == D(120)
    assert result.balances["ic_receivable"] == 0


def test_opening_cta_changes_oci_not_position(config, entries):
    first = consolidate(entries, config)
    config["entities"]["US"]["opening_cta"] = "1500"
    second = consolidate(entries, config)
    assert first.position == second.position
    assert amounts(second.income)["translation_oci"] == D(1885)


def test_unbalanced_source_cannot_be_hidden_in_cta(config, entries):
    entries[0] = replace(entries[0], amount=entries[0].amount + D("0.01"))
    with pytest.raises(CloseError, match="CA: unbalanced ledger 0.01"):
        consolidate(entries, config)


def test_one_sided_balance_fails_even_when_local_ledger_balances(config, entries):
    row = next(e for e in entries if e.account == "ic_payable")
    entries.remove(row)
    entries.append(replace(row, account="trade_payables", partner="", reference=""))
    with pytest.raises(CloseError, match="unmatched or duplicate"):
        consolidate(entries, config)


def test_one_cent_translated_mismatch_is_not_plugged(config, entries):
    for i, e in enumerate(entries):
        if e.entity == "EU" and e.account == "ic_payable":
            entries[i] = replace(e, amount=e.amount - D("0.01"))
        if e.entity == "EU" and e.account == "cash":
            entries[i] = replace(e, amount=e.amount + D("0.01"))
    with pytest.raises(CloseError, match="translated mismatch -0.0150"):
        consolidate(entries, config)


def test_split_or_duplicate_ic_reference_needs_source_resolution(config, entries):
    row = next(e for e in entries if e.account == "ic_receivable")
    i = entries.index(row)
    entries[i] = replace(row, amount=row.amount / 2)
    entries.append(entries[i])
    with pytest.raises(CloseError, match="unmatched or duplicate"):
        consolidate(entries, config)


def test_wrong_reciprocal_account_does_not_match(config, entries):
    rows = [
        replace(e, account="ic_receivable") if e.account == "ic_payable" else e for e in entries
    ]
    with pytest.raises(CloseError, match="unmatched or duplicate"):
        consolidate(rows, config)


def test_parent_investment_mismatch_fails_with_balanced_trial_balance(config, entries):
    entries += [
        Entry("CA", "investment", D(1), "US", historical_rate=D(1)),
        Entry("CA", "cash", D(-1)),
    ]
    with pytest.raises(CloseError, match="investment/capital mismatch"):
        consolidate(entries, config)


@pytest.mark.parametrize("ownership", ["0.8", "0", "1.1"])
def test_non_wholly_owned_entities_are_rejected(config, entries, ownership):
    config["entities"]["US"]["ownership"] = ownership
    with pytest.raises(CloseError, match="only 100%"):
        consolidate(entries, config)


@pytest.mark.parametrize("rate", ["0", "-1", "NaN", "Infinity"])
def test_invalid_exchange_rates_fail(config, entries, rate):
    next(r for r in config["rates"] if r["currency"] == "USD")["closing"] = rate
    with pytest.raises(CloseError):
        consolidate(entries, config)


def test_missing_rate_fails(config, entries):
    config["rates"] = [
        r for r in config["rates"] if not (r["scenario"] == "Actual" and r["currency"] == "EUR")
    ]
    with pytest.raises(CloseError, match="Missing FX rate"):
        consolidate(entries, config)


def test_duplicate_rate_is_not_silently_overwritten(config, entries):
    config["rates"].append(dict(config["rates"][0]))
    with pytest.raises(CloseError, match="Duplicate FX"):
        consolidate(entries, config)


def test_equity_needs_historical_rate(config, entries):
    entries = [
        replace(e, historical_rate=None) if e.account == "share_capital" else e for e in entries
    ]
    with pytest.raises(CloseError, match="historical rate required"):
        consolidate(entries, config)


def test_presentation_currency_rate_must_be_one(config, entries):
    config["rates"][0]["average"] = "1.2"
    with pytest.raises(CloseError, match="must be 1"):
        consolidate(entries, config)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "not-a-number"])
def test_nonfinite_or_invalid_money_is_rejected(value):
    with pytest.raises(CloseError):
        number(value)


def test_missing_entity_ledger_is_blocking(config, entries):
    with pytest.raises(CloseError, match="UK: missing ledger"):
        consolidate([e for e in entries if e.entity != "UK"], config)


def test_unknown_account_is_never_dropped(config, entries):
    entries[0] = replace(entries[0], account="suspense")
    with pytest.raises(CloseError, match="Unknown entity/account"):
        consolidate(entries, config)


def test_missing_partner_is_not_inferred(config, entries):
    i = next(i for i, e in enumerate(entries) if e.account == "ic_receivable")
    entries[i] = replace(entries[i], partner="")
    with pytest.raises(CloseError, match="another group partner"):
        consolidate(entries, config)


def test_plan_roll_up_all_years_scenarios_and_no_ic_remaining(config, plan):
    results = roll_up_plan(plan, config)
    assert len(results) == 6
    assert amounts(results["Base", "2027"].income)["profit_loss"] == D("16544")
    assert amounts(results["Base", "2029"].income)["profit_loss"] == D("20018.24")
    assert amounts(results["Downside", "2027"].income)["profit_loss"] == D("12421.8")
    for result in results.values():
        assert result.balances["ic_service_revenue"] == 0
        assert result.balances["ic_service_expense"] == 0


def test_plan_pairs_cannot_match_across_years(config, plan):
    row = next(r for r in plan if r["account"] == "ic_service_expense")
    row["reference"] += "-wrong-year"
    with pytest.raises(CloseError, match="unmatched or duplicate"):
        roll_up_plan(plan, config)


def test_plan_missing_horizon_is_rejected(config, plan):
    with pytest.raises(CloseError, match="coverage"):
        roll_up_plan([r for r in plan if r["period"] != "2029"], config)


def test_plan_missing_entity_is_rejected(config, plan):
    with pytest.raises(CloseError, match="all group entities"):
        roll_up_plan([r for r in plan if r["entity"] != "CA"], config)


def test_plan_balance_sheet_rows_rejected(config, plan):
    plan[0]["account"] = "cash"
    with pytest.raises(CloseError, match="income or expense"):
        roll_up_plan(plan, config)


def test_zero_reciprocal_balances_are_valid(config, entries):
    entries += [
        Entry("US", "ic_receivable", D(0), "CA", "ZERO"),
        Entry("CA", "ic_payable", D(0), "US", "ZERO"),
    ]
    assert len(consolidate(entries, config).checks) == 15


def test_opening_cta_must_be_explicit(config, entries):
    del config["entities"]["US"]["opening_cta"]
    with pytest.raises(CloseError, match="opening CTA must be supplied"):
        consolidate(entries, config)


@pytest.mark.parametrize(
    "assumption", ["formation_only", "services_fully_consumed", "average_rates_appropriate"]
)
def test_unsupported_reporting_scope_is_blocked(config, entries, assumption):
    config[assumption] = False
    with pytest.raises(CloseError, match="Unsupported scope"):
        consolidate(entries, config)


def test_wrong_period_is_not_accepted(config, entries):
    config["period"] = "2026-13"
    with pytest.raises(CloseError, match="valid YYYY-MM"):
        consolidate(entries, config)


def test_wrong_plan_average_rate_creates_blocking_ic_mismatch(config, plan):
    rate = next(
        r
        for r in config["rates"]
        if r["scenario"] == "Base" and r["period"] == "2027" and r["currency"] == "EUR"
    )
    rate["average"] = "1.6"
    with pytest.raises(CloseError, match="translated mismatch"):
        roll_up_plan(plan, config)
