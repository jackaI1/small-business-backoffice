"""Validated inputs and a scoped adapter over lifelib's actual model cells."""

from contextlib import AbstractContextManager
import csv
from dataclasses import dataclass, asdict
from importlib.resources import files
import math
from pathlib import Path

import lifelib
import modelx as mx

from . import cells

MORTALITY_SOURCE = "https://www.ssa.gov/oact/STATS/table4c6_2022_TR2025.html"


def finite_number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum}")


@dataclass(frozen=True)
class Cohort:
    id: str
    product: str
    sex: str
    issue_age: int
    count: float
    benefit: float
    annual_premium: float
    term: int | None = None

    def __post_init__(self):
        if not self.id or not self.id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("cohort id must contain only letters, numbers, underscores or hyphens")
        if self.product not in ("term", "whole_life") or self.sex not in ("male", "female"):
            raise ValueError("product must be term/whole_life and sex must be male/female")
        if type(self.issue_age) is not int or not 0 <= self.issue_age <= 119:
            raise ValueError("issue_age must be an integer from 0 through 119")
        if self.product == "term":
            if type(self.term) is not int or not 1 <= self.term <= 120 - self.issue_age:
                raise ValueError("term must be a positive integer within the mortality table")
        elif self.term is not None:
            raise ValueError("whole_life uses the full mortality table; omit term")
        for name in ("count", "benefit", "annual_premium"):
            finite_number(getattr(self, name), name)
        if self.count == 0 or self.benefit == 0:
            raise ValueError("count and benefit must be positive")

    @property
    def years(self):
        return self.term if self.product == "term" else 120 - self.issue_age


@dataclass(frozen=True)
class Assumptions:
    discount_rate: float = 0.03
    mortality_factor: float = 1.0
    lapse_first: float = 0.08
    lapse_renewal: float = 0.04
    lapse_factor: float = 1.0
    acquisition: float = 200.0
    maintenance: float = 40.0
    inflation: float = 0.02

    def __post_init__(self):
        for name, value in asdict(self).items():
            finite_number(value, name, -0.99 if name in ("discount_rate", "inflation") else 0)
        if self.lapse_first > 1 or self.lapse_renewal > 1:
            raise ValueError("lapse probabilities must be between 0 and 1")


def load_mortality():
    with files("insurance_projection").joinpath("data/ssa_2022.csv").open() as source:
        rows = list(csv.DictReader(source))
    if [int(row["age"]) for row in rows] != list(range(120)):
        raise ValueError("mortality table must cover every age 0 through 119")
    table = {sex: tuple(float(row[sex]) for row in rows) for sex in ("male", "female")}
    if any(not math.isfinite(q) or not 0 <= q <= 1 for rates in table.values() for q in rates):
        raise ValueError("invalid mortality probability")
    if any(rates[-1] != 1 for rates in table.values()):
        raise ValueError("terminal mortality must equal 1")
    return table


@dataclass
class Projection:
    cohort: Cohort
    assumptions: Assumptions
    rows: list[dict]
    summary: dict


class ProjectionEngine(AbstractContextManager):
    """Load lifelib once, release every model and its cell cache on exit."""

    def __init__(self, mortality=None):
        self.mortality = load_mortality() if mortality is None else mortality
        model_path = Path(lifelib.__file__).parent / "libraries/annuallife/TradLife_A"
        self.model = mx.read_model(str(model_path))
        self.serial = 0

    def __exit__(self, *args):
        self.model.close()

    def project(self, cohort: Cohort, assumptions: Assumptions) -> Projection:
        rates = self.mortality[cohort.sex]
        if len(rates) < cohort.issue_age + cohort.years or any(not math.isfinite(q) or not 0 <= q <= 1 for q in rates):
            raise ValueError("mortality rates are invalid or do not cover this cohort")
        self.serial += 1
        space = self.model.new_space(f"Run{self.serial}", bases=[self.model.BaseProj, self.model.PV])
        try:
            space.cohort, space.assumptions, space.mortality = cohort, assumptions, rates
            for name in dir(cells):
                formula = getattr(cells, name)
                if callable(formula) and not name.startswith("_"):
                    if name in space.cells:
                        space.cells[name].formula = formula
                    else:
                        space.new_cells(name=name, formula=formula)
            rows = []
            for t in range(cohort.years):
                # The exposure, premium, claim, expense and PV calculations below
                # are inherited lifelib cells, not a parallel Python projection.
                opening = space.pols_if_beg1(t)
                deaths, lapses = space.pols_death(t), space.pols_lapse(t)
                survivors = space.pols_if(t + 1)
                premium, claim, expense = space.premiums(t), space.claims(t), space.expenses(t)
                reserve = space.pv_claims(t) + space.pv_expenses(t) - space.pv_premiums(t)
                closing_reserve = space.pv_claims(t + 1) + space.pv_expenses(t + 1) - space.pv_premiums(t + 1)
                rows.append(dict(year=t + 1, age=space.age(t), opening=opening,
                                 mortality=space.mort_rate(space.age(t)), lapse=space.lapse_rate(t),
                                 deaths=deaths, lapses=lapses,
                                 expiries=survivors if t == cohort.years - 1 else 0.0,
                                 closing=0.0 if t == cohort.years - 1 else survivors,
                                 premiums=premium, claims=claim, expenses=expense,
                                 cash_profit=space.net_cf(t), reserve_beg=reserve,
                                 reserve_end=closing_reserve,
                                 pv_premiums=premium / (1 + assumptions.discount_rate) ** t,
                                 pv_claims=claim / (1 + assumptions.discount_rate) ** (t + 1),
                                 pv_expenses=expense / (1 + assumptions.discount_rate) ** t))
            pv_premiums = space.pv_premiums(0)
            pv_claims, pv_expenses = space.pv_claims(0), space.pv_expenses(0)
            annuity = space.pv_sum_insur_if(0) / cohort.benefit / cohort.count
            return Projection(cohort, assumptions, rows, dict(
                pv_premiums=pv_premiums, pv_claims=pv_claims, pv_expenses=pv_expenses,
                pv_liabilities=pv_claims + pv_expenses - pv_premiums,
                pv_profit=space.pv_net_cf(0), annuity_due=annuity,
                net_premium=pv_claims / cohort.count / annuity))
        finally:
            delattr(self.model, space.name)
