import json
import shutil
from decimal import Decimal as D
from pathlib import Path

import pytest

from ifrs_consolidation.annual import build_annual, classified_position
from ifrs_consolidation.cli import main, read_csv
from ifrs_consolidation.model import CloseError, Entry, consolidate

ANNUAL = Path(__file__).resolve().parents[1] / "examples" / "statutory_group"


@pytest.fixture
def annual_inputs():
    def load_config(name):
        return json.loads((ANNUAL / name).read_text())

    config = load_config("config.json")
    comparative_config = load_config("comparative_config.json")
    opening_config = load_config("opening_config.json")

    def close(name, cfg):
        return consolidate([Entry.from_row(r) for r in read_csv(ANNUAL / name)], cfg)

    return dict(
        current=close("ledger.csv", config),
        comparative=close("comparative_ledger.csv", comparative_config),
        opening=close("opening_ledger.csv", opening_config),
        config=config,
        comparative_config=comparative_config,
        opening_config=opening_config,
        disclosure=load_config("statutory.json"),
        cash_rows=read_csv(ANNUAL / "cash_movements.csv"),
        equity_rows=read_csv(ANNUAL / "equity_movements.csv"),
    )


def indexed(table):
    return {r["line"]: r for r in table}


def test_independent_annual_statements_comparatives_cash_and_tax(annual_inputs):
    result = build_annual(**annual_inputs)
    position = indexed(result.tables["annual_financial_position.csv"])
    income = indexed(result.tables["annual_income_and_oci.csv"])
    cash = indexed(result.tables["annual_cash_flows.csv"])
    assert position["total_assets"]["current"] == D("69456.50")
    assert position["total_liabilities_and_equity"]["current"] == D("69456.50")
    assert position["total_assets"]["comparative"] == D("54400")
    assert position["total_current_assets"]["current"] == D("69456.50")
    assert position["total_noncurrent_assets"]["current"] == 0
    assert income["revenue"]["current"] == D("41950")
    assert income["tax_expense"]["current"] == D("3718.50")
    assert income["profit_loss"]["current"] == D("11381.50")
    assert income["profit_loss"]["comparative"] == D("4400")
    assert income["translation_oci"]["current"] == D("3675")
    assert cash["customer_receipts"]["current"] == D("41950")
    assert cash["supplier_payments"]["current"] == D("-26850")
    assert cash["tax_paid"]["current"] == D("-3718.5")
    assert cash["net_operating_cash_flow"]["current"] == D("11381.5")
    assert cash["exchange_effect_on_cash"]["current"] == D("3675")
    assert cash["opening_cash"]["current"] == D("54400")
    assert cash["closing_cash"]["current"] == D("69456.5")
    assert cash["opening_cash"]["comparative"] == D("50000")
    assert cash["closing_cash"]["comparative"] == D("54400")
    assert len(result.checks) == 73
    assert all(c["difference"] == 0 for c in result.checks)


def test_equity_each_component_rolls_forward_for_both_years(annual_inputs):
    table = build_annual(**annual_inputs).tables["annual_changes_in_equity.csv"]
    for year in ("2025", "2026"):
        rows = [r for r in table if r["year"] == year]
        closing = rows[-1]
        for component in ("share_capital", "retained_earnings", "translation_reserve", "total"):
            assert sum(r[component] for r in rows[:-1]) == closing[component]
    final = next(r for r in table if r["year"] == "2026" and r["movement"] == "closing_balance")
    assert final["retained_earnings"] == D("15781.5")
    assert final["translation_reserve"] == D("3675")


def test_current_and_prior_tax_reconciliation_uses_loss_relief(annual_inputs):
    table = build_annual(**annual_inputs).tables["annual_tax_note.csv"]
    assert sum(r["tax_expense"] for r in table if r["year"] == "2026") == D("3718.5")
    assert sum(r["loss_relief"] for r in table if r["year"] == "2025") == D("1082")
    assert sum(r["tax_expense"] for r in table if r["year"] == "2025") == 0


