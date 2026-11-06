"""Decimal-based translation and balanced, reference-matched elimination journals.

Trial balances are pre-close: debit positive, credit negative. No implicit FX
plug, suspense account, inferred counterparty or investment balancing entry.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")

# Fixed chart prevents an unrecognised account being silently omitted from a statement.
ACCOUNTS = {
    "cash": ("asset", "closing"),
    "trade_receivables": ("asset", "closing"),
    "inventory": ("asset", "closing"),
    "property_plant_equipment": ("asset", "closing"),
    "trade_payables": ("liability", "closing"),
    "debt": ("liability", "closing"),
    "investment": ("asset", "historical"),
    "share_capital": ("equity", "historical"),
    "opening_retained_earnings": ("equity", "historical"),
    "revenue": ("revenue", "average"),
    "cost_of_sales": ("expense", "average"),
    "operating_expense": ("expense", "average"),
    "finance_expense": ("expense", "average"),
    "tax_expense": ("expense", "average"),
    "ic_receivable": ("asset", "closing"),
    "ic_payable": ("liability", "closing"),
    "ic_service_revenue": ("revenue", "average"),
    "ic_service_expense": ("expense", "average"),
}
IC_PAIRS = {
    frozenset(("ic_receivable", "ic_payable")),
    frozenset(("ic_service_revenue", "ic_service_expense")),
}


class CloseError(ValueError):
    """A blocking reconciliation issue; amounts must be corrected at source."""


def number(value, label="amount"):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CloseError(f"{label}: expected a decimal number") from None
    if not result.is_finite():
        raise CloseError(f"{label}: must be finite")
    return result


@dataclass(frozen=True)
class Entry:
    entity: str
    account: str
    amount: Decimal
    partner: str = ""
    reference: str = ""
    historical_rate: Decimal | None = None

    def __post_init__(self):
        object.__setattr__(self, "amount", number(self.amount))
        if self.historical_rate is not None:
            object.__setattr__(
                self, "historical_rate", number(self.historical_rate, "historical rate")
            )

    @classmethod
    def from_row(cls, row):
        return cls(
            row["entity"],
            row["account"],
            number(row["amount"]),
            row.get("partner", ""),
            row.get("reference", ""),
            number(row["historical_rate"], "historical rate")
            if row.get("historical_rate")
            else None,
        )


@dataclass(frozen=True)
class Translated:
    entry: Entry
    rate: Decimal
    amount: Decimal


@dataclass
class Result:
    translated: list[Translated]
    journals: list[dict]
    balances: dict[str, Decimal]
    checks: list[dict]
    income: list[dict]
    position: list[dict]
    reserves: list[dict]


def validate_config(config):
    for assumption in ("formation_only", "services_fully_consumed", "average_rates_appropriate"):
        if config.get(assumption) is not True:
            raise CloseError(f"Unsupported scope: explicitly confirm {assumption} in config")
    try:
        date.fromisoformat(config["period"] + "-01")
        if len(config["period"]) != 7:
            raise ValueError
    except ValueError:
        raise CloseError("Actual period must be a valid YYYY-MM") from None
    if (
        not config["plan_periods"]
        or not config["plan_scenarios"]
        or any(len(p) != 4 or not p.isdigit() for p in config["plan_periods"])
    ):
        raise CloseError("Configure named planning scenarios and YYYY planning periods")
    entities = config.get("entities", {})
    parent = config.get("parent")
    if parent not in entities or len(entities) < 2 or "GROUP" in entities:
        raise CloseError("Define a parent and subsidiaries; GROUP is a reserved identifier")
    if entities[parent]["currency"] != config["presentation_currency"]:
        raise CloseError(
            "Parent functional currency must equal presentation currency in this model"
        )
    for name, entity in entities.items():
        if name != parent and number(entity.get("ownership", 0)) != 1:
            raise CloseError(f"{name}: only 100% ownership from formation is supported")
        if not entity.get("currency"):
            raise CloseError(f"{name}: missing functional currency")
        if "opening_cta" not in entity:
            raise CloseError(f"{name}: opening CTA must be supplied, including explicit zero")
        number(entity["opening_cta"], "opening CTA")
    if number(entities[parent]["opening_cta"]) != 0:
        raise CloseError("Parent opening CTA must be zero")
    seen = set()
    for rate in config["rates"]:
        key = (rate["scenario"], rate["period"], rate["currency"])
        if key in seen:
            raise CloseError(f"Duplicate FX rate: {key}")
        seen.add(key)
        for basis in ("closing", "average"):
            if number(rate[basis], f"{key} {basis}") <= 0:
                raise CloseError(f"{key}: FX rates must be positive")
            if rate["currency"] == config["presentation_currency"] and number(rate[basis]) != 1:
                raise CloseError("Presentation currency FX rate must be 1")


def translate(entries, config, scenario, period, *, plan=False):
    validate_config(config)
    entities = config["entities"]
    rates = {
        r["currency"]: r
        for r in config["rates"]
        if r["scenario"] == scenario and r["period"] == period
    }
    result = []
    for entry in entries:
        if entry.entity not in entities or entry.account not in ACCOUNTS:
            raise CloseError(f"Unknown entity/account: {entry.entity}/{entry.account}")
        kind, basis = ACCOUNTS[entry.account]
        if plan and kind not in ("revenue", "expense"):
            raise CloseError("Plan rows must be income or expense accounts")
        if entry.account.startswith("ic_"):
            if (
                entry.partner not in entities
                or entry.partner == entry.entity
                or not entry.reference
            ):
                raise CloseError(
                    f"{entry.entity}: intercompany row needs another group partner and reference"
                )
        elif entry.account == "investment":
            if (
                entry.entity != config["parent"]
                or entry.partner not in entities
                or entry.partner == entry.entity
            ):
                raise CloseError("Investment must identify a subsidiary held by the parent")
        elif entry.partner or entry.reference:
            raise CloseError(
                f"{entry.account}: unexpected partner/reference; use an intercompany account"
            )
        currency = entities[entry.entity]["currency"]
        if currency not in rates:
            raise CloseError(f"Missing FX rate for {scenario}/{period}/{currency}")
        if basis == "historical":
            rate = entry.historical_rate
            if rate is None or rate <= 0:
                raise CloseError(
                    f"{entry.entity}/{entry.account}: positive historical rate required"
                )
            if currency == config["presentation_currency"] and rate != 1:
                raise CloseError("Presentation currency historical rate must be 1")
        else:
            if entry.historical_rate is not None:
                raise CloseError(f"{entry.account}: historical rate is not applicable")
            rate = number(rates[currency][basis])
        result.append(Translated(entry, rate, entry.amount * rate))
    return result


def eliminate_intercompany(translated):
    pairs = defaultdict(list)
    for row in translated:
        e = row.entry
        if e.account.startswith("ic_"):
            pairs[(tuple(sorted((e.entity, e.partner))), e.reference)].append(row)
    journals, checks = [], []
    for (entities, reference), rows in sorted(pairs.items()):
        label = f"intercompany:{'/'.join(entities)}:{reference}"
        if (
            len(rows) != 2
            or frozenset(r.entry.account for r in rows) not in IC_PAIRS
            or rows[0].entry.entity != rows[1].entry.partner
            or rows[1].entry.entity != rows[0].entry.partner
        ):
            raise CloseError(f"{label}: unmatched or duplicate reciprocal items")
        difference = sum((r.amount for r in rows), ZERO)
        if difference != 0:
            raise CloseError(
                f"{label}: translated mismatch {difference}; correct source ledgers or FX"
            )
        for row in rows:
            journals.append(
                {
                    "entity": row.entry.entity,
                    "account": row.entry.account,
                    "reference": reference,
                    "amount": -row.amount,
                    "reason": "intercompany",
                }
            )
        checks.append({"check": label, "status": "PASS", "difference": difference})
    return journals, checks


def sum_accounts(rows, journals):
    result = {account: ZERO for account in ACCOUNTS}
    for row in rows:
        result[row.entry.account] += row.amount
    for row in journals:
        result[row["account"]] += row["amount"]
    return result


def income_statement(balances, oci=ZERO):
    revenue = -sum((v for a, v in balances.items() if ACCOUNTS[a][0] == "revenue"), ZERO)
    expenses = sum((v for a, v in balances.items() if ACCOUNTS[a][0] == "expense"), ZERO)
    profit = revenue - expenses
    return [
        {"line": line, "amount": amount}
        for line, amount in (
            ("revenue", revenue),
            ("cost_of_sales", balances["cost_of_sales"]),
            ("gross_profit", revenue - balances["cost_of_sales"]),
            ("operating_expense", balances["operating_expense"] + balances["ic_service_expense"]),
            ("finance_expense", balances["finance_expense"]),
            ("tax_expense", balances["tax_expense"]),
            ("profit_loss", profit),
            ("translation_oci", oci),
            ("total_comprehensive_income", profit + oci),
        )
    ]


def consolidate(entries, config):
    """Validate source trial balances, translate, eliminate and build close workpapers."""
    entries = list(entries)
    validate_config(config)
    checks = []
    for entity in config["entities"]:
        local = [e for e in entries if e.entity == entity]
        if not local:
            raise CloseError(f"{entity}: missing ledger")
        difference = sum((e.amount for e in local), ZERO)
        if difference != 0:
            raise CloseError(f"{entity}: unbalanced ledger {difference} in functional currency")
        checks.append(
            {"check": f"trial_balance:{entity}", "status": "PASS", "difference": difference}
        )
    rows = translate(entries, config, "Actual", config["period"])
    journals, ic_checks = eliminate_intercompany(rows)
    checks.extend(ic_checks)
    # Parent investment offsets only the subsidiary's original capital. Post-formation
    # retained earnings stay in group equity. No goodwill or acquisition plug is inferred.
    for entity in config["entities"]:
        if entity == config["parent"]:
            continue
        capital = [
            r for r in rows if r.entry.entity == entity and r.entry.account == "share_capital"
        ]
        investment = [
            r for r in rows if r.entry.account == "investment" and r.entry.partner == entity
        ]
        if not capital or not investment:
            raise CloseError(f"{entity}: missing formation capital or parent investment")
        amount = sum((r.amount for r in investment), ZERO)
        difference = amount + sum((r.amount for r in capital), ZERO)
        if amount <= 0 or difference != 0:
            raise CloseError(
                f"{entity}: investment/capital mismatch {difference}; unsupported acquisition"
            )
        for row in investment + capital:
            journals.append(
                {
                    "entity": row.entry.entity,
                    "account": row.entry.account,
                    "reference": f"formation:{entity}",
                    "amount": -row.amount,
                    "reason": "investment_capital",
                }
            )
        checks.append(
            {"check": f"investment_capital:{entity}", "status": "PASS", "difference": difference}
        )
    reserves = []
    for entity, details in config["entities"].items():
        # The source TB is proven balanced first; this residual is solely caused by
        # translating at different bases, not by inventing a missing ledger amount.
        closing = sum((r.amount for r in rows if r.entry.entity == entity), ZERO)
        opening = number(details["opening_cta"])
        reserves.append(
            {
                "entity": entity,
                "opening_cta": opening,
                "translation_oci": closing - opening,
                "closing_cta": closing,
            }
        )
    balances = sum_accounts(rows, journals)
    closing_cta = sum((r["closing_cta"] for r in reserves), ZERO)
    oci = sum((r["translation_oci"] for r in reserves), ZERO)
    income = income_statement(balances, oci)
    profit = next(r["amount"] for r in income if r["line"] == "profit_loss")
    assets = sum((v for a, v in balances.items() if ACCOUNTS[a][0] == "asset"), ZERO)
    liabilities = -sum((v for a, v in balances.items() if ACCOUNTS[a][0] == "liability"), ZERO)
    capital = -balances["share_capital"]
    opening_re = -balances["opening_retained_earnings"]
    equity = capital + opening_re + profit + closing_cta
    difference = assets - liabilities - equity
    if difference != 0:
        raise CloseError(
            f"Consolidated statement of financial position does not balance: {difference}"
        )
    if any(balances[a] != 0 for a in ACCOUNTS if a.startswith("ic_") or a == "investment"):
        raise CloseError("Intercompany/investment balances remain after elimination")
    checks.extend(
        [
            {"check": "consolidated_position", "status": "PASS", "difference": difference},
            {"check": "eliminations_cleared", "status": "PASS", "difference": ZERO},
            {
                "check": "cta_rollforward",
                "status": "PASS",
                "difference": closing_cta - oci - sum((r["opening_cta"] for r in reserves), ZERO),
            },
        ]
    )
    position = [
        {"line": a, "amount": v if ACCOUNTS[a][0] == "asset" else -v}
        for a, v in balances.items()
        if ACCOUNTS[a][0] in ("asset", "liability")
    ]
    position += [
        {"line": line, "amount": value}
        for line, value in (
            ("total_assets", assets),
            ("total_liabilities", liabilities),
            ("share_capital", capital),
            ("opening_retained_earnings", opening_re),
            ("current_profit", profit),
            ("closing_retained_earnings", opening_re + profit),
            ("translation_reserve", closing_cta),
            ("total_equity", equity),
            ("total_liabilities_and_equity", liabilities + equity),
        )
    ]
    return Result(rows, journals, balances, checks, income, position, reserves)


def roll_up_plan(plan_rows, config):
    """Return independently matched income-only scenario/year consolidations."""
    grouped = defaultdict(list)
    for row in plan_rows:
        scenario, period = row["scenario"], row["period"]
        if scenario == "Actual" or not scenario or not period:
            raise CloseError("Plan requires a named non-Actual scenario and period")
        grouped[(scenario, period)].append(Entry.from_row(row))
    if not grouped:
        raise CloseError("Plan is empty")
    expected = {(s, p) for s in config["plan_scenarios"] for p in config["plan_periods"]}
    if set(grouped) != expected:
        raise CloseError("Plan scenario/period coverage differs from configured planning horizon")
    results = {}
    for (scenario, period), entries in sorted(grouped.items()):
        if {e.entity for e in entries} != set(config["entities"]):
            raise CloseError(f"{scenario}/{period}: plan needs all group entities")
        translated = translate(entries, config, scenario, period, plan=True)
        journals, checks = eliminate_intercompany(translated)
        balances = sum_accounts(translated, journals)
        results[(scenario, period)] = Result(
            translated,
            journals,
            balances,
            checks,
            income_statement(balances),
            [],
            [],
        )
    return results
