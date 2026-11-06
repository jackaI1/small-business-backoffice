"""Scheduled and local refresh entry point. No network or service account needed."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from staffing_forecast.data import load_regions, load_tickets, synthetic_tickets, validate_tickets
from staffing_forecast.excel import write_workbook
from staffing_forecast.exports import build_tables, write_tables
from staffing_forecast.forecast import Settings


def refresh(output: Path, regions: Path, input_path: Path | None = None, settings: Settings = Settings()):
    output = output.absolute()
    if output.is_symlink() or (
        output.exists()
        and (not output.is_dir() or (any(output.iterdir()) and not (output / "manifest.json").is_file()))
    ):
        raise ValueError("Output must be empty or a previous refresh directory containing manifest.json")
    for source in (regions, input_path):
        if source is not None and source.resolve().is_relative_to(output.resolve()):
            raise ValueError("Output cannot contain a source file; keep ticket data and region config outside it")
    config = load_regions(regions)
    tickets = load_tickets(input_path, config) if input_path else validate_tickets(synthetic_tickets(), config)
    tables, manifest = build_tables(tickets, config, settings)
    manifest["source"] = (
        "synthetic seed=42, 730 days, no personal records" if input_path is None else "user supplied daily CSV"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staffing-", dir=output.parent) as temporary:
        staging = Path(temporary) / "new"
        staging.mkdir()
        write_tables(tables, manifest, staging)
        write_workbook(tables, staging / "staffing_plan.xlsx")
        backup = Path(temporary) / "previous"
        if output.exists():
            output.rename(backup)
        try:
            staging.rename(output)
        except BaseException:
            if backup.exists():
                backup.rename(output)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Backtest and publish daily staffing forecast tables and Excel")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--synthetic", action="store_true", help="Use the reproducible 730-day demonstration")
    source.add_argument("--input", type=Path, help="CSV with date,region_id,tickets")
    parser.add_argument("--regions", type=Path, default=Path("config/regions.csv"))
    parser.add_argument("--output", type=Path, default=Path("outputs/latest"))
    parser.add_argument("--horizon", type=int, default=28)
    args = parser.parse_args()
    try:
        result = refresh(
            args.output, args.regions, args.input, Settings(horizon=args.horizon, fold_horizon=args.horizon)
        )
    except (ValueError, RuntimeError) as error:
        parser.exit(2, f"Refresh failed: {error}\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "selected_models": result["selected_models"],
                "evaluation_wape": result["evaluation_wape"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