def test_annual_pack_includes_sourced_notes_and_numerical_comparatives(annual_inputs):
    notes = build_annual(**annual_inputs).notes
    assert "Canada, federal CBCA" in notes
    assert "50,000.00" in notes
    assert "69,456.50 | 54,400.00" in notes
    assert annual_inputs["disclosure"]["going_concern"] in notes
    assert "Prior loss relief" in notes


def test_cash_difference_cannot_be_hidden_in_exchange_effect(annual_inputs):
    annual_inputs["cash_rows"][0]["amount"] = "1000.01"
    with pytest.raises(CloseError, match="mismatch 0.01"):
        build_annual(**annual_inputs)


def test_gross_cash_misclassification_fails_even_if_net_cash_is_unchanged(annual_inputs):
    annual_inputs["cash_rows"][0]["amount"] = "1100"
    annual_inputs["cash_rows"][1]["amount"] = "-1100"
    with pytest.raises(CloseError, match="cash_receipts_to_revenue"):
        build_annual(**annual_inputs)


def test_internal_cash_requires_matching_reference_and_transaction_rates(annual_inputs):
    annual_inputs["cash_rows"][-1]["rate"] = "1.51"
    with pytest.raises(CloseError, match="cash_elimination"):
        build_annual(**annual_inputs)


def test_one_sided_internal_cash_is_rejected(annual_inputs):
    annual_inputs["cash_rows"].pop()
    with pytest.raises(CloseError, match="unmatched internal cash"):
        build_annual(**annual_inputs)


def test_opening_retained_earnings_must_match_comparative_close(annual_inputs):
    entries = [Entry.from_row(r) for r in read_csv(ANNUAL / "ledger.csv")]
    entries += [
        Entry("CA", "opening_retained_earnings", D(-1), historical_rate=D(1)),
        Entry("CA", "cash", D(1)),
    ]
    annual_inputs["current"] = consolidate(entries, annual_inputs["config"])
    with pytest.raises(CloseError, match="retained_earnings_carry"):
        build_annual(**annual_inputs)


def test_opening_cta_must_match_prior_close(annual_inputs):
    annual_inputs["config"]["entities"]["US"]["opening_cta"] = "1"
    with pytest.raises(CloseError, match="cta_carry"):
        build_annual(**annual_inputs)


@pytest.mark.parametrize(
    "field", ["going_concern", "related_parties", "risk", "revenue_policy", "tax_policy"]
)
def test_missing_material_notes_block_publication(annual_inputs, field):
    annual_inputs["disclosure"][field] = ""
    with pytest.raises(CloseError, match="missing disclosure"):
        build_annual(**annual_inputs)


def test_equity_source_must_not_omit_entity(annual_inputs):
    annual_inputs["equity_rows"].pop()
    with pytest.raises(CloseError, match="one row per entity"):
        build_annual(**annual_inputs)


def test_unknown_dividend_cannot_be_dropped(annual_inputs):
    annual_inputs["equity_rows"][0]["dividends"] = "50"
    with pytest.raises(CloseError, match="capital changes or dividends"):
        build_annual(**annual_inputs)


def test_tax_expense_must_reconcile_to_entity_rate_and_losses(annual_inputs):
    annual_inputs["disclosure"]["tax"]["2026"]["US"]["rate"] = "0.22"
    with pytest.raises(CloseError, match="tax_reconciliation"):
        build_annual(**annual_inputs)


def test_annual_does_not_infer_a_different_jurisdiction(annual_inputs):
    annual_inputs["disclosure"]["jurisdiction"] = "United Kingdom"
    with pytest.raises(CloseError, match="Canadian federal"):
        build_annual(**annual_inputs)


def test_missing_comparative_year_cash_is_not_guessed(annual_inputs):
    annual_inputs["cash_rows"] = [r for r in annual_inputs["cash_rows"] if r["year"] == "2026"]
    with pytest.raises(CloseError, match="exactly current and comparative"):
        build_annual(**annual_inputs)


