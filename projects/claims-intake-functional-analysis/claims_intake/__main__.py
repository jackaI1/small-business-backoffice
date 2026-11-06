"""Run with python3 -m claims_intake --help."""
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .core import InputError, connect, detail, intake, parse_date, queue, review, seed_policies, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fictional home claim intake. Sample data only.")
    parser.add_argument("--db", required=True, help="SQLite file, created if needed")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="Load an immutable policy snapshot")
    seed.add_argument("file", type=Path)
    submit = commands.add_parser("submit", help="Validate and route a JSON array of claims")
    submit.add_argument("file", type=Path)
    submit.add_argument("--as-of", required=True, type=parse_date)
    commands.add_parser("queue", help="Show flagged claims still awaiting human action")
    commands.add_parser("summary", help="Show routing and review counts")
    show = commands.add_parser("show", help="Inspect original claim, history and related record IDs")
    show.add_argument("claim_id", type=int)
    action = commands.add_parser("review", help="Record a human triage action")
    action.add_argument("claim_id", type=int)
    action.add_argument("--action", required=True)
    action.add_argument("--reviewer", required=True, help="Synthetic reviewer ID for this demo")
    args = parser.parse_args(argv)
    try:
        with closing(connect(args.db)) as db:
            if args.command == "seed":
                policies = json.loads(args.file.read_text())
                if not isinstance(policies, list):
                    raise InputError("Policy snapshot must be an array")
                seed_policies(db, policies)
                output = {"policies": len(policies)}
            elif args.command == "submit":
                results = intake(db, json.loads(args.file.read_text()), args.as_of)
                output = [{"id": r["id"], "claim_ref": r["claim_ref"], "status": r["status"],
                           "reasons": json.loads(r["reasons"]), "replayed": r["replayed"]} for r in results]
            elif args.command == "queue":
                output = queue(db)
                for r in output:
                    r["reasons"] = json.loads(r["reasons"])
            elif args.command == "review":
                review(db, args.claim_id, args.action, args.reviewer)
                output = {"id": args.claim_id, "action": args.action}
            elif args.command == "show":
                output = detail(db, args.claim_id)
            else:
                output = summary(db)
        print(json.dumps(output, indent=2))
    except (InputError, ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        parser.exit(2, "Input/storage error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
