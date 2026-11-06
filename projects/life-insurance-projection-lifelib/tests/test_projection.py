from dataclasses import replace
import math

import modelx as mx
import pytest

from insurance_projection.cli import load_cohorts, run
from insurance_projection.engine import Assumptions, Cohort, ProjectionEngine, load_mortality


@pytest.fixture
def engine():
    with ProjectionEngine() as e:
        yield e


def cohort(**overrides):
    return replace(Cohort("hand", "term", "male", 40, 1, 1000, 100, 3), **overrides)


def no_expenses(**overrides):
    return replace(Assumptions(lapse_first=0, lapse_renewal=0, acquisition=0, maintenance=0), **overrides)


@pytest.mark.parametrize("interest", [0, 0.05, -0.01])
def test_annuity_due_and_net_premium_by_hand(interest):
    # Independent 3-payment annuity and 3 end-year death benefits, q=10%.
    v = 1 / (1 + interest)
    annuity = 1 + 0.9 * v + 0.81 * v**2
    claims = 100 * v + 90 * v**2 + 81 * v**3
    with ProjectionEngine({"male": [0.1] * 120}) as e:
        p = e.project(cohort(), no_expenses(discount_rate=interest))
        assert p.summary["annuity_due"] == pytest.approx(annuity)
        assert p.summary["pv_claims"] == pytest.approx(claims)
        assert p.summary["net_premium"] == pytest.approx(claims / annuity)
        priced = e.project(cohort(annual_premium=claims / annuity), no_expenses(discount_rate=interest))
        assert priced.summary["pv_liabilities"] == pytest.approx(0, abs=1e-10)


def test_one_year_expenses_and_timing_by_hand():
    with ProjectionEngine({"male": [0.1] * 120}) as e:
        p = e.project(cohort(count=100, term=1), Assumptions(discount_rate=0.05, acquisition=20, maintenance=5))
    row = p.rows[0]
    assert row["premiums"] == 10000
    assert row["claims"] == 10000
    assert row["expenses"] == 2500
    assert row["cash_profit"] == -2500
    assert p.summary["pv_liabilities"] == pytest.approx(10000 / 1.05 + 2500 - 10000)
    assert row["closing"] == row["reserve_end"] == 0


def test_sequential_decrements_and_term_expiry():
    with ProjectionEngine({"male": [0.1] * 120}) as e:
        p = e.project(cohort(count=100), no_expenses(lapse_first=0.2, lapse_renewal=0.1))
    assert p.rows[0]["deaths"] == 10
    assert p.rows[0]["lapses"] == 18
    assert p.rows[1]["opening"] == 72
    assert p.rows[-1]["expiries"] > 0
    assert p.rows[-1]["closing"] == 0
    for r in p.rows:
        assert r["opening"] == pytest.approx(r["deaths"] + r["lapses"] + r["expiries"] + r["closing"])


@pytest.mark.parametrize("factor", [0.0, 0.8, 1.0, 1.2])
def test_whole_life_terminal_claim_and_no_survivors(engine, factor):
    c = cohort(product="whole_life", issue_age=119, term=None)
    p = engine.project(c, no_expenses(mortality_factor=factor))
    assert len(p.rows) == 1
    assert p.rows[0]["claims"] == 1000
    assert p.rows[0]["expiries"] == 0
    assert p.rows[0]["closing"] == 0
    assert p.summary["net_premium"] == pytest.approx(1000 / 1.03)


def test_two_year_whole_life_by_hand():
    rates = [0.5] * 119 + [1]
    with ProjectionEngine({"male": rates}) as e:
        p = e.project(cohort(product="whole_life", issue_age=118, term=None), no_expenses(discount_rate=0.05))
    annuity = 1 + 0.5 / 1.05
    claims = 500 / 1.05 + 500 / 1.05**2
    assert p.summary["annuity_due"] == pytest.approx(annuity)
    assert p.summary["net_premium"] == pytest.approx(claims / annuity)
    assert sum(r["deaths"] for r in p.rows) == 1


