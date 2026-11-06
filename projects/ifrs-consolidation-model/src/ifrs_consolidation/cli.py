"""CSV interface and review pack. Failed closes never produce statements."""

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .annual import build_annual
from .model import ACCOUNTS, CloseError, Entry, consolidate, roll_up_plan

MANUAL_CHECKS = (
    "Review average rates against transaction-date rates; confirm no material volatility",
    "Approve historical equity rates and opening retained earnings/translation reserves",
    "Confirm control, formation-only ownership, and fully consumed intercompany services",
    "Review local ledgers, tax, cut-off, classifications and disclosure requirements",
    "Review cash flows, changes in equity, comparatives and notes before statutory sign-off",
)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise CloseError(f"{Path(path).name}: missing or duplicate CSV headers")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise CloseError(f"{Path(path).name}: row width does not match CSV headers")
        return rows


def write_csv(path, rows, fields):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: format(value, "f") if isinstance(value, Decimal) else value
                    for key, value in row.items()
                }
            )


def checklist(output, checks):
    rows = [{**c, "owner": "model", "evidence": "reconciliation_checks.csv"} for c in checks]
    rows += [
        {
            "check": task,
            "status": "REVIEW_REQUIRED",
            "difference": "",
            "owner": "preparer/reviewer",
            "evidence": "manual approval required",
        }
        for task in MANUAL_CHECKS
    ]
    write_csv(
        output / "month_end_checklist.csv",
        rows,
        ["check", "status", "difference", "owner", "evidence"],
    )


