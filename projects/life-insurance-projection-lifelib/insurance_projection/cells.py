"""Modelx overrides for the lifelib TradLife_A annual projection.

Names such as cohort and assumptions are references injected into the Space,
not Python globals. The inherited lifelib cells call these formulas.
"""


def age(t):
    return cohort.issue_age + t


def proj_len():
    # lifelib's PV recursion includes t == proj_len().
    return cohort.years - 1


def pols_if_init(t):
    return cohort.count if t == 0 else 0


def pols_maturity(t):
    return pols_if(t) if t == cohort.years else 0


def sum_assured(t):
    return cohort.benefit


def mort_rate(x):
    # Preserve the terminal q=1 under mortality improvements too.
    return 1.0 if x == 119 else min(1.0, mortality[x] * assumptions.mortality_factor)


def mort_factor(t):
    return 1.0


def lapse_rate(t):
    base = assumptions.lapse_first if t == 0 else assumptions.lapse_renewal
    return min(1.0, base * assumptions.lapse_factor)


def pols_lapse(t):
    return (pols_if_beg1(t) - pols_death(t)) * lapse_rate(t)


def premium_pp(t):
    return cohort.annual_premium


def expense_acq_pp(t):
    return assumptions.acquisition if t == 0 else 0.0


def expense_maint_pp(t):
    return assumptions.maintenance * (1 + assumptions.inflation) ** t


def commissions_init_pp(t):
    return 0.0


def commissions_ren_pp(t):
    return 0.0


def claims_surr_pp(t):
    return 0.0


def disc_rate(t):
    return assumptions.discount_rate