def test_annual_dates_must_match_consolidated_ledgers(annual_inputs):
    annual_inputs["disclosure"]["reporting_date"] = "2026-09-30"
    with pytest.raises(CloseError, match="matching CAD group"):
        build_annual(**annual_inputs)


def test_current_noncurrent_mapping_uses_actual_balances(config, entries):
    result = consolidate(
        entries + [Entry("CA", "property_plant_equipment", D(2500)), Entry("CA", "debt", D(-2500))],
        config,
    )
    position = classified_position(result)
    assert position["total_current_assets"] == D(73125)
    assert position["total_noncurrent_assets"] == D(2500)
    assert position["total_noncurrent_liabilities"] == D(2500)
    assert position["total_assets"] == D(75625)


def test_annual_command_generates_a_complete_readable_pack(tmp_path):
    output = tmp_path / "annual"
    assert main(["--statutory", "--input", str(ANNUAL), "--output", str(output)]) == 0
    assert len(read_csv(output / "reconciliation_checks.csv")) == 99
    assert len(read_csv(output / "annual_changes_in_equity.csv")) == 10
    assert len(json.loads((output / "status.json").read_text())["source_sha256"]) == 10
    report = (output / "annual_financial_statements.md").read_text()
    for part in (
        "annual financial position",
        "annual income and oci",
        "annual cash flows",
        "annual changes in equity",
        "Notes to the consolidated financial statements",
    ):
        assert part in report
    assert "69,456.50" in report
    assert "54,400.00" in report
    assert (
        next(r for r in read_csv(output / "dim_period.csv") if r["period"] == "2026-10")["grain"]
        == "year"
    )


def test_failed_annual_reconciliation_leaves_no_statements(tmp_path):
    source, output = tmp_path / "input", tmp_path / "blocked"
    shutil.copytree(ANNUAL, source)
    (source / "equity_movements.csv").write_text("year,entity,capital_contributions,dividends\n")
    assert main(["--statutory", "--input", str(source), "--output", str(output)]) == 1
    assert not (output / "annual_financial_statements.md").exists()
    assert not (output / "income_statement_and_oci.csv").exists()


def test_annual_new_external_sale_recomputes_tax_cash_and_equity(annual_inputs):
    entries = [Entry.from_row(r) for r in read_csv(ANNUAL / "ledger.csv")]
    entries += [
        Entry("CA", "cash", D("73.5")),
        Entry("CA", "revenue", D(-100)),
        Entry("CA", "tax_expense", D("26.5")),
    ]
    annual_inputs["current"] = consolidate(entries, annual_inputs["config"])
    for category, amount in [("customer_receipts", "100"), ("tax_paid", "-26.5")]:
        annual_inputs["cash_rows"].append(
            dict(
                year="2026",
                entity="CA",
                category=category,
                amount=amount,
                rate="1",
                partner="",
                reference="",
            )
        )
    pack = build_annual(**annual_inputs)
    assert indexed(pack.tables["annual_financial_position.csv"])["total_assets"]["current"] == D(
        69530
    )
    assert indexed(pack.tables["annual_income_and_oci.csv"])["tax_expense"]["current"] == D(3745)
    assert indexed(pack.tables["annual_cash_flows.csv"])["net_operating_cash_flow"]["current"] == D(
        11455
    )


def test_unsupported_annual_asset_needs_real_disclosures_before_publication(annual_inputs):
    entries = [Entry.from_row(r) for r in read_csv(ANNUAL / "ledger.csv")]
    entries += [Entry("CA", "cash", D(-100)), Entry("CA", "inventory", D(100))]
    annual_inputs["current"] = consolidate(entries, annual_inputs["config"])
    with pytest.raises(CloseError, match="unsupported material account"):
        build_annual(**annual_inputs)
