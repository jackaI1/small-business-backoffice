"""Comparative annual statements for an explicitly scoped Canadian service group.

Cash flow sources are actual movement schedules, not a difference used as a plug.
Opening, comparative and current ledgers are independently consolidated first.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .model import ACCOUNTS, ZERO, CloseError, Result, number

NOTE_FIELDS = (
    "entity_name",
    "jurisdiction",
    "basis",
    "reporting_date",
    "comparative_date",
    "opening_date",
    "authorisation_date",
    "authorised_by",
    "registered_office",
    "activity",
    "profile",
    "share_count",
    "share_class",
    "ultimate_control",
    "going_concern",
    "revenue_policy",
    "financial_instruments_policy",
    "risk",
    "capital_management",
    "judgments",
    "related_parties",
    "commitments",
    "subsequent_events",
    "new_standards",
    "restatements",
    "tax_policy",
)
FLOW_CATEGORIES = {
    "customer_receipts",
    "supplier_payments",
    "tax_paid",
    "investing",
    "financing",
    "internal_receipts",
    "internal_payments",
}


@dataclass
class AnnualPack:
    tables: dict[str, list[dict]]
    checks: list[dict]
    notes: str
    title: str


def lines(rows):
    return {r["line"]: r["amount"] for r in rows}


def entity_balance(result, entity, account):
    return sum(
        (
            r.amount
            for r in result.translated
            if r.entry.entity == entity and r.entry.account == account
        ),
        ZERO,
    )


def entity_profit(result, entity):
    return -sum(
        (
            r.amount
            for r in result.translated
            if r.entry.entity == entity and ACCOUNTS[r.entry.account][0] in ("revenue", "expense")
        ),
        ZERO,
    )


def require_equal(checks, name, actual, expected):
    difference = actual - expected
    if difference != 0:
        raise CloseError(f"Annual {name}: mismatch {difference}")
    checks.append({"check": f"annual:{name}", "status": "PASS", "difference": difference})


def classified_position(result):
    """Explicit current/non-current classification for the fixed chart."""
    b = result.balances
    current_assets = sum(
        (b[a] for a in ("cash", "trade_receivables", "inventory", "ic_receivable")), ZERO
    )
    noncurrent_assets = b["property_plant_equipment"] + b["investment"]
    current_liabilities = -b["trade_payables"] - b["ic_payable"]
    noncurrent_liabilities = -b[
        "debt"
    ]  # Annual profile rejects debt, so maturity is never inferred.
    p = lines(result.position)
    return {
        "cash_and_cash_equivalents": b["cash"],
        "other_current_assets": current_assets - b["cash"],
        "total_current_assets": current_assets,
        "property_plant_equipment": b["property_plant_equipment"],
        "total_noncurrent_assets": noncurrent_assets,
        "total_assets": current_assets + noncurrent_assets,
        "total_current_liabilities": current_liabilities,
        "total_noncurrent_liabilities": noncurrent_liabilities,
        "total_liabilities": current_liabilities + noncurrent_liabilities,
        "share_capital": p["share_capital"],
        "retained_earnings": p["closing_retained_earnings"],
        "translation_reserve": p["translation_reserve"],
        "total_equity": p["total_equity"],
        "total_liabilities_and_equity": p["total_liabilities_and_equity"],
    }


def cash_statement(current, previous, config, year, cash_rows, checks):
    entities = set(config["entities"])
    selected = [r for r in cash_rows if r["year"] == year]
    if {r["entity"] for r in selected} != entities:
        raise CloseError(f"Annual {year}: cash schedule needs exactly the group entities")
    local = defaultdict(Decimal)
    converted = defaultdict(Decimal)
    categories = defaultdict(Decimal)
    internal = defaultdict(list)
    for r in selected:
        entity, category = r["entity"], r["category"]
        if category not in FLOW_CATEGORIES:
            raise CloseError(f"Annual {year}: unsupported cash movement {category}")
        amount, rate = number(r["amount"]), number(r["rate"])
        if category in ("investing", "financing") and amount != 0:
            raise CloseError("Annual cash-only profile has no investing or financing transactions")
        if rate <= 0 or (entity == config["parent"] and rate != 1):
            raise CloseError("Annual cash transaction rates must be positive, and 1 for the parent")
        if category.endswith("receipts") and amount < 0:
            raise CloseError("Annual cash receipts must be positive")
        if category in ("supplier_payments", "tax_paid", "internal_payments") and amount > 0:
            raise CloseError("Annual cash payments must be negative")
        local[entity] += amount
        converted[entity] += amount * rate
        categories[category] += amount * rate
        if category.startswith("internal_"):
            if r["partner"] not in entities or r["partner"] == entity or not r["reference"]:
                raise CloseError("Annual internal cash needs partner and reference")
            internal[(tuple(sorted((entity, r["partner"]))), r["reference"])].append(r)
        elif r["partner"] or r["reference"]:
            raise CloseError("Annual external cash must not identify an internal partner/reference")
    for (_, ref), pair in internal.items():
        if (
            len(pair) != 2
            or {r["category"] for r in pair} != {"internal_receipts", "internal_payments"}
            or pair[0]["entity"] != pair[1]["partner"]
            or pair[1]["entity"] != pair[0]["partner"]
        ):
            raise CloseError(f"Annual {year}/{ref}: unmatched internal cash")
        require_equal(
            checks,
            f"{year}/{ref}/cash_elimination",
            sum((number(r["amount"]) * number(r["rate"]) for r in pair), ZERO),
            ZERO,
        )
    exchange_effect = ZERO
    for entity in sorted(entities):
        opening_local = sum(
            (
                r.entry.amount
                for r in previous.translated
                if r.entry.entity == entity and r.entry.account == "cash"
            ),
            ZERO,
        )
        closing_local = sum(
            (
                r.entry.amount
                for r in current.translated
                if r.entry.entity == entity and r.entry.account == "cash"
            ),
            ZERO,
        )
        require_equal(
            checks, f"{year}/{entity}/local_cash", local[entity], closing_local - opening_local
        )
        # IAS 7: the exchange effect on cash is separate from cash flows. Local movement
        # and transaction rates are validated above; this is not an operating-flow plug.
        exchange_effect += (
            entity_balance(current, entity, "cash")
            - entity_balance(previous, entity, "cash")
            - converted[entity]
        )
    result = {k: categories[k] for k in ("customer_receipts", "supplier_payments", "tax_paid")}
    require_equal(
        checks,
        f"{year}/cash_receipts_to_revenue",
        result["customer_receipts"],
        lines(current.income)["revenue"],
    )
    require_equal(
        checks,
        f"{year}/cash_payments_to_costs",
        -result["supplier_payments"],
        current.balances["cost_of_sales"] + current.balances["operating_expense"],
    )
    result["net_operating_cash_flow"] = sum(result.values(), ZERO)
    result["net_investing_cash_flow"] = categories["investing"]
    result["net_financing_cash_flow"] = categories["financing"]
    result["net_cash_flow"] = sum(
        (
            result[k]
            for k in (
                "net_operating_cash_flow",
                "net_investing_cash_flow",
                "net_financing_cash_flow",
            )
        ),
        ZERO,
    )
    result["exchange_effect_on_cash"] = exchange_effect
    result["opening_cash"] = previous.balances["cash"]
    result["closing_cash"] = current.balances["cash"]
    require_equal(
        checks,
        f"{year}/cash_bridge",
        result["closing_cash"],
        result["opening_cash"] + result["net_cash_flow"] + exchange_effect,
    )
    require_equal(
        checks, f"{year}/cash_tax_to_income", -result["tax_paid"], current.balances["tax_expense"]
    )
    require_equal(
        checks,
        f"{year}/operating_to_profit",
        result["net_operating_cash_flow"],
        lines(current.income)["profit_loss"],
    )
    return result


def equity_statement(current, previous, config, year, movements, checks):
    rows = [r for r in movements if r["year"] == year]
    if len(rows) != len(config["entities"]) or {r["entity"] for r in rows} != set(
        config["entities"]
    ):
        raise CloseError(f"Annual {year}: equity schedule requires one row per entity")
    for row in rows:
        if number(row["capital_contributions"]) != 0 or number(row["dividends"]) != 0:
            raise CloseError("Annual profile does not support capital changes or dividends")
    previous_position, current_position = lines(previous.position), lines(current.position)
    for entity, details in config["entities"].items():
        opening_re = -entity_balance(current, entity, "opening_retained_earnings")
        previous_re = -entity_balance(
            previous, entity, "opening_retained_earnings"
        ) + entity_profit(previous, entity)
        require_equal(checks, f"{year}/{entity}/retained_earnings_carry", opening_re, previous_re)
        require_equal(
            checks,
            f"{year}/{entity}/capital_carry",
            entity_balance(current, entity, "share_capital"),
            entity_balance(previous, entity, "share_capital"),
        )
        previous_cta = next(r["closing_cta"] for r in previous.reserves if r["entity"] == entity)
        require_equal(
            checks, f"{year}/{entity}/cta_carry", number(details["opening_cta"]), previous_cta
        )
    profit = lines(current.income)["profit_loss"]
    oci = lines(current.income)["translation_oci"]
    require_equal(
        checks,
        f"{year}/equity_bridge",
        current_position["total_equity"],
        previous_position["total_equity"] + profit + oci,
    )
    return [
        {
            "movement": "opening_balance",
            "share_capital": previous_position["share_capital"],
            "retained_earnings": previous_position["closing_retained_earnings"],
            "translation_reserve": previous_position["translation_reserve"],
            "total": previous_position["total_equity"],
        },
        {
            "movement": "profit_loss",
            "share_capital": ZERO,
            "retained_earnings": profit,
            "translation_reserve": ZERO,
            "total": profit,
        },
        {
            "movement": "translation_oci",
            "share_capital": ZERO,
            "retained_earnings": ZERO,
            "translation_reserve": oci,
            "total": oci,
        },
        {
            "movement": "owner_contributions_and_distributions",
            "share_capital": ZERO,
            "retained_earnings": ZERO,
            "translation_reserve": ZERO,
            "total": ZERO,
        },
        {
            "movement": "closing_balance",
            "share_capital": current_position["share_capital"],
            "retained_earnings": current_position["closing_retained_earnings"],
            "translation_reserve": current_position["translation_reserve"],
            "total": current_position["total_equity"],
        },
    ]


def build_annual(
    current: Result,
    comparative: Result,
    opening: Result,
    config,
    comparative_config,
    opening_config,
    disclosure,
    cash_rows,
    equity_rows,
):
    for key in NOTE_FIELDS:
        if not isinstance(disclosure.get(key), str) or not disclosure[key].strip():
            raise CloseError(f"Annual missing disclosure: {key}")
    if (
        disclosure["jurisdiction"] != "Canada, federal CBCA"
        or disclosure["profile"] != "cash_only_service_group"
    ):
        raise CloseError("Annual supports the Canadian federal cash-only service-group profile")
    if number(disclosure["share_count"]) <= 0:
        raise CloseError("Annual share count must be positive")
    dates = [
        date.fromisoformat(disclosure[k])
        for k in ("opening_date", "comparative_date", "reporting_date", "authorisation_date")
    ]
    if not dates[0] < dates[1] < dates[2] <= dates[3]:
        raise CloseError("Annual reporting and authorisation dates are not ordered")
    configs = [opening_config, comparative_config, config]
    for i, (cfg, reporting_date) in enumerate(zip(configs, dates[:3], strict=True)):
        if (
            cfg["period"] != reporting_date.isoformat()[:7]
            or cfg["presentation_currency"] != "CAD"
            or cfg["parent"] != config["parent"]
            or cfg["entities"].keys() != config["entities"].keys()
        ):
            raise CloseError("Annual ledgers must use matching CAD group and reporting periods")
        for entity in config["entities"]:
            if cfg["entities"][entity]["currency"] != config["entities"][entity]["currency"]:
                raise CloseError("Annual changes of functional currency are unsupported")
        if i and (
            reporting_date.year != dates[i - 1].year + 1
            or (reporting_date.month, reporting_date.day) != (dates[i - 1].month, dates[i - 1].day)
        ):
            raise CloseError("Annual periods must be consecutive years with the same year-end")
    years = {str(dates[1].year), str(dates[2].year)}
    if {r["year"] for r in cash_rows} != years or {r["year"] for r in equity_rows} != years:
        raise CloseError("Annual movement schedules require exactly current and comparative years")
    # This profile has no external working capital, PPE, debt or non-cash items.
    # The base engine still supports these accounts in workpapers; annual notes must
    # be extended before accepting them into a statutory pack.
    allowed = {
        "cash",
        "investment",
        "share_capital",
        "opening_retained_earnings",
        "revenue",
        "cost_of_sales",
        "operating_expense",
        "tax_expense",
        "ic_receivable",
        "ic_payable",
        "ic_service_revenue",
        "ic_service_expense",
    }
    for result in (opening, comparative, current):
        if any(r.amount != 0 and r.entry.account not in allowed for r in result.translated):
            raise CloseError(
                "Annual profile has an unsupported material account; "
                "extend notes and movements first"
            )
    checks = [
        {**c, "check": f"annual_source:{cfg['period']}:{c['check']}"}
        for result, cfg in ((comparative, comparative_config), (opening, opening_config))
        for c in result.checks
    ]
    equity, flows, tax_rows = [], {}, []
    for result, prev, cfg, year in (
        (comparative, opening, comparative_config, str(dates[1].year)),
        (current, comparative, config, str(dates[2].year)),
    ):
        equity.extend(
            {"year": year, **r}
            for r in equity_statement(result, prev, cfg, year, equity_rows, checks)
        )
        flows[year] = cash_statement(result, prev, cfg, year, cash_rows, checks)
        for entity in cfg["entities"]:
            source = disclosure["tax"][year][entity]
            rate, losses = number(source["rate"]), number(source["losses_used"])
            expense = entity_balance(result, entity, "tax_expense")
            pretax = entity_profit(result, entity) + expense
            average = next(
                number(r["average"])
                for r in cfg["rates"]
                if r["scenario"] == "Actual"
                and r["period"] == cfg["period"]
                and r["currency"] == cfg["entities"][entity]["currency"]
            )
            if (
                rate < 0
                or rate > 1
                or losses < 0
                or losses * average > pretax
                or number(source["deferred_tax"]) != 0
                or number(source["unrecognised_losses"]) != 0
            ):
                raise CloseError("Annual tax inputs fall outside the current-tax-only profile")
            expected = (pretax - losses * average) * rate
            require_equal(checks, f"{year}/{entity}/tax_reconciliation", expense, expected)
            tax_rows.append(
                {
                    "year": year,
                    "entity": entity,
                    "pretax_profit": pretax,
                    "rate": rate,
                    "loss_relief": losses * average * rate,
                    "tax_expense": expense,
                }
            )
    current_year, previous_year = str(dates[2].year), str(dates[1].year)

    def comparative_rows(now, before):
        return [{"line": k, "current": v, "comparative": before[k]} for k, v in now.items()]

    tables = {
        "annual_financial_position.csv": comparative_rows(
            classified_position(current), classified_position(comparative)
        ),
        "annual_income_and_oci.csv": comparative_rows(
            lines(current.income), lines(comparative.income)
        ),
        "annual_cash_flows.csv": comparative_rows(flows[current_year], flows[previous_year]),
        "annual_changes_in_equity.csv": equity,
        "annual_tax_note.csv": tax_rows,
    }
    # Notes contain quantitative comparative information driven by reconciled ledgers.
    quantitative = [
        "## Supporting amounts (CAD)",
        "",
        "| Disclosure | Current | Comparative |",
        "| --- | ---: | ---: |",
    ]
    for label, now, before in (
        ("Unrestricted cash", current.balances["cash"], comparative.balances["cash"]),
        (
            "External revenue",
            lines(current.income)["revenue"],
            lines(comparative.income)["revenue"],
        ),
        (
            "Current income tax",
            current.balances["tax_expense"],
            comparative.balances["tax_expense"],
        ),
        ("Deferred tax, commitments, key management compensation", ZERO, ZERO),
        (
            "Common shares outstanding (count)",
            number(disclosure["share_count"]),
            number(disclosure["share_count"]),
        ),
    ):
        quantitative.append(f"| {label} | {now:,.2f} | {before:,.2f} |")
    quantitative += [
        "",
        "## Subsidiaries, currency and external revenue (CAD)",
        "",
        "| Entity | Country | Currency | Ownership | Current | Comparative |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for entity, details in config["entities"].items():
        quantitative.append(
            f"| {details['name']} | {disclosure['countries'][entity]} | "
            f"{details['currency']} | 100% | "
            f"{-entity_balance(current, entity, 'revenue'):,.2f} | "
            f"{-entity_balance(comparative, entity, 'revenue'):,.2f} |"
        )
    policies = [
        f"## {key.replace('_', ' ').capitalize()}\n\n{disclosure[key]}\n"
        for key in NOTE_FIELDS
        if key
        not in {"profile", "share_count", "reporting_date", "comparative_date", "opening_date"}
    ]
    notes = (
        "# Notes to the consolidated financial statements\n\n"
        "All entities and disclosures are synthetic. Amounts are CAD unless labelled otherwise. "
        "These annual statements are prepared for review, not filed or audited.\n\n"
        "## Basis and material policies\n\n"
        "This synthetic statement set is prepared on the IFRS Accounting Standards basis "
        "incorporated in Part I of the CPA Canada Handbook for this supported service-group "
        "scenario. The group is a continuing IFRS reporter, not a first-time adopter. "
        "Accrual accounting, historical cost and consistent policies apply. "
        "Subsidiaries are consolidated "
        "from formation; investments and all intragroup balances, "
        "income, expenses and cash transfers "
        "are eliminated. Assets and liabilities use closing FX, income and expense average FX, "
        "capital historical FX and opening retained earnings the prior translated amount. "
        "Translation OCI is reclassifiable on disposal; "
        "there are no disposals or tax effects on OCI "
        "in this scenario. Cash means unrestricted demand deposits; there are no overdrafts or "
        "cash equivalents. Operating cash flow uses the direct method, with tax paid separately. "
        "No investing, financing or non-cash transactions occurred. There are no discontinued "
        "operations, NCI, other OCI items or exceptional items. Basic/diluted EPS and segment "
        "reporting are not required for this privately held, unlisted profile.\n\n"
        + "\n".join(policies)
        + "\n"
        + "\n".join(quantitative)
        + "\n\nThe detailed tax-rate reconciliation is in annual_tax_note.csv. "
        "The equity statement reconciles every reserve and shows no owner transactions. "
        f"Share capital is CAD {lines(current.position)['share_capital']:,.2f} "
        f"(comparative {lines(comparative.position)['share_capital']:,.2f}); "
        "no shares were issued or cancelled. "
        "Prior loss relief reduced tax to zero; current tax equals the sum of each entity's "
        "profit at the supplied local rate. No tax effects are allocated to OCI.\n"
    )
    return AnnualPack(
        tables,
        checks,
        notes,
        f"{disclosure['entity_name']}\nYears ended {disclosure['reporting_date']} "
        f"and {disclosure['comparative_date']}",
    )
