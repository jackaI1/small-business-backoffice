# Running a review from start to finish

All names, amounts, records and dates in `examples/` are fictional. I use the role
names Controller, Accountant and Internal reviewer rather than real people.
Run `controls --help` or `controls record --help` for the command list. `--db`
goes before the command. Every command prints JSON and errors return exit code 2.

## A complete small walkthrough

After the README installation commands, I start a separate review. This first
selection inspects all six months so the supplied June exception is definitely
in the saved selection. Smaller random selections work as in the README, but a
result must refer to an item that was actually selected.

```sh
controls --db walkthrough.sqlite init
controls --db walkthrough.sqlite record process examples/process.json
controls --db walkthrough.sqlite record control examples/control.json
controls --db walkthrough.sqlite record population examples/population.json
controls --db walkthrough.sqlite sample POP-BANK-H1 --size 6 --seed walkthrough \
  --rationale "Inspect all six months for this walkthrough" --tester "Internal reviewer"
controls --db walkthrough.sqlite record result examples/result.json
controls --db walkthrough.sqlite list deficiencies
controls --db walkthrough.sqlite record request examples/request.json
controls --db walkthrough.sqlite evidence AR-BANK-01 examples/evidence/bank-review.txt \
  --actor Controller
controls --db walkthrough.sqlite status --as-of 2026-08-10
controls --db walkthrough.sqlite export walkthrough.xlsx --as-of 2026-08-10
controls --db walkthrough.sqlite extract 1 recovered-bank-review.txt
```

The sample run is 1 in this new database. The June reconciliation agrees to the
ledger, but the approval has no date. The result therefore creates deficiency 1
with a Controller owner and an August 1 due date. The request is `received`,
not `fulfilled`: a person still needs to assess whether the evidence is enough.

I use `controls list documents` to read all earlier narrative and control versions,
`controls list results` for test records, and `controls list events` for recorded
changes. Every `list` command needs the same `--db` argument as the other commands.
For example: `controls --db walkthrough.sqlite list documents`.

## Input records

`controls --db review.sqlite record KIND file.json` reads one JSON object.
Extra or missing fields fail instead of being silently ignored. File paths inside
JSON are relative to that JSON file. Shell arguments for evidence paths are relative
to the current directory. Dates use `YYYY-MM-DD`; due dates may be in the past so I
can capture and report overdue work.

| Kind | Required fields | Purpose |
| --- | --- | --- |
| `process` | `id`, `name`, `narrative`, `author`, `reason` | Add a process or append its next version |
| `control` | `id`, `process_id`, `risk`, `description`, `owner`, `frequency`, `key`, `assertion`, `test_procedure`, `evidence_expected`, `author`, `reason` | Add a control or append its next version |
| `population` | `id`, `control_id`, `period_start`, `period_end`, `source`, `reconciliation`, `items` | Save the complete supplied occurrence list with its current document versions |
| `result` | `run_id`, `item_id`, `outcome`, `notes`, `tester`, `evidence_file` | Record one selected item's result and preserve its evidence |
| `request` | `id`, `control_id`, `description`, `owner`, `due`, `requested_by` | Open an evidence request |
| `followup` | `request_id`, `description`, `owner`, `due`, `actor` | Record a question about an unfinished request |
| `resolve-followup` | `followup_id`, `actor`, `notes` | Explain how a question was answered |
| `fulfill` | `request_id`, `actor`, `notes` | Close a request after evidence arrives and follow-ups are resolved |
| `remediate` | `deficiency_id`, `owner`, `due`, `action`, `actor` | Update an open deficiency's action plan and log the change |
| `close` | `deficiency_id`, `retest_result_id`, `reviewer`, `notes` | Close an open deficiency after a new passing retest |

`frequency` is `daily`, `weekly`, `monthly`, `quarterly`, `annually` or
`per-transaction`. `key` is a JSON boolean, `true` or `false`, not a quoted string.
An assertion describes what should be true about the accounts, for example that
an entry actually happened and belongs in the right period.

Each population item has exactly `id`, `date` and `description`. Item IDs must be
unique within the population and dates must fall within its period. I use a new
population ID for a corrected source list. An existing population, sample or result
cannot be replaced. A control's process cannot change under the same control ID.

`outcome` is `pass` or `exception`. An exception also requires `owner`, `due` and
`remediation`. A pass rejects those fields to avoid implying an unrecorded deficiency.
Evidence files must contain 1 byte to 10 MiB. Their bytes stay in the database,
with SHA-256 fingerprints and the uploader's name. Extraction and workbook export
both refuse to overwrite existing files.

## Following up on evidence

For the walkthrough above, I can save this as `followup.json`:

```json
{
  "request_id": "AR-BANK-01",
  "description": "When was the reconciliation independently approved?",
  "owner": "Controller",
  "due": "2026-07-20",
  "actor": "Internal reviewer"
}
```

Then I run `controls --db walkthrough.sqlite record followup followup.json`.
The returned ID identifies the question. When I receive an answer, I attach the
additional file with `controls evidence`, then submit a `resolve-followup` record
containing that ID and a note explaining the answer. A `fulfill` record closes
the request only if evidence is saved and every follow-up is resolved. Fulfilled
requests cannot take new work; I create a new request for that.

## Updating documents and closing a deficiency

I copy a process or control JSON file, edit the wording and `reason`, then submit
it with the same ID. That adds a new numbered version. Previously saved populations
and tests still point to the old version. The current matrix shows the latest
version, while the Documents sheet retains every version.

After improving a control, I save a new population of post-remediation occurrences,
generate a new sample run, and record the retest result with supporting evidence.
The retest run must have been created after the original exception was recorded
and must test the same control. A passing result from the original sample run or
another control cannot close the deficiency. The person reviewing closure must
still judge whether the new evidence actually demonstrates remediation.

For example, after recording passing retest result 2 for deficiency 1, I save:

```json
{
  "deficiency_id": 1,
  "retest_result_id": 2,
  "reviewer": "Finance lead",
  "notes": "I inspected the new dated independent approval and the passing retest."
}
```

I submit it with `controls --db walkthrough.sqlite record close closure.json`.
These IDs are examples; I use `list results` and `list deficiencies` to find mine.
The original exception remains an exception. The action-plan history and closure
record explain what changed. The built-in `demo` performs this entire sequence.

## Reading the export

The first sheet counts unfinished and overdue items. `overdue` means the due date
is earlier than the supplied `--as-of` date and the item is still unfinished. An
evidence request with a file but unresolved questions remains unfinished. Counts
reflect current records, with deadlines evaluated at that date, not historical
state reconstruction.

The Matrix sheet is the current risk and control matrix. Samples contains one row
per selected occurrence, its original document versions, seed and result. Untested
items say `untested`; they are never counted as passes. Population items contains
every eligible occurrence, not just those selected. Evidence contains fingerprints
and file IDs, not file contents. History links changes to their record IDs.

The sheets are wide because the full review details stay visible. I use filters
and horizontal scrolling rather than shrinking text to fit a printed page. Long
narratives can be expanded in the spreadsheet formula bar. Text over 32,767 characters
or characters Excel cannot represent cause an explicit export error; the database
still retains the full input and `list` can return it as JSON.

## Keeping the database

I work on trusted local files and back up the SQLite file when no command is
running. Database files and generated workbooks are ignored by git. I never put
real company evidence or personal records into this public example. The design
notes describe the audit-trail protections and their limits.
