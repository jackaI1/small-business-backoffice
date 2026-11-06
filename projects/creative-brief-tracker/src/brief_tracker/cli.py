"""Command line entry points for the sandbox and a configured Airtable base."""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .airtable import Airtable, AirtableError
from .reminders import build_report, write_drafts
from .sandbox import sandbox
from .setup import setup_tables
from .tracker import plan_brief, seed


def load(path):
    return json.loads(Path(path).read_text())


def live_api():
    return Airtable(os.environ.get("AIRTABLE_BASE_ID"), os.environ.get("AIRTABLE_TOKEN"))


def summarize(report, paths):
    return {
        "drafts": len(paths),
        "overdue_approvals": len(report["overdue_approvals"]),
        "overloaded": len(report["overloaded"]),
        "warnings": len(report["warnings"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan creative briefs and draft deadline emails")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run synthetic campaign through a local REST sandbox")
    demo.add_argument("--data", default="data/sports-campaign.json")
    demo.add_argument("--out", default="out/demo")
    demo.add_argument("--today", default="2026-11-16")
    commands.add_parser("setup", help="Create linked tables in an empty Airtable base")
    seed_cmd = commands.add_parser("seed", help="Upsert a campaign into configured Airtable tables")
    seed_cmd.add_argument("--data", default="data/sports-campaign.json")
    plan = commands.add_parser("plan", help="Replan an existing brief, keeping progress")
    plan.add_argument("--brief", required=True)
    plan.add_argument("--due", required=True)
    plan.add_argument("--steps", required=True, help="JSON list in forward work order")
    remind = commands.add_parser("remind", help="Read Airtable and save unsent .eml files")
    remind.add_argument("--today", default=date.today().isoformat())
    remind.add_argument("--days", type=int, default=7)
    remind.add_argument("--out", default=f"out/{date.today().isoformat()}")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            with (
                sandbox() as fixture,
                Airtable("appSandbox", "sandbox-only", endpoint=fixture["endpoint"]) as api,
            ):
                counts = seed(api, load(args.data))
                # A second seed exercises updates through the same real HTTP API.
                seed(api, load(args.data))
                report = build_report(api, args.today)
                paths = write_drafts(report, args.out)
                result = {
                    **counts,
                    **summarize(report, paths),
                    "api_requests": api.requests,
                    "sandbox": fixture,
                }
            print(json.dumps(result, indent=2))
        else:
            with live_api() as api:
                if args.command == "setup":
                    result = {"created_tables": setup_tables(api)}
                elif args.command == "seed":
                    result = seed(api, load(args.data))
                elif args.command == "plan":
                    rows = plan_brief(api, args.brief, args.due, load(args.steps))
                    result = {"scheduled_tasks": len(rows)}
                else:
                    report = build_report(api, args.today, args.days)
                    paths = write_drafts(report, args.out)
                    result = summarize(report, paths)
                print(json.dumps({**result, "api_requests": api.requests}, indent=2))
    except (ValueError, KeyError, TypeError, OSError, AirtableError) as exc:
        # Don't include record contents, request bodies or tokens in console errors.
        detail = str(exc) if isinstance(exc, (ValueError, AirtableError)) else type(exc).__name__
        print(f"Error: {detail}", file=sys.stderr)
        return 2
    return 0
