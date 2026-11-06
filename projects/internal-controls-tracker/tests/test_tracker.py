import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from conftest import exception, request, result, selection


def test_document_versions_preserve_previous_wording(ready, control, process):
    control["description"] = "Review and date the reconciliation."
    control["reason"] = "Clarify approval timing"
    assert ready.save_control(**control) == 2
    process["narrative"] = "Prepare, review, retain evidence, then lock."
    assert ready.save_process(**process) == 2
    docs = ready.rows("documents")
    assert len(docs) == 4
    assert "signed bank" in json.loads(docs[1]["payload"])["description"]
    assert ready.document("control", "C-REC")["version"] == 2


def test_population_pins_documents_and_hash(ready, control):
    control["description"] = "New control wording"
    ready.save_control(**control)
    pop = ready.rows("populations")[0]
    assert pop["control_version"] == 1
    assert pop["process_version"] == 1
    assert hashlib.sha256(pop["payload"].encode()).hexdigest() == pop["sha256"]


def test_sampling_repeatable_across_order_and_new_database(
    ready, population, tmp_path, process, control
):
    from controls_tracker.core import Tracker

    run = selection(ready)
    first = [r["item_id"] for r in ready.selected(run)]
    with Tracker(tmp_path / "other.sqlite") as other:
        other.save_process(**process)
        other.save_control(**control)
        population["items"].reverse()
        other.add_population(**population)
        run2 = selection(other)
        assert first == [r["item_id"] for r in other.selected(run2)]
    assert len(first) == len(set(first)) == 3
    assert ready.rows("runs")[0]["algorithm"] == "sha256-rank-v1"
    assert len(ready.selected(selection(ready, size=6))) == 6


