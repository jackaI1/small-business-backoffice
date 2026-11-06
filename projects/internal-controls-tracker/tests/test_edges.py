import json
import sqlite3

import pytest
from conftest import exception, result, selection

from controls_tracker.cli import main
from controls_tracker.core import MAX_EVIDENCE_BYTES, Tracker


def test_main_runs_complete_demo_and_review_pack_in_process(tmp_path, capsys):
    db = str(tmp_path / "demo.sqlite")
    assert main(["--db", db, "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["test_results"] == 12
    assert main(["--db", db, "status", "--as-of", "2026-08-10"]) == 0
    assert json.loads(capsys.readouterr().out)["open_deficiencies"] == 1
    assert main(["--db", db, "list", "events"]) == 0
    assert len(json.loads(capsys.readouterr().out)) > 20
    assert main(["--db", db, "export", str(tmp_path / "review.xlsx")]) == 0
    capsys.readouterr()
    assert main(["--db", db, "demo"]) == 2
    assert "empty database" in capsys.readouterr().err


@pytest.mark.parametrize("size", [0, MAX_EVIDENCE_BYTES + 1])
def test_empty_and_large_evidence_rejected_without_partial_records(ready, tmp_path, size):
    file = tmp_path / "evidence.bin"
    with file.open("wb") as handle:
        handle.truncate(size)
    run = selection(ready)
    with pytest.raises(ValueError, match="10 MiB"):
        result(ready, str(file), run, ready.selected(run)[0]["item_id"])
    assert ready.rows("evidence") == ready.rows("results") == []


@pytest.mark.parametrize("value", ["2026-01-32", "20260101", "", "2026-13-01"])
def test_invalid_as_of_date_is_rejected(tracker, value):
    with pytest.raises(ValueError):
        tracker.status(value)


def test_missing_evidence_cannot_create_or_change_request(ready, tmp_path):
    from conftest import request

    request(ready)
    with pytest.raises(FileNotFoundError):
        ready.attach_evidence(request_id="AR-01", file=tmp_path / "missing", actor="Controller")
    assert ready.rows("requests")[0]["status"] == "open"
    assert ready.rows("request_evidence") == ready.rows("evidence") == []


def test_passing_retest_of_another_control_cannot_close(ready, control, population, evidence):
    _, _, _, did = exception(ready, evidence)
    control["id"] = "C-OTHER"
    ready.save_control(**control)
    population.update(id="POP-OTHER", control_id="C-OTHER")
    ready.add_population(**population)
    run = selection(ready, population_id="POP-OTHER")
    rid = result(ready, evidence, run, ready.selected(run)[0]["item_id"])
    with pytest.raises(ValueError, match="same control"):
        ready.close_deficiency(
            deficiency_id=did, retest_result_id=rid, reviewer="Reviewer", notes="Wrong control"
        )


def test_future_schema_is_not_changed(tmp_path):
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError, match="Unsupported"):
        Tracker(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999


def test_unknown_population_item_shape_rejected(tracker, process, control, population):
    tracker.save_process(**process)
    tracker.save_control(**control)
    population["items"][0]["unexpected"] = "value"
    with pytest.raises(ValueError, match="exactly"):
        tracker.add_population(**population)


def test_null_character_and_pass_with_remediation_are_rejected(ready, process, evidence):
    process["narrative"] = "Review\x00and sign"
    with pytest.raises(ValueError, match="null character"):
        ready.save_process(**process)
    run = selection(ready)
    with pytest.raises(ValueError, match="only apply"):
        result(ready, evidence, run, ready.selected(run)[0]["item_id"], owner="Controller")
    assert ready.rows("results") == []


def test_cli_record_example_commands_work_without_edits(tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    db = str(tmp_path / "example.sqlite")
    for kind in ("process", "control", "population", "request"):
        assert main(["--db", db, "record", kind, str(root / "examples" / f"{kind}.json")]) == 0
    assert (
        main(
            [
                "--db",
                db,
                "sample",
                "POP-BANK-H1",
                "--size",
                "6",
                "--seed",
                "walkthrough",
                "--rationale",
                "Inspect all six months for the walkthrough",
                "--tester",
                "Tester",
            ]
        )
        == 0
    )
    assert main(["--db", db, "record", "result", str(root / "examples/result.json")]) == 0
    assert (
        main(
            [
                "--db",
                db,
                "evidence",
                "AR-BANK-01",
                str(root / "examples/evidence/bank-review.txt"),
                "--actor",
                "Controller",
            ]
        )
        == 0
    )
    assert main(["--db", db, "extract", "1", str(tmp_path / "original.txt")]) == 0
    assert main(["--db", db, "init"]) == 0
