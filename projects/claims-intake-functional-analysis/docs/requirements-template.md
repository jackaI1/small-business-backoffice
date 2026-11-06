# Functional requirement template

Copy this for another process. Replace assumptions with confirmed decisions before using it outside a prototype. The completed catalogue for this fictional process is [requirements.json](requirements.json).

| Field | Fill in |
| --- | --- |
| ID and title | Stable ID, short action |
| Business problem | Who loses time or receives a wrong result today? |
| Source and confidence | Actual source, date, confirmed fact or assumption |
| Owner and approver | Who needs it; who accepts the result? |
| Priority | P1 required for pilot, P2 decision support, P3 later |
| Trigger and input | What starts the action; required data and format |
| Expected behaviour | One observable outcome using “shall” |
| Rules and dependencies | Linked rule IDs and requirements |
| Exceptions | Missing, conflicting, repeated or unavailable input |
| Acceptance examples | Given / when / then, including boundaries |
| QA trace | Test case IDs and expected results |
| Status and evidence | Proposed / agreed / implemented / verified; link to executed report |
| Change record | Version, reason, impact on existing cases |

## Completed example: R08, preserve conflicting submissions

- **Problem:** Replacing an earlier submission would hide what changed and could start duplicate work.
- **Source:** My fictional scenario assumption, version 1. No insurer interviews or private records.
- **Owner / approver:** Claims supervisor / business owner (fictional roles).
- **Priority:** P1.
- **Trigger / input:** A new batch item with an existing `claim_ref` but a different canonical JSON payload.
- **Behaviour:** The intake service shall store the changed submission with a new internal ID, preserve the original and flag `REFERENCE_CONFLICT` for human review.
- **Dependencies:** BR07, BR08, R07, R09, R10, R13. Identical retries follow R07 instead.
- **Exception:** A missing reference makes the whole batch untrackable, so R01 rejects it before storing any claims.
- **Acceptance:** Given a stored claim, when the amount changes under the same reference, then two records exist and the new one needs review. Neither is a payment approval.
- **QA trace:** `test_conflicting_reference_preserves_both_versions`, `test_identical_retry_is_idempotent_even_on_later_day`, `test_storage_failure_rolls_back_claims_and_audit`.
- **Status / evidence:** Implemented; actual execution status is in [qa.md](../reports/qa.md).
- **Change record:** Version 1, initial prototype. Future correction support must retain this history.
