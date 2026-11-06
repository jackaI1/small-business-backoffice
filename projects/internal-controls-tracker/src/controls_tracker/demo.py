"""An end-to-end exercise for fictional Northstar Components, not real company data."""

from pathlib import Path
from tempfile import TemporaryDirectory


def build_demo(tracker):
    if any(tracker.rows(table) for table in ("documents", "populations", "requests")):
        raise ValueError("Demo needs an empty database. Choose a new --db file.")
    tracker.save_process(
        id="P-CLOSE",
        name="Northstar Components financial close",
        narrative="The preparer reconciles cash and checks the close calendar each month. "
        "The controller independently reviews reconciling items and signs the bank reconciliation. "
        "After journal review, the finance lead locks the ledger and keeps the lock log.",
        author="Controller",
        reason="Initial fictional walkthrough",
    )
    tracker.save_process(
        id="P-JE",
        name="Manual journal entries",
        narrative="The accountant prepares manual entries with supporting calculations. "
        "The controller checks account coding, amount and period before posting. "
        "The accountant retains the entry, support and independent approval in the close folder.",
        author="Accountant",
        reason="Initial fictional walkthrough",
    )
    controls = [
        dict(
            id="C-BANK",
            process_id="P-CLOSE",
            risk="Cash is misstated by unresolved differences",
            description="Controller reviews bank reconciliations and dates their approval.",
            owner="Controller",
            frequency="monthly",
            key=True,
            assertion="Existence and accuracy",
            test_procedure="Inspect bank statement agreement, reperform the reconciliation and "
            "inspect dated independent approval.",
            evidence_expected="Bank reconciliation, statement and dated reviewer approval",
        ),
        dict(
            id="C-JE",
            process_id="P-JE",
            risk="Unsupported manual entries distort expenses",
            description="Controller independently approves manual journals before posting.",
            owner="Controller",
            frequency="per-transaction",
            key=True,
            assertion="Occurrence, accuracy and cutoff",
            test_procedure="Agree the entry to support, inspect approver independence and "
            "compare approval time with posting time.",
            evidence_expected="Journal, calculation, approval and posting timestamp",
        ),
        dict(
            id="C-LOCK",
            process_id="P-CLOSE",
            risk="Entries change after close signoff",
            description="Finance lead locks the ledger after close review.",
            owner="Finance lead",
            frequency="monthly",
            key=True,
            assertion="Cutoff and completeness",
            test_procedure="Inspect lock log and confirm lock follows close signoff.",
            evidence_expected="Close signoff and ledger lock log",
        ),
        dict(
            id="C-CALENDAR",
            process_id="P-CLOSE",
            risk="Close tasks are missed",
            description="Accountant updates the monthly close checklist.",
            owner="Accountant",
            frequency="monthly",
            key=False,
            assertion="Completeness",
            test_procedure="Inspect checklist completion against the close calendar.",
            evidence_expected="Completed monthly checklist",
        ),
    ]
    for control in controls:
        tracker.save_control(**control, author="Controller", reason="Initial control matrix")
        count = 12 if control["id"] == "C-JE" else 6
        tracker.add_population(
            id="POP-" + control["id"],
            control_id=control["id"],
            period_start="2026-01-01",
            period_end="2026-06-30",
            source="Northstar fictional register, January to June 2026",
            reconciliation=f"{count} supplied records agreed to {count} register rows. "
            "Monthly controls also matched to the six-month close calendar.",
            items=[
                dict(
                    id=f"{control['id']}-{i:02}",
                    date=f"2026-{(i - 1) % 6 + 1:02}-28",
                    description=f"Fictional {control['id']} occurrence {i}",
                )
                for i in range(1, count + 1)
            ],
        )
    bank_deficiency = None
    with TemporaryDirectory(prefix="controls-demo-evidence-") as scratch:

        def file(name, content):
            path = Path(scratch) / name
            path.write_text(
                "NORTHSTAR COMPONENTS: FICTIONAL TRAINING EVIDENCE\n" + content + "\n",
                encoding="utf-8",
            )
            return path

        for control, size in zip(controls, (3, 4, 2, 2), strict=True):
            cid = control["id"]
            run = tracker.sample(
                population_id="POP-" + cid,
                size=size,
                seed="northstar-2026-h1",
                rationale=f"Inspect {size} occurrences for this walkthrough. Judgmental exercise "
                "size, not statistical assurance. Population reconciled to the fictional register.",
                tester="Internal reviewer",
            )
            for ordinal, item in enumerate(tracker.selected(run)):
                failed = ordinal == 0 and cid in {"C-BANK", "C-JE"}
                notes = (
                    (
                        "Reconciliation agrees to statement, but independent approval is undated."
                        if cid == "C-BANK"
                        else "Journal support agrees, but approval follows posting."
                    )
                    if failed
                    else "Inspected expected support and reviewer evidence. "
                    "Reperformed the documented comparison with no difference."
                )
                kwargs = (
                    dict(
                        owner="Controller",
                        due="2026-08-01",
                        remediation="Require and retain dated approval before completion.",
                    )
                    if failed
                    else {}
                )
                tracker.record_result(
                    run_id=run,
                    item_id=item["item_id"],
                    outcome="exception" if failed else "pass",
                    notes=notes,
                    tester="Internal reviewer",
                    evidence_file=file(
                        f"{item['item_id']}.txt",
                        f"Occurrence: {item['item_id']}\nProcedure: {control['test_procedure']}\n"
                        f"Observation: {notes}",
                    ),
                    **kwargs,
                )
                if failed and cid == "C-BANK":
                    bank_deficiency = tracker.rows("deficiencies")[-1]["id"]
        revised = {
            **controls[0],
            "description": "Controller reviews reconciliations, resolves "
            "differences and records approval date before close signoff.",
        }
        tracker.save_control(
            **revised, author="Controller", reason="Require approval date explicitly"
        )
        tracker.remediate(
            deficiency_id=bank_deficiency,
            owner="Controller",
            due="2026-08-06",
            action="Use the dated review checklist on the next close.",
            actor="Controller",
        )
        tracker.add_population(
            id="POP-BANK-RETEST",
            control_id="C-BANK",
            period_start="2026-08-01",
            period_end="2026-08-06",
            source="August remediation register",
            reconciliation="One post-remediation review matched to one register entry.",
            items=[
                dict(
                    id="BANK-RETEST-01",
                    date="2026-08-05",
                    description="New reconciliation after the dated-approval procedure changed",
                )
            ],
        )
        run = tracker.sample(
            population_id="POP-BANK-RETEST",
            size=1,
            seed="retest-2026",
            rationale="Inspect the first occurrence after remediation.",
            tester="Internal reviewer",
        )
        rid = tracker.record_result(
            run_id=run,
            item_id="BANK-RETEST-01",
            outcome="pass",
            notes="New reconciliation agrees and independent approval is dated before close.",
            tester="Internal reviewer",
            evidence_file=file(
                "bank-retest.txt",
                "Reviewed 2026-08-05 by Controller. Statement agrees. Difference: 0.00. "
                "Approval date precedes close signoff on 2026-08-06.",
            ),
        )
        tracker.close_deficiency(
            deficiency_id=bank_deficiency,
            retest_result_id=rid,
            reviewer="Finance lead",
            notes="Inspected the new dated approval and passing retest.",
        )
        for cid in ("C-BANK", "C-JE"):
            request_id = "AR-" + cid
            tracker.add_request(
                id=request_id,
                control_id=cid,
                description="Provide review support and dated independent approval.",
                owner="Controller",
                due="2026-07-25",
                requested_by="Internal reviewer",
            )
            fid = tracker.add_followup(
                request_id=request_id,
                description="Confirm approval timing.",
                owner="Controller",
                due="2026-07-30",
                actor="Internal reviewer",
            )
            tracker.attach_evidence(
                request_id=request_id,
                actor="Controller",
                file=file(
                    cid + "-request.txt",
                    "Review support received. "
                    + (
                        "Dated approval supplied with remediation retest."
                        if cid == "C-BANK"
                        else "Original approval follows posting. Corrective evidence still needed."
                    ),
                ),
            )
            if cid == "C-BANK":
                tracker.resolve_followup(
                    followup_id=fid,
                    actor="Internal reviewer",
                    notes="Approval timing checked against the new signoff.",
                )
                tracker.fulfill_request(
                    request_id=request_id,
                    actor="Internal reviewer",
                    notes="Evidence retained and timing follow-up resolved.",
                )
    return dict(
        company="Northstar Components (fictional)",
        processes=2,
        controls=4,
        populations=5,
        sample_runs=5,
        test_results=12,
        exceptions=2,
        open_deficiencies=1,
        closed_deficiencies=1,
        next="Run status --as-of 2026-08-10, then export review.xlsx --as-of 2026-08-10",
    )
