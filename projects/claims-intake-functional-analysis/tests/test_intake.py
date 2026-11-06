import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from claims_intake.core import InputError, connect, intake, queue, review, seed_policies, summary
from claims_intake.options import compare
from claims_intake.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 1, 15)


def requirement(*ids):
    def decorate(method):
        method.requirements = ids
        return method
    return decorate


def claim(**changes):
    result = dict(claim_ref="DEMO-C01", policy_id="DEMO-P01", property_id="DEMO-H01",
                  loss_date="2026-01-10", reported_date="2026-01-11", loss_type="water",
                  amount_cents=125000, description="Fictional pipe leak", evidence=["photos"])
    result.update(changes)
    return result


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.addCleanup(self.db.close)
        seed_policies(self.db, json.loads((ROOT / "samples/policies.json").read_text()))

    def submit(self, **changes):
        row = intake(self.db, [claim(**changes)], AS_OF)[0]
        return row, json.loads(row["reasons"])

    @requirement("R01", "R09")
    def test_complete_claim_routes_to_adjuster(self):
        row, flags = self.submit()
        self.assertEqual(row["status"], "READY_FOR_ADJUSTER")
        self.assertEqual(flags, [])
        self.assertEqual(row["evaluated_on"], "2026-01-15")

    @requirement("R02", "R09")
    def test_every_required_business_field_can_be_missing(self):
        for field in ("policy_id", "property_id", "loss_date", "reported_date", "loss_type", "amount_cents", "description"):
            for value in (None, "", "  "):
                with self.subTest(field=field, value=value):
                    row, flags = self.submit(**{field: value})
                    self.assertIn("MISSING:" + field, flags)
                    self.assertEqual(row["status"], "NEEDS_REVIEW")

    @requirement("R02", "R05", "R06")
    def test_bad_field_types_are_reviewable(self):
        for field in ("policy_id", "property_id", "description", "loss_type", "loss_date", "reported_date", "amount_cents", "evidence"):
            for value in ([], {}, True):
                with self.subTest(field=field, value=value):
                    row, flags = self.submit(**{field: value})
                    # An empty evidence list is valid structure but requires photos.
                    self.assertTrue(flags)
                    self.assertEqual(row["status"], "NEEDS_REVIEW")

    @requirement("R03")
    def test_policy_and_property_conflicts(self):
        for changes, flag in [({"policy_id": "UNKNOWN"}, "UNKNOWN_POLICY"),
                              ({"property_id": "DEMO-H99"}, "PROPERTY_MISMATCH"),
                              ({"loss_date": "2024-12-31"}, "LOSS_OUTSIDE_POLICY")]:
            with self.subTest(changes=changes):
                self.assertIn(flag, self.submit(**changes)[1])

    @requirement("R03", "R04")
    def test_policy_boundaries_are_inclusive(self):
        for boundary in ("2025-01-01", "2026-12-31"):
            with self.subTest(boundary=boundary):
                row = intake(self.db, [claim(claim_ref=boundary, loss_date=boundary, reported_date=boundary)],
                             date(2026, 12, 31))[0]
                self.assertEqual(row["status"], "READY_FOR_ADJUSTER")

    @requirement("R04")
    def test_dates_and_chronology(self):
        cases = [({"loss_date": "2026-02-30"}, "INVALID:loss_date"),
                 ({"reported_date": "2026-1-11"}, "INVALID:reported_date"),
                 ({"reported_date": "2026-01-09"}, "LOSS_AFTER_REPORT"),
                 ({"reported_date": "2026-01-16"}, "FUTURE_DATE"),
                 ({"loss_date": "2026-01-16"}, "FUTURE_DATE")]
        for changes, flag in cases:
            with self.subTest(changes=changes):
                self.assertIn(flag, self.submit(**changes)[1])

    @requirement("R05")
    def test_amount_boundaries_and_loss_types(self):
        for amount in (-1, 0, True, 1.2, "100", 1_000_000_001):
            with self.subTest(amount=amount):
                self.assertIn("INVALID:amount_cents", self.submit(amount_cents=amount)[1])
        self.assertNotIn("HIGH_VALUE", self.submit(amount_cents=2_499_999)[1])
        for amount in (2_500_000, 1_000_000_000):
            self.assertIn("HIGH_VALUE", self.submit(amount_cents=amount)[1])
        self.assertIn("INVALID:loss_type", self.submit(loss_type="other")[1])

    @requirement("R06")
    def test_each_loss_type_evidence(self):
        for kind, required in (("water", ["photos"]), ("fire", ["photos"]),
                               ("wind", ["photos"]), ("theft", ["inventory", "police_reference"])):
            with self.subTest(kind=kind):
                self.assertTrue(all("EVIDENCE_REQUIRED:" + e in self.submit(loss_type=kind, evidence=[])[1]
                                    for e in required))
                self.assertFalse(any(f.startswith("EVIDENCE_REQUIRED:") for f in
                                     self.submit(loss_type=kind, evidence=required)[1]))
        self.assertIn("INVALID:evidence", self.submit(evidence=[3])[1])

    @requirement("R07", "R10")
    def test_identical_retry_is_idempotent_even_on_later_day(self):
        first, _ = self.submit()
        again = intake(self.db, [claim()], date(2026, 2, 1))[0]
        self.assertTrue(again["replayed"])
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(again["evaluated_on"], "2026-01-15")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    @requirement("R08", "R09")
    def test_conflicting_reference_preserves_both_versions(self):
        first, _ = self.submit()
        second, flags = self.submit(description="Different fictional account")
        self.assertIn("REFERENCE_CONFLICT", flags)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(summary(self.db)["total"], 2)

    @requirement("R08")
    def test_duplicate_signal_and_distinct_claims(self):
        self.submit()
        self.assertIn("POSSIBLE_DUPLICATE", self.submit(claim_ref="DEMO-C02")[1])
        self.assertNotIn("POSSIBLE_DUPLICATE", self.submit(claim_ref="DEMO-C03", loss_date="2026-01-09")[1])
        self.assertNotIn("POSSIBLE_DUPLICATE", self.submit(claim_ref="DEMO-C04", policy_id="DEMO-P02", property_id="DEMO-H02")[1])

    @requirement("R10", "R11", "R12")
    def test_review_is_audited_and_removes_only_pending_item(self):
        row, flags = self.submit(description="")
        self.assertEqual(len(queue(self.db)), 1)
        review(self.db, row["id"], "request_information", "DEMO-REVIEWER")
        self.assertEqual(queue(self.db), [])
        self.assertEqual(summary(self.db), {"total": 1, "ready_for_adjuster": 0, "flagged": 1,
                                            "awaiting_review": 0, "reviewed": 1})
        events = self.db.execute("SELECT * FROM events ORDER BY id").fetchall()
        self.assertEqual([e["kind"] for e in events], ["INTAKE", "REVIEW"])
        self.assertEqual(events[1]["actor"], "DEMO-REVIEWER")
        self.assertTrue(events[1]["created_at"].endswith("Z"))
        self.assertEqual(json.loads(events[0]["details"])["reasons"], flags)
        self.assertEqual(self.db.execute("SELECT status FROM claims").fetchone()[0], "NEEDS_REVIEW")
        with self.assertRaises(InputError):
            review(self.db, row["id"], "refer_adjuster", "DEMO-REVIEWER")

    @requirement("R11")
    def test_review_guards_and_each_action(self):
        ready, _ = self.submit()
        for cid, action, actor in ((999, "refer_adjuster", "R"), (ready["id"], "refer_adjuster", "R"),
                                    (ready["id"], "approve_payment", "R"), (ready["id"], "refer_adjuster", " ")):
            with self.subTest(cid=cid, action=action, actor=actor), self.assertRaises(InputError):
                review(self.db, cid, action, actor)
        bad, _ = self.submit(claim_ref="DEMO-BAD", description="", loss_date="2026-01-08")
        with self.assertRaises(InputError):
            review(self.db, bad["id"], "close_duplicate", "R")
        review(self.db, bad["id"], "refer_adjuster", "R")
        dup, _ = self.submit(claim_ref="DEMO-DUP")
        review(self.db, dup["id"], "close_duplicate", "R")
        self.assertEqual(summary(self.db)["reviewed"], 2)

    @requirement("R01", "R13")
    def test_malformed_batch_is_rejected_before_any_write(self):
        for bad in ([], {}, None, [claim(), None], [claim(), {"claim_ref": "x", "unexpected": 1}],
                    [claim(), {}], [claim(claim_ref=" ")], [claim(amount_cents=float("nan"))]):
            with self.subTest(bad=bad), self.assertRaises(InputError):
                intake(self.db, bad, AS_OF)
            self.assertEqual(summary(self.db)["total"], 0)

    @requirement("R13")
    def test_storage_failure_rolls_back_claims_and_audit(self):
        self.db.execute("""CREATE TRIGGER fail_second BEFORE INSERT ON claims
            WHEN NEW.claim_ref='FAIL' BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            intake(self.db, [claim(), claim(claim_ref="FAIL")], AS_OF)
        self.assertEqual(summary(self.db)["total"], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    @requirement("R03", "R13")
    def test_policy_snapshot_is_immutable_and_atomic(self):
        policies = json.loads((ROOT / "samples/policies.json").read_text())
        seed_policies(self.db, policies)
        new = dict(policies[0], policy_id="NEW")
        changed = dict(policies[0], property_id="WRONG")
        with self.assertRaises(InputError):
            seed_policies(self.db, [new, changed])
        self.assertIsNone(self.db.execute("SELECT * FROM policies WHERE policy_id='NEW'").fetchone())

    @requirement("R01", "R10", "R12")
    def test_sample_batch_and_disk_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "intake.sqlite"
            with contextlib.closing(connect(path)) as db:
                seed_policies(db, json.loads((ROOT / "samples/policies.json").read_text()))
                rows = intake(db, json.loads((ROOT / "samples/claims.json").read_text()), AS_OF)
                self.assertEqual(len(rows), 12)
            with contextlib.closing(connect(path)) as db:
                self.assertEqual(summary(db), {"total": 12, "ready_for_adjuster": 2,
                                              "flagged": 10, "awaiting_review": 10, "reviewed": 0})
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 12)

    @requirement("R07", "R08", "R13")
    def test_two_connections_share_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shared.sqlite"
            with contextlib.closing(connect(path)) as a, contextlib.closing(connect(path)) as b:
                seed_policies(a, json.loads((ROOT / "samples/policies.json").read_text()))
                first = intake(a, [claim()], AS_OF)[0]
                again = intake(b, [claim()], AS_OF)[0]
                self.assertEqual(first["id"], again["id"])
                a.execute("BEGIN IMMEDIATE")
                b.execute("PRAGMA busy_timeout=1")
                with self.assertRaises(sqlite3.OperationalError):
                    intake(b, [claim(claim_ref="OTHER")], AS_OF)
                a.rollback()
                self.assertEqual(summary(b)["total"], 1)

    @requirement("R01", "R10", "R11", "R12")
    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            common = ["--db", str(Path(folder) / "cli.sqlite")]
            def run(*args):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    main(common + list(args))
                return json.loads(output.getvalue())
            self.assertEqual(run("seed", str(ROOT / "samples/policies.json")), {"policies": 2})
            self.assertEqual(len(run("submit", str(ROOT / "samples/claims.json"), "--as-of", "2026-01-15")), 12)
            pending = run("queue")
            original = run("show", "1")
            self.assertEqual(original["payload"]["description"], "Fictional pipe leak")
            self.assertIn(12, original["related_ids"])
            self.assertEqual(original["events"][0]["kind"], "INTAKE")
            self.assertIsNone(original["review"])
            run("review", str(pending[0]["id"]), "--action", "request_information", "--reviewer", "DEMO-R01")
            self.assertEqual(run("summary")["awaiting_review"], 9)
            reviewed = run("show", str(pending[0]["id"]))
            self.assertEqual(reviewed["review"]["action"], "request_information")
            self.assertEqual([e["kind"] for e in reviewed["events"]], ["INTAKE", "REVIEW"])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                run("show", "999")
            self.assertEqual(error.exception.code, 2)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                run("submit", str(ROOT / "samples/missing.json"), "--as-of", "2026-01-15")
            self.assertEqual(error.exception.code, 2)

    @requirement("R15")
    def test_options_arithmetic_and_sensitivity(self):
        rows = compare()["options"]
        self.assertEqual([r["first_year_cad"] for r in rows], [108000, 75960, 61680])
        self.assertEqual(rows[2]["monthly_handling_hours"], 95)
        self.assertEqual(rows[2]["claims_per_160h"], 1684)
        self.assertGreater(compare(review_share=1)["options"][2]["first_year_cad"], rows[0]["first_year_cad"])
        self.assertLess(compare(monthly_claims=100)["options"][0]["first_year_cad"],
                        compare(monthly_claims=100)["options"][2]["first_year_cad"])
        for args in ({"monthly_claims": 0}, {"review_share": 1.1}):
            with self.assertRaises(ValueError):
                compare(**args)
