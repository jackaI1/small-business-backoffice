import json
import os
import subprocess
import sys

from openpyxl import load_workbook


def cli(db, *args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "controls_tracker", "--db", str(db), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )


def test_demo_cli_persists_complete_workflow_and_exports(tmp_path):
    db = tmp_path / "demo.sqlite"
    completed = cli(db, "demo")
    assert completed.returncode == 0, completed.stderr
    info = json.loads(completed.stdout)
    assert info["controls"] == 4
    status = json.loads(cli(db, "status", "--as-of", "2026-08-10").stdout)
    assert status["exception_results"] == 2
    assert status["open_deficiencies"] == 1
    assert status["overdue_deficiencies"] == 1
    assert status["open_requests"] == 1
    assert status["open_followups"] == 1
    out = tmp_path / "review.xlsx"
    completed = cli(db, "export", str(out), "--as-of", "2026-08-10")
    assert completed.returncode == 0, completed.stderr
    wb = load_workbook(out)
    assert wb["Matrix"].max_row == 5
    assert wb["Deficiencies"].max_row == 3
    wb.close()
    assert cli(db, "demo").returncode == 2


def test_cli_can_record_and_test_its_own_data(tmp_path, process, control, population, evidence):
    db = tmp_path / "custom.sqlite"
    for kind, data in (("process", process), ("control", control), ("population", population)):
        source = tmp_path / f"{kind}.json"
        source.write_text(json.dumps(data))
        completed = cli(db, "record", kind, str(source))
        assert completed.returncode == 0, completed.stderr
    sampled = cli(
        db,
        "sample",
        "POP-2026",
        "--size",
        "2",
        "--seed",
        "custom-seed",
        "--rationale",
        "Two months for the walkthrough",
        "--tester",
        "Tester",
    )
    assert sampled.returncode == 0, sampled.stderr
    run = json.loads(sampled.stdout)
    source = tmp_path / "result.json"
    source.write_text(
        json.dumps(
            dict(
                run_id=run["run_id"],
                item_id=run["selected"][0]["item_id"],
                outcome="exception",
                notes="No dated signoff",
                tester="Tester",
                evidence_file=os.path.relpath(evidence, tmp_path),
                owner="Controller",
                due="2026-08-01",
                remediation="Require a dated signoff",
            )
        )
    )
    # Evidence paths in JSON resolve relative to the input file, not the working directory.
    completed = cli(db, "record", "result", str(source), cwd=tmp_path.parent)
    assert completed.returncode == 0, completed.stderr
    assert len(json.loads(cli(db, "list", "deficiencies").stdout)) == 1
    dest = tmp_path / "original.txt"
    assert cli(db, "extract", "1", str(dest)).returncode == 0
    assert dest.read_text().startswith("Fictional reviewer")


def test_cli_errors_are_actionable_and_do_not_dump_tracebacks(tmp_path):
    db = tmp_path / "empty.sqlite"
    malformed = tmp_path / "bad.json"
    for value in ("{", "[]", '{"id":"P"}', '{"unexpected":true}'):
        malformed.write_text(value)
        completed = cli(db, "record", "process", str(malformed))
        assert completed.returncode == 2
        assert "error:" in completed.stderr
        assert "Traceback" not in completed.stderr
    completed = cli(
        db,
        "sample",
        "missing",
        "--size",
        "2",
        "--seed",
        "x",
        "--tester",
        "Tester",
        "--rationale",
        "Practice",
    )
    assert completed.returncode == 2
    assert "No populations record" in completed.stderr


def test_cli_evidence_and_init_commands(ready, evidence, tmp_path):
    from conftest import request

    request(ready)
    completed = cli(ready.path, "evidence", "AR-01", evidence, "--actor", "Controller")
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["evidence_id"] == 1
    assert cli(tmp_path / "new.sqlite", "init").returncode == 0
