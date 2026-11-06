"""Offline, reproducible cohort runs and sensitivity exports."""

import argparse
import csv
from dataclasses import asdict, replace
import json
from pathlib import Path

from .engine import Assumptions, Cohort, ProjectionEngine


def load_cohorts(path):
    with Path(path).open(newline="") as source:
        result = []
        for row in csv.DictReader(source):
            result.append(Cohort(id=row["id"], product=row["product"], sex=row["sex"],
                                 issue_age=int(row["issue_age"]), count=float(row["count"]),
                                 benefit=float(row["benefit"]), annual_premium=float(row["annual_premium"]),
                                 term=int(row["term"]) if row["term"] else None))
    if not result or len({c.id for c in result}) != len(result):
        raise ValueError("cohorts must be nonempty with unique ids")
    return result


def scenarios(base):
    return {
        "Base": base,
        "Mortality -20%": replace(base, mortality_factor=base.mortality_factor * 0.8),
        "Mortality +20%": replace(base, mortality_factor=base.mortality_factor * 1.2),
        "Lapse -50%": replace(base, lapse_factor=base.lapse_factor * 0.5),
        "Lapse +50%": replace(base, lapse_factor=base.lapse_factor * 1.5),
        "Discount -1pp": replace(base, discount_rate=base.discount_rate - 0.01),
        "Discount +1pp": replace(base, discount_rate=base.discount_rate + 0.01),
    }


def run(cohorts, assumptions):
    with ProjectionEngine() as engine:
        return {name: [engine.project(c, a) for c in cohorts] for name, a in scenarios(assumptions).items()}


def main():
    parser = argparse.ArgumentParser(description="Project synthetic life insurance cohorts with lifelib.")
    parser.add_argument("--cohorts", type=Path, default=Path("examples/cohorts.csv"))
    parser.add_argument("--assumptions", type=Path, default=Path("examples/assumptions.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/projection.xlsx"))
    args = parser.parse_args()
    try:
        cohorts = load_cohorts(args.cohorts)
        assumptions = Assumptions(**json.loads(args.assumptions.read_text()))
        results = run(cohorts, assumptions)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    from .report import export_report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_report(results, args.output)
    records = [{"scenario": name, "cohort": asdict(p.cohort), "assumptions": asdict(p.assumptions),
                "summary": p.summary, "rows": p.rows} for name, projections in results.items() for p in projections]
    args.output.with_suffix(".json").write_text(json.dumps(records, indent=2) + "\n")
    with args.output.with_suffix(".csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["scenario", "cohort", *records[0]["rows"][0]])
        writer.writeheader()
        for record in records:
            writer.writerows({"scenario": record["scenario"], "cohort": record["cohort"]["id"], **row} for row in record["rows"])
    liability = sum(p.summary["pv_liabilities"] for p in results["Base"])
    print(f"{len(cohorts)} cohorts, {len(results)} scenarios, base PV liabilities ${liability:,.2f}")
    print(args.output)


if __name__ == "__main__":
    main()