def export_pack(output, config, actual, plans, annual=None):
    write_csv(output / "statement_of_financial_position.csv", actual.position, ["line", "amount"])
    write_csv(output / "income_statement_and_oci.csv", actual.income, ["line", "amount"])
    write_csv(
        output / "translation_reserve.csv",
        actual.reserves,
        ["entity", "opening_cta", "translation_oci", "closing_cta"],
    )
    all_results = {("Actual", config["period"]): actual, **plans}
    facts, translated, journals, checks, plan_income = [], [], [], [], []
    for (scenario, period), result in all_results.items():
        meta = {"scenario": scenario, "period": period}
        aggregated = defaultdict(Decimal)
        for row in result.translated:
            e = row.entry
            translated.append(
                {
                    **meta,
                    "entity": e.entity,
                    "account": e.account,
                    "partner": e.partner,
                    "reference": e.reference,
                    "functional_currency": config["entities"][e.entity]["currency"],
                    "local_amount": e.amount,
                    "rate": row.rate,
                    "rate_basis": ACCOUNTS[e.account][1],
                    "amount": row.amount,
                }
            )
            aggregated[(e.entity, e.account, "translated")] += row.amount
        for journal in result.journals:
            journals.append({**meta, **journal})
            aggregated[(journal["entity"], journal["account"], "elimination")] += journal["amount"]
        for account, amount in result.balances.items():
            aggregated[("GROUP", account, "consolidated")] = amount
        # These synthetic accounts bridge the pre-close signed trial balance to position/OCI.
        if scenario == "Actual":
            for reserve in result.reserves:
                for account, amount in (
                    ("translation_reserve", -reserve["closing_cta"]),
                    ("translation_oci", -reserve["translation_oci"]),
                ):
                    aggregated[(reserve["entity"], account, "translated")] = amount
            for account in ("translation_reserve", "translation_oci"):
                aggregated[("GROUP", account, "consolidated")] = sum(
                    (
                        v
                        for (entity, a, stage), v in aggregated.items()
                        if entity != "GROUP" and a == account and stage == "translated"
                    ),
                    Decimal(0),
                )
        facts.extend(
            {
                **meta,
                "entity": entity,
                "account": account,
                "stage": stage,
                "currency": config["presentation_currency"],
                "amount": amount,
            }
            for (entity, account, stage), amount in sorted(aggregated.items())
        )
        checks.extend({**meta, **check} for check in result.checks)
        if scenario != "Actual":
            plan_income.extend(
                {**meta, **row}
                for row in result.income
                if row["line"] not in ("translation_oci", "total_comprehensive_income")
            )
    if annual is not None:
        checks.extend(
            {"scenario": "Actual", "period": config["period"], **c} for c in annual.checks
        )
        report = [
            f"# {annual.title}",
            "",
            "Consolidated annual financial statements. CAD; synthetic, unaudited, for review.",
            "",
        ]
        for name, table in annual.tables.items():
            fields = list(table[0])
            write_csv(output / name, table, fields)
            report += [
                f"## {name.removesuffix('.csv').replace('_', ' ')}",
                "",
                "| " + " | ".join(fields) + " |",
                "| " + " | ".join("---" for _ in fields) + " |",
            ]
            report += [
                "| "
                + " | ".join(
                    (f"{100 * r[f]:.1f}%" if f == "rate" else f"{r[f]:,.2f}")
                    if isinstance(r[f], Decimal)
                    else str(r[f])
                    for f in fields
                )
                + " |"
                for r in table
            ]
            report.append("")
        (output / "annual_notes.md").write_text(annual.notes, encoding="utf-8")
        (output / "annual_financial_statements.md").write_text(
            "\n".join(report) + "\n" + annual.notes, encoding="utf-8"
        )
    write_csv(
        output / "translated_ledger.csv",
        translated,
        [
            "scenario",
            "period",
            "entity",
            "account",
            "partner",
            "reference",
            "functional_currency",
            "local_amount",
            "rate",
            "rate_basis",
            "amount",
        ],
    )
    write_csv(
        output / "elimination_journal.csv",
        journals,
        ["scenario", "period", "entity", "account", "reference", "amount", "reason"],
    )
    write_csv(
        output / "reconciliation_checks.csv",
        checks,
        ["scenario", "period", "check", "status", "difference"],
    )
    checklist(
        output,
        [
            {
                "check": f"{c['scenario']}/{c['period']}/{c['check']}",
                "status": c["status"],
                "difference": c["difference"],
            }
            for c in checks
        ],
    )
    write_csv(
        output / "plan_income_statement.csv", plan_income, ["scenario", "period", "line", "amount"]
    )
    write_csv(
        output / "fact_financials.csv",
        facts,
        ["scenario", "period", "entity", "account", "stage", "currency", "amount"],
    )
    write_csv(
        output / "dim_entity.csv",
        [
            {"entity": e, "currency": d["currency"], "name": d.get("name", e)}
            for e, d in config["entities"].items()
        ]
        + [
            {
                "entity": "GROUP",
                "currency": config["presentation_currency"],
                "name": "Consolidated group",
            }
        ],
        ["entity", "currency", "name"],
    )
    write_csv(
        output / "dim_account.csv",
        [{"account": a, "kind": kind, "rate_basis": basis} for a, (kind, basis) in ACCOUNTS.items()]
        + [
            {"account": "translation_reserve", "kind": "equity", "rate_basis": "derived"},
            {"account": "translation_oci", "kind": "oci", "rate_basis": "derived"},
        ],
        ["account", "kind", "rate_basis"],
    )
    periods = sorted({period for _, period in all_results})
    write_csv(
        output / "dim_period.csv",
        [
            {
                "period": p,
                "grain": "month" if "-" in p and annual is None else "year",
                "year": p[:4],
            }
            for p in periods
        ],
        ["period", "grain", "year"],
    )
    write_csv(
        output / "dim_scenario.csv",
        [{"scenario": s} for s in sorted({s for s, _ in all_results})],
        ["scenario"],
    )
    return len(checks)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a reconciled IFRS-style close and planning pack"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Folder containing config.json, ledger.csv, plan.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New output folder (existing folders are protected)",
    )
    parser.add_argument(
        "--statutory",
        action="store_true",
        help="Also reconcile and produce comparative annual statements and notes",
    )
    args = parser.parse_args(argv)
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(
            "Output already exists. Choose a new folder so an old close cannot look current."
        )
    try:
        config = json.loads((args.input / "config.json").read_text(encoding="utf-8"))
        actual = consolidate(
            [Entry.from_row(r) for r in read_csv(args.input / "ledger.csv")], config
        )
        plans = roll_up_plan(read_csv(args.input / "plan.csv"), config)
        annual = None
        extra_sources = []
        if args.statutory:
            extra_sources = [
                "comparative_config.json",
                "comparative_ledger.csv",
                "opening_config.json",
                "opening_ledger.csv",
                "statutory.json",
                "cash_movements.csv",
                "equity_movements.csv",
            ]
            comparative_config = json.loads((args.input / "comparative_config.json").read_text())
            opening_config = json.loads((args.input / "opening_config.json").read_text())
            comparative = consolidate(
                [Entry.from_row(r) for r in read_csv(args.input / "comparative_ledger.csv")],
                comparative_config,
            )
            opening = consolidate(
                [Entry.from_row(r) for r in read_csv(args.input / "opening_ledger.csv")],
                opening_config,
            )
            annual = build_annual(
                actual,
                comparative,
                opening,
                config,
                comparative_config,
                opening_config,
                json.loads((args.input / "statutory.json").read_text()),
                read_csv(args.input / "cash_movements.csv"),
                read_csv(args.input / "equity_movements.csv"),
            )
    except (ValueError, OSError, KeyError, TypeError) as error:
        message = str(error)
        checklist(args.output, [{"check": message, "status": "FAIL", "difference": ""}])
        write_csv(
            args.output / "reconciliation_checks.csv",
            [{"check": message, "status": "FAIL", "difference": ""}],
            ["check", "status", "difference"],
        )
        (args.output / "status.json").write_text(
            json.dumps({"status": "BLOCKED", "error": message}, indent=2) + "\n"
        )
        print(
            f"Close blocked: {message}. See {args.output / 'month_end_checklist.csv'}",
            file=sys.stderr,
        )
        return 1
    count = export_pack(args.output, config, actual, plans, annual)
    status = {
        "status": "REVIEW_REQUIRED",
        "automated_checks_passed": count,
        "manual_checks_pending": len(MANUAL_CHECKS),
        "presentation_currency": config["presentation_currency"],
        "period": config["period"],
        "plan_groups": len(plans),
        "source_sha256": {
            name: hashlib.sha256((args.input / name).read_bytes()).hexdigest()
            for name in ["config.json", "ledger.csv", "plan.csv"] + extra_sources
        },
        "note": (
            "Comparative Canadian IFRS annual statement illustration; "
            "requires professional review and authorisation."
            if annual
            else "Workpapers only. Not a complete IFRS statutory reporting package."
        ),
    }
    (args.output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(
        f"{count} automated checks passed; {len(plans)} plan groups. "
        f"Manual review required: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
