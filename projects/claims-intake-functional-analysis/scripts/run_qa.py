"""Execute all tests and emit deterministic, requirement-traced evidence."""
import argparse
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from claims_intake.core import connect, intake, seed_policies, summary
from claims_intake.options import compare
from claims_intake.qa import aggregate
from contextlib import closing
from datetime import date


class TracedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = []

    def startTest(self, test):
        super().startTest(test)
        self.outcomes.append({"test": test.id(), "status": "PASS",
                              "requirements": list(getattr(getattr(test, test._testMethodName), "requirements", ()))})

    def fail(self, test):
        # unittest passes a _SubTest object for a skipped subcase.
        parent = getattr(test, "test_case", test)
        for row in self.outcomes:
            if row["test"] == parent.id():
                row["status"] = "FAIL"

    def addFailure(self, test, err):
        self.fail(test)
        super().addFailure(test, err)

    def addError(self, test, err):
        self.fail(test)
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.fail(test)
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.fail(test)
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.fail(test)
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err:
            self.fail(test)
        super().addSubTest(test, subtest, err)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, resultclass=TracedResult).run(suite)
    requirements = json.loads((ROOT / "docs/requirements.json").read_text())
    ids = [r["id"] for r in requirements]
    outcomes = sorted(result.outcomes, key=lambda o: o["test"])
    rows = aggregate(ids, outcomes)
    trace_valid = all(o["requirements"] and set(o["requirements"]) <= set(ids) for o in outcomes)
    passed = result.wasSuccessful() and trace_valid and all(r["status"] == "PASS" for r in rows)
    paths = sorted(p for folder in ("claims_intake", "tests", "scripts")
                   for p in (ROOT / folder).glob("*.py")) + [ROOT / "docs/requirements.json"] \
            + sorted((ROOT / "samples").glob("*.json"))
    digest = hashlib.sha256()
    for p in paths:
        digest.update(str(p.relative_to(ROOT)).encode() + b"\0" + p.read_bytes())
    output = {"status": "PASS" if passed else "FAIL", "source_sha256": digest.hexdigest(),
              "test_methods_run": result.testsRun, "requirements_passed": sum(r["status"] == "PASS" for r in rows),
              "requirements_total": len(rows), "requirements": rows, "tests": outcomes}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "qa.json").write_text(json.dumps(output, indent=2) + "\n")
    lines = ["# Executed QA report", "", "Fictional process, synthetic data. Regenerate with `python3 scripts/run_qa.py`.", "",
             f"Result: **{output['status']}**. {result.testsRun} test methods; {output['requirements_passed']}/{len(rows)} requirements passed.", "",
             "A requirement passes only when every linked test passes. Missing coverage and skipped tests fail the gate.", "",
             f"Source SHA-256: `{digest.hexdigest()}`", "", "| Requirement | Result | Executed test methods |", "| --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['id']} | {row['status']} | " + ", ".join(t.rsplit(".", 1)[-1] for t in row["tests"]) + " |")
    (args.output / "qa.md").write_text("\n".join(lines) + "\n")
    with closing(connect(":memory:")) as db:
        seed_policies(db, json.loads((ROOT / "samples/policies.json").read_text()))
        sample = intake(db, json.loads((ROOT / "samples/claims.json").read_text()), date(2026, 1, 15))
        sample_report = {"fictional": True, "as_of": "2026-01-15", "summary": summary(db),
                         "claims": [{"id": r["id"], "claim_ref": r["claim_ref"], "status": r["status"],
                                     "reasons": json.loads(r["reasons"])} for r in sample]}
    (args.output / "sample-run.json").write_text(json.dumps(sample_report, indent=2) + "\n")
    (args.output / "options.json").write_text(json.dumps({"base": compare(),
        "60_percent_review": compare(review_share=0.6), "all_review": compare(review_share=1)}, indent=2) + "\n")
    print(stream.getvalue(), end="")
    print(f"Requirements: {output['requirements_passed']}/{len(rows)}; overall {output['status']}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