def test_real_lifelib_cells_and_cache_cleanup(engine):
    original_spaces = set(engine.model.spaces)
    assert "pols_if_beg1" in engine.model.BaseProj.cells
    assert "pv_claims_death" in engine.model.PV.cells
    for _ in range(2):
        p = engine.project(cohort(), no_expenses())
        assert p.rows[0]["deaths"] == pytest.approx(0.003353)
        assert set(engine.model.spaces) == original_spaces
    # These formulas are inherited unchanged and drive the exported outputs.
    assert "pols_if_beg1(t)" in engine.model.BaseProj.premiums.formula.source
    assert "pv_claims_death(t+1)" in engine.model.PV.pv_claims_death.formula.source


def test_reserve_matches_discounted_future_net_cashflows(engine):
    p = engine.project(cohort(count=100), Assumptions())
    i = p.assumptions.discount_rate
    for t, r in enumerate(p.rows):
        future = sum((x["expenses"] - x["premiums"]) / (1+i)**(u-t) + x["claims"] / (1+i)**(u-t+1)
                     for u, x in enumerate(p.rows) if u >= t)
        assert r["reserve_beg"] == pytest.approx(future)
        assert r["reserve_beg"] == pytest.approx(r["expenses"] - r["premiums"] + (r["claims"] + r["reserve_end"]) / (1+i))
    assert p.rows[0]["reserve_beg"] == pytest.approx(p.summary["pv_liabilities"])
    assert p.summary["pv_profit"] == pytest.approx(-p.summary["pv_liabilities"])


def test_sensitivities_reproject_and_reconcile():
    results = run(load_cohorts("examples/cohorts.csv"), Assumptions())
    assert len(results) == 7
    assert sum(p.cohort.count for p in results["Base"]) == 2500
    for name, projections in results.items():
        for p in projections:
            assert all(math.isfinite(v) for v in p.summary.values())
            for key in ("pv_premiums", "pv_claims", "pv_expenses"):
                assert p.summary[key] == pytest.approx(sum(r[key] for r in p.rows))
            assert all(r["opening"] >= 0 and r["closing"] >= 0 for r in p.rows)
    assert results["Mortality +20%"][0].summary["pv_claims"] > results["Base"][0].summary["pv_claims"]
    assert results["Lapse +50%"][0].rows[1]["opening"] < results["Base"][0].rows[1]["opening"]
    assert results["Discount +1pp"][0].rows[0]["claims"] == results["Base"][0].rows[0]["claims"]
    assert results["Discount +1pp"][0].summary["pv_claims"] < results["Base"][0].summary["pv_claims"]


@pytest.mark.parametrize("changes", [{"count": 0}, {"annual_premium": float("nan")}, {"issue_age": 120}, {"term": 0}, {"term": 81}, {"sex": "unknown"}, {"product": "endowment"}])
def test_invalid_cohorts(changes):
    with pytest.raises(ValueError):
        cohort(**changes)


@pytest.mark.parametrize("changes", [{"discount_rate": -1}, {"lapse_first": 1.1}, {"mortality_factor": -1}, {"maintenance": float("inf")}, {"inflation": float("nan")}])
def test_invalid_assumptions(changes):
    with pytest.raises(ValueError):
        Assumptions(**changes)


def test_table_source_sentinels():
    table = load_mortality()
    assert len(table["male"]) == len(table["female"]) == 120
    assert table["male"][0] == 0.006064
    assert table["male"][40] == 0.003353
    assert table["female"][55] == 0.005040
    assert table["male"][119] == table["female"][119] == 1


def test_closed_model_on_exception():
    before = set(mx.get_models())
    with pytest.raises(RuntimeError):
        with ProjectionEngine():
            raise RuntimeError("exercise failure cleanup")
    assert set(mx.get_models()) == before