def test_sampling_matches_independent_ranking(ready, population):
    ranked = sorted(
        population["items"],
        key=lambda item: (
            hashlib.sha256(
                json.dumps(
                    ["close-2026", item["id"]], ensure_ascii=False, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            item["id"],
        ),
    )
    assert [r["item_id"] for r in ready.selected(selection(ready))] == [
        item["id"] for item in ranked[:3]
    ]


@pytest.mark.parametrize("size", [0, -1, 7, True, 1.5])
def test_invalid_sample_size_is_rejected(ready, size):
    with pytest.raises(ValueError):
        selection(ready, size=size)
    assert ready.rows("runs") == []


@pytest.mark.parametrize(
    "change",
    [
        {"items": []},
        {"period_start": "2026-07-01"},
        {"period_end": "2026-02-30"},
        {"source": " "},
        {
            "items": [
                {"id": "DUP", "date": "2026-01-01", "description": "A"},
                {"id": "DUP", "date": "2026-01-02", "description": "B"},
            ]
        },
        {"items": [{"id": "OUT", "date": "2025-12-31", "description": "Outside"}]},
    ],
)
def test_invalid_population_rolls_back(tracker, process, control, population, change):
    tracker.save_process(**process)
    tracker.save_control(**control)
    population.update(change)
    with pytest.raises(ValueError):
        tracker.add_population(**population)
    assert tracker.rows("populations") == []


def test_population_cannot_be_replaced(ready, population):
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        ready.add_population(**population)
    assert len(ready.rows("populations")) == 1


@pytest.mark.parametrize(
    "field,value",
    [("key", "false"), ("frequency", "whenever"), ("risk", ""), ("process_id", "MISSING")],
)
def test_control_validation(tracker, process, control, field, value):
    tracker.save_process(**process)
    control[field] = value
    with pytest.raises(ValueError):
        tracker.save_control(**control)
    assert len(tracker.rows("documents")) == 1


def test_control_cannot_move_to_another_process(ready, process, control):
    process["id"] = "P-OTHER"
    ready.save_process(**process)
    control["process_id"] = "P-OTHER"
    with pytest.raises(ValueError):
        ready.save_control(**control)


def test_exception_is_atomic_and_original_result_survives(ready, evidence):
    run, item, rid, did = exception(ready, evidence)
    deficiency = ready.rows("deficiencies")[0]
    assert deficiency["result_id"] == rid
    assert deficiency["owner"] == "Controller"
    assert deficiency["status"] == "open"
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        result(ready, evidence, run, item)
    assert len(ready.rows("results")) == 1
    assert len(ready.rows("evidence")) == 1
    ready.remediate(
        deficiency_id=did,
        owner="Finance lead",
        due="2026-08-15",
        action="Retain dated approvals",
        actor="Controller",
    )
    assert ready.rows("deficiencies")[0]["owner"] == "Finance lead"
    assert ready.rows("results")[0]["outcome"] == "exception"
    assert any(e["action"] == "remediation_updated" for e in ready.rows("events"))


def test_failed_result_validation_leaves_no_evidence(ready, evidence):
    run = selection(ready)
    item = ready.selected(run)[0]["item_id"]
    with pytest.raises(ValueError):
        result(ready, evidence, run, item, "exception")
    with pytest.raises(ValueError):
        result(ready, evidence, run, "NOT-SELECTED")
    with pytest.raises(ValueError):
        result(ready, evidence, run, item, "unknown")
    with pytest.raises(FileNotFoundError):
        result(ready, evidence + ".missing", run, item)
    assert ready.rows("results") == ready.rows("evidence") == []


def test_evidence_retains_original_bytes_after_source_removed(ready, evidence, tmp_path):
    run = selection(ready)
    result(ready, evidence, run, ready.selected(run)[0]["item_id"])
    original = Path(evidence).read_bytes()
    Path(evidence).unlink()
    row = ready.rows("evidence")[0]
    assert "content" not in row
    assert row["sha256"] == hashlib.sha256(original).hexdigest()
    target = tmp_path / "recovered.txt"
    ready.extract_evidence(row["id"], target)
    assert target.read_bytes() == original
    with pytest.raises(FileExistsError):
        ready.extract_evidence(row["id"], target)


def test_closure_requires_later_passing_retest_of_same_control(ready, evidence):
    run, item, rid, did = exception(ready, evidence)
    # A pass from the original sample run does not establish remediation.
    another = ready.selected(run)[1]["item_id"]
    old_pass = result(ready, evidence, run, another)
    args = dict(deficiency_id=did, reviewer="Controller", notes="Inspected new approval")
    with pytest.raises(ValueError):
        ready.close_deficiency(retest_result_id=old_pass, **args)
    with pytest.raises(ValueError):
        ready.close_deficiency(retest_result_id=rid, **args)
    new_run = selection(ready)
    retest = result(ready, evidence, new_run, item)
    ready.close_deficiency(retest_result_id=retest, **args)
    assert ready.rows("deficiencies")[0]["status"] == "closed"
    assert ready.rows("results")[0]["outcome"] == "exception"
    with pytest.raises(ValueError):
        ready.close_deficiency(retest_result_id=retest, **args)


def test_retest_created_before_exception_cannot_close(ready, evidence):
    earlier = selection(ready)
    _, _, _, did = exception(ready, evidence)
    passing = result(ready, evidence, earlier, ready.selected(earlier)[0]["item_id"])
    with pytest.raises(ValueError):
        ready.close_deficiency(
            deficiency_id=did,
            retest_result_id=passing,
            reviewer="Controller",
            notes="Not a new run",
        )


def test_request_needs_evidence_and_resolved_followups(ready, evidence):
    request(ready)
    args = dict(request_id="AR-01", actor="Tester", notes="Evidence reviewed")
    with pytest.raises(ValueError):
        ready.fulfill_request(**args)
    fid = ready.add_followup(
        request_id="AR-01",
        description="Need dated approval",
        owner="Controller",
        due="2026-07-15",
        actor="Tester",
    )
    ready.attach_evidence(request_id="AR-01", file=evidence, actor="Controller")
    assert ready.rows("requests")[0]["status"] == "received"
    with pytest.raises(ValueError):
        ready.fulfill_request(**args)
    ready.resolve_followup(followup_id=fid, actor="Tester", notes="Dated approval received")
    ready.fulfill_request(**args)
    assert ready.rows("requests")[0]["status"] == "fulfilled"
    with pytest.raises(ValueError):
        ready.add_followup(
            request_id="AR-01",
            description="Another",
            owner="Controller",
            due="2026-07-20",
            actor="Tester",
        )


def test_status_distinguishes_pending_and_overdue(ready, evidence):
    request(ready)
    ready.add_followup(
        request_id="AR-01",
        description="Approval date",
        owner="Controller",
        due="2026-07-15",
        actor="Tester",
    )
    exception(ready, evidence)
    summary = ready.status("2026-07-16")
    assert summary["open_requests"] == summary["overdue_requests"] == 1
    assert summary["open_followups"] == summary["overdue_followups"] == 1
    assert summary["open_deficiencies"] == 1
    assert summary["overdue_deficiencies"] == 0
    assert summary["untested_samples"] == 2
    assert ready.status("2026-07-10")["overdue_requests"] == 0


@pytest.mark.parametrize(
    "table", ["documents", "populations", "runs", "selections", "results", "evidence", "events"]
)
def test_audit_records_cannot_be_updated_or_deleted(ready, evidence, table):
    exception(ready, evidence)
    for command in (f"DELETE FROM {table}", f"UPDATE {table} SET rowid=rowid"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ready.db.execute(command)
        ready.db.rollback()


def test_unknown_table_is_rejected(ready):
    with pytest.raises(ValueError):
        ready.rows("documents; DROP TABLE documents")


def test_records_persist_on_reopen(ready):
    from controls_tracker.core import Tracker

    run = selection(ready)
    with Tracker(ready.path) as reopened:
        assert reopened.selected(run) == ready.selected(run)
        assert reopened.document("control", "C-REC")["version"] == 1
