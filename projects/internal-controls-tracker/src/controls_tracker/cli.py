"""JSON inputs keep long narratives and test records easy to review and repeat."""

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

from .core import Tracker
from .db import TABLES

RECORDS = {
    "process": "save_process",
    "control": "save_control",
    "population": "add_population",
    "result": "record_result",
    "request": "add_request",
    "followup": "add_followup",
    "resolve-followup": "resolve_followup",
    "fulfill": "fulfill_request",
    "remediate": "remediate",
    "close": "close_deficiency",
}


def parser():
    parser = argparse.ArgumentParser(description="Track a fictional financial-close control review")
    parser.add_argument("--db", default="close.sqlite", help="SQLite file (default: close.sqlite)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create an empty database")
    commands.add_parser("demo", help="Load a full fictional example into an empty database")
    record = commands.add_parser("record", help="Record one JSON object; see docs/usage.md")
    record.add_argument("kind", choices=RECORDS)
    record.add_argument("file", type=Path)
    sample = commands.add_parser("sample", help="Save a repeatable sample without replacement")
    sample.add_argument("population_id")
    sample.add_argument("--size", type=int, required=True)
    sample.add_argument("--seed", required=True)
    sample.add_argument("--rationale", required=True)
    sample.add_argument("--tester", required=True)
    listing = commands.add_parser("list", help="Read records as JSON; evidence is metadata only")
    listing.add_argument("table", choices=TABLES)
    for command in ("status", "export"):
        cmd = commands.add_parser(command)
        if command == "export":
            cmd.add_argument("out", type=Path, help="New .xlsx path; existing files are protected")
        cmd.add_argument(
            "--as-of", default=date.today().isoformat(), help="YYYY-MM-DD deadline date"
        )
    evidence = commands.add_parser("evidence", help="Attach an evidence file to an open request")
    evidence.add_argument("request_id")
    evidence.add_argument("file", type=Path)
    evidence.add_argument("--actor", required=True)
    extract = commands.add_parser("extract", help="Recover stored evidence to a new file")
    extract.add_argument("id", type=int)
    extract.add_argument("out", type=Path)
    return parser


def execute(tracker, args):
    if args.command == "init":
        return {"database": str(tracker.path), "schema_version": 1}
    if args.command == "demo":
        from .demo import build_demo

        return build_demo(tracker)
    if args.command == "record":
        with args.file.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Input must be one JSON object")
        if "evidence_file" in payload:
            path = Path(payload["evidence_file"])
            payload["evidence_file"] = str(args.file.resolve().parent / path)
        result = getattr(tracker, RECORDS[args.kind])(**payload)
        return {"kind": args.kind, "id_or_version": result}
    if args.command == "sample":
        run = tracker.sample(
            population_id=args.population_id,
            size=args.size,
            seed=args.seed,
            rationale=args.rationale,
            tester=args.tester,
        )
        return {"run_id": run, "selected": tracker.selected(run)}
    if args.command == "list":
        return tracker.rows(args.table)
    if args.command == "status":
        return tracker.status(args.as_of)
    if args.command == "export":
        from .excel import export_workbook

        return {"workbook": export_workbook(tracker, args.out, args.as_of)}
    if args.command == "evidence":
        return {
            "evidence_id": tracker.attach_evidence(
                request_id=args.request_id, file=args.file, actor=args.actor
            )
        }
    if args.command == "extract":
        tracker.extract_evidence(args.id, args.out)
        return {"saved": str(args.out)}
    raise ValueError("Unknown command")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        with Tracker(args.db) as tracker:
            result = execute(tracker, args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, TypeError, OSError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
