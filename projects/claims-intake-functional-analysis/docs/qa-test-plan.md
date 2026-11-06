# QA test plan

## Scope and execution

This plan tests the fictional intake requirements against Python functions, a real SQLite database and the command line. Inputs are synthetic. There were no pre-existing tests in the initial repository. Run `python3 scripts/run_qa.py` from the repository root; it discovers and runs the entire `tests/` suite and generates [qa.md](../reports/qa.md), [qa.json](../reports/qa.json), the sample-run report and the options calculations. `python3 -m unittest discover -v` also runs the suite directly.

Entry conditions: Python 3.9 or later, a writable temporary directory and the committed sample files. There are no packages to install or network services to start. Each function test gets a fresh database; disk/CLI tests use temporary directories that close connections and delete files on exit. A fixed 2026-01-15 evaluation date keeps outcomes reproducible.

## Planned cases and trace

The stable test case IDs are the Python method names shown below, under `tests/test_intake.py` unless otherwise noted. Each method is tagged with its requirement IDs in code. Subcases exercise boundaries and invalid types within each method. The generated report lists the full exact method names for every requirement, including shared cases.

| Requirement | Primary cases | Expected result |
| --- | --- | --- |
| R01 | complete_claim_routes_to_adjuster; malformed_batch_is_rejected_before_any_write; cli_roundtrip | Valid batch imports; invalid envelope exits 2 with no partial writes |
| R02 | every_required_business_field_can_be_missing; bad_field_types_are_reviewable | Each missing field and invalid type receives a reason and review route |
| R03 | policy_and_property_conflicts; policy_boundaries_are_inclusive; policy_snapshot_is_immutable_and_atomic | Unknown/mismatch/outside flagged; exact endpoints allowed; changed snapshot rolled back |
| R04 | dates_and_chronology; policy_boundaries_are_inclusive | Invalid calendar/format, reversed chronology and future dates flagged |
| R05 | amount_boundaries_and_loss_types; bad_field_types_are_reviewable | Zero/negative/fraction/bool/over-limit rejected as amounts; threshold just below/at CAD 25,000 works |
| R06 | each_loss_type_evidence; bad_field_types_are_reviewable | Each type has its required labels; malformed labels flagged |
| R07 | identical_retry_is_idempotent_even_on_later_day; two_connections_share_duplicate_protection | Same ID and original decision/date, one intake event |
| R08 | conflicting_reference_preserves_both_versions; duplicate_signal_and_distinct_claims | Conflict and same-loss match flagged; different date/policy not treated as duplicate |
| R09 | complete_claim_routes_to_adjuster; every_required_business_field_can_be_missing; conflicting_reference_preserves_both_versions | Clean record ready, any flagged record needs review |
| R10 | sample_batch_and_disk_reopen; review_is_audited_and_removes_only_pending_item | File survives reopen; intake/review audit retains actor, timestamp, decision and reasons |
| R11 | review_guards_and_each_action; review_is_audited_and_removes_only_pending_item; cli_roundtrip | Three actions work; missing/clean/already-reviewed claim, blank actor and unsupported action fail |
| R12 | review_is_audited_and_removes_only_pending_item; sample_batch_and_disk_reopen; cli_roundtrip | Counts reconcile; reviewed item leaves pending queue and keeps original status |
| R13 | malformed_batch_is_rejected_before_any_write; storage_failure_rolls_back_claims_and_audit; two_connections_share_duplicate_protection | No partial writes after a deliberately injected SQLite failure; second writer gets lock error |
| R14 | tests/test_qa.py: missing_failed_and_skipped_coverage_cannot_pass; all_linked_tests_must_pass | Missing, failing or skipped coverage cannot become a passing requirement |
| R15 | options_arithmetic_and_sensitivity | Base costs $108,000/$75,960/$61,680; all-review and low-volume cases reverse decision |

Case names in the table omit the `test_` prefix for readability. The lock test uses two independent connections with a held write transaction, rather than relying on thread timing. A test-only database trigger injects a storage failure after a first valid item to check rollback of both claims and audit events. No fault injection exists in the application flow.

## Release gate and evidence

A requirement passes only if it has at least one executed case and all linked cases pass. Skips, expected failures, errors, failed subcases and missing coverage fail the gate. Untagged tests and unknown requirement tags also fail the runner. The overall command must return zero. The report includes a hash of source, tests, runner and requirement catalogue to identify its input; it is not a signature or independent certification.

GitHub Actions repeats the suite on Python 3.9 and 3.13 for pushes and PRs. It regenerates the reports and fails if they differ from the committed baseline, then uploads evidence even on failure. Results on `main` must be green before calling the change complete. The report contains no elapsed times so it can be compared across machines.

I manually reviewed the process maps, the rule-to-requirement links and decision arithmetic against the code. This is a document review, not stakeholder approval or a usability study. The README commands are exercised through the CLI round-trip test; the first 12-record sample run should yield 2 ready, 10 flagged and 10 awaiting review. After one request-information action, 9 should remain pending. Repeating submission should create no new records.

Not covered: production load, attachment authenticity, actual insurance wording, security/access control, disaster recovery or staff handling time. These remain pilot/production acceptance work rather than implied passes. Full test evidence appears in [the executed matrix](../reports/qa.md), with per-case status in [qa.json](../reports/qa.json).
