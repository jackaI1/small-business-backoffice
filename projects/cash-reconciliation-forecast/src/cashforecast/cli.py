import argparse
import os
import sys
from datetime import date
from decimal import InvalidOperation
from pathlib import Path

import psycopg

from . import db
from .forecast import forecast
from .inputs import load_csv
from .models import money
from .reconcile import reconcile
from .report import write_report


def run(database_url, input_dir, as_of, minimum, window, output):
    source = load_csv(input_dir)
    with db.connect(database_url) as conn:
        db.initialize(conn)
        db.store(conn, source)
        # The report uses rows read back from PostgreSQL, not the original CSV objects.
        data = db.retrieve(conn, source.id)
        reconciliation = reconcile(data.accounts, data.bank, data.ledger, as_of, window)
        cash = forecast(data, reconciliation, as_of, minimum)
        result = {
            "dataset_id": data.id,
            "as_of": as_of,
            "date_window": window,
            "reconciliation": reconciliation,
            "forecast": cash,
        }
        db.save_run(conn, data.id, as_of, window, minimum, result)
    output.mkdir(parents=True, exist_ok=True)
    write_report(output / "cash-report.xlsx", result)
    (output / "results.json").write_text(db.dumps(result) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reconcile bank/ledger CSVs and forecast 13 weeks."
    )
    parser.add_argument("--input", type=Path, required=True, help="directory containing five CSVs")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--minimum-cad", default="15000")
    parser.add_argument("--date-window", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.error("set DATABASE_URL to your PostgreSQL connection string")
    try:
        result = run(
            url, args.input, args.as_of, money(args.minimum_cad), args.date_window, args.output
        )
    except (ValueError, InvalidOperation, OSError, psycopg.Error) as exc:
        # Never echo connection strings or database errors that may contain credentials.
        if isinstance(exc, psycopg.Error):
            print(
                "Database operation failed. Check PostgreSQL connectivity and schema permissions.",
                file=sys.stderr,
            )
        else:
            print(f"Input/report error: {exc}", file=sys.stderr)
        return 1
    recon, cash = result["reconciliation"], result["forecast"]
    cleared = sum(p["variance"] == 0 for p in recon["pairs"])
    variances = len(recon["pairs"]) - cleared
    print(
        f"{cleared} cleared pairs; {variances} amount variances; "
        f"{len(recon['unmatched'])} unmatched records"
    )
    print(
        f"13 weeks; opening CAD {cash['opening_cad']:.2f}; "
        f"{cash['breach_weeks']} weeks below minimum"
    )
    print(f"Report: {args.output / 'cash-report.xlsx'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
