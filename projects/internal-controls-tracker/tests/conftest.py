import pytest

from controls_tracker.core import Tracker


@pytest.fixture
def tracker(tmp_path):
    with Tracker(tmp_path / "close.sqlite") as tracker:
        yield tracker


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / "review.txt"
    path.write_text("Fictional reviewer approval of account reconciliation.\n")
    return str(path)


@pytest.fixture
def process():
    return dict(
        id="P-CLOSE",
        name="Financial close",
        narrative="Prepare, review, then lock.",
        author="Controller",
        reason="Initial walkthrough",
    )


@pytest.fixture
def control():
    return dict(
        id="C-REC",
        process_id="P-CLOSE",
        risk="Cash balance is misstated",
        description="Controller reviews signed bank reconciliations.",
        owner="Controller",
        frequency="monthly",
        key=True,
        assertion="Existence and accuracy",
        test_procedure="Inspect reviewer approval and reperform the reconciliation.",
        evidence_expected="Reconciliation and dated independent approval",
        author="Controller",
        reason="Initial matrix",
    )


@pytest.fixture
def population():
    return dict(
        id="POP-2026",
        control_id="C-REC",
        period_start="2026-01-01",
        period_end="2026-06-30",
        source="Fictional close register",
        reconciliation="Six monthly occurrences matched to six close-calendar entries.",
        items=[
            dict(
                id=f"REC-{month:02}",
                date=f"2026-{month:02}-28",
                description=f"Month {month} bank reconciliation",
            )
            for month in range(1, 7)
        ],
    )


@pytest.fixture
def ready(tracker, process, control, population):
    tracker.save_process(**process)
    tracker.save_control(**control)
    tracker.add_population(**population)
    return tracker


def selection(tracker, population_id="POP-2026", size=3, seed="close-2026"):
    return tracker.sample(
        population_id=population_id,
        size=size,
        seed=seed,
        rationale="Inspect three of six months for this exercise.",
        tester="Close tester",
    )


def result(tracker, evidence, run, item, outcome="pass", **kwargs):
    return tracker.record_result(
        run_id=run,
        item_id=item,
        outcome=outcome,
        notes="Inspected supporting reconciliation and approval.",
        tester="Close tester",
        evidence_file=evidence,
        **kwargs,
    )


def exception(tracker, evidence):
    run = selection(tracker)
    item = tracker.selected(run)[0]["item_id"]
    rid = result(
        tracker,
        evidence,
        run,
        item,
        "exception",
        owner="Controller",
        due="2026-08-01",
        remediation="Add dated reviewer signoff.",
    )
    return run, item, rid, tracker.rows("deficiencies")[0]["id"]


def request(tracker):
    return tracker.add_request(
        id="AR-01",
        control_id="C-REC",
        description="June approval",
        owner="Controller",
        due="2026-07-10",
        requested_by="Tester",
    )
