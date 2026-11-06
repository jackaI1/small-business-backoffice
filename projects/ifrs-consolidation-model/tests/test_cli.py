import csv
import json
import shutil
import subprocess
import sys
from decimal import Decimal as D

import pytest
from conftest import EXAMPLE

from ifrs_consolidation.cli import main, read_csv


def test_installed_command_and_complete_output_pack(tmp_path):
    output = tmp_path / "close"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ifrs_consolidation.cli",
            "--input",
            str(EXAMPLE),
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "26 automated checks passed; 6 plan groups" in completed.stdout
    status = json.loads((output / "status.json").read_text())
    assert status["manual_checks_pending"] == 5
    assert status["status"] == "REVIEW_REQUIRED"
    assert len(read_csv(output / "month_end_checklist.csv")) == 31
    assert len(read_csv(output / "elimination_journal.csv")) == 38
    assert len(read_csv(output / "plan_income_statement.csv")) == 42
    facts = read_csv(output / "fact_financials.csv")
    keys = [(r["scenario"], r["period"], r["entity"], r["account"], r["stage"]) for r in facts]
    assert len(keys) == len(set(keys))
    for dimension in ["entity", "account", "scenario", "period"]:
        valid = {r[dimension] for r in read_csv(output / f"dim_{dimension}.csv")}
        assert {r[dimension] for r in facts} <= valid
    # Fact bridge: entity translations plus journals equal the consolidated group.
    for group in (r for r in facts if r["stage"] == "consolidated"):
        details = [
            r
            for r in facts
            if r["scenario"] == group["scenario"]
            and r["period"] == group["period"]
            and r["account"] == group["account"]
            and r["stage"] in ("translated", "elimination")
        ]
        assert sum((D(r["amount"]) for r in details), D(0)) == D(group["amount"])


def test_failed_close_writes_diagnostics_without_statements(tmp_path):
    source, output = tmp_path / "input", tmp_path / "failed"
    shutil.copytree(EXAMPLE, source)
    rows = read_csv(source / "ledger.csv")
    rows[0]["amount"] = "0"
    with (source / "ledger.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    assert main(["--input", str(source), "--output", str(output)]) == 1
    assert json.loads((output / "status.json").read_text())["status"] == "BLOCKED"
    assert read_csv(output / "month_end_checklist.csv")[0]["status"] == "FAIL"
    assert not (output / "statement_of_financial_position.csv").exists()
    assert not (output / "fact_financials.csv").exists()


def test_bad_plan_blocks_actual_statements_too(tmp_path):
    source, output = tmp_path / "input", tmp_path / "failed"
    shutil.copytree(EXAMPLE, source)
    (source / "plan.csv").write_text("scenario,period,entity,account,amount\n")
    assert main(["--input", str(source), "--output", str(output)]) == 1
    assert not (output / "statement_of_financial_position.csv").exists()


def test_output_protection_preserves_existing_files(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "owner.txt").write_text("keep")
    with pytest.raises(SystemExit) as error:
        main(["--input", str(EXAMPLE), "--output", str(output)])
    assert error.value.code == 2
    assert (output / "owner.txt").read_text() == "keep"


def test_cli_malformed_input_is_readable_failure(tmp_path):
    source, output = tmp_path / "input", tmp_path / "failed"
    source.mkdir()
    (source / "config.json").write_text("{bad-json}")
    assert main(["--input", str(source), "--output", str(output)]) == 1
    assert json.loads((output / "status.json").read_text())["status"] == "BLOCKED"


@pytest.mark.parametrize("content", ["entity,entity\nCA,CA\n", "entity,account\nCA,cash,extra\n"])
def test_malformed_csv_is_never_silently_truncated(tmp_path, content):
    from ifrs_consolidation.model import CloseError

    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(CloseError):
        read_csv(path)
