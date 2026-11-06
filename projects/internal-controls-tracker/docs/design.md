# How I keep a control test traceable

I use one local SQLite database for a fictional company's financial close. A process
narrative explains who does what. Each control links the risk, financial assertion
(what should be true about the accounts), owner, frequency, evidence expected and
test procedure. A key control is one the reviewer considers important enough to
rely on. That flag does not automatically establish effectiveness.

I chose a command-line tool and JSON input files so I can repeat a close-cycle
exercise and review changes in ordinary text. A spreadsheet alone would make it
too easy to overwrite a test's original control wording. A hosted web application
would add accounts and deployment work without improving this single-user exercise.

## Documents and populations

Process and control edits append numbered versions with an author, timestamp and
change reason. Existing versions cannot be updated or deleted through SQLite.
A population is the complete supplied list of control occurrences for an explicit
period, with source and completeness-reconciliation notes. It freezes the current
process and control versions and hashes the canonical JSON. The reviewer must
check completeness against the source system. The tool cannot prove that an
uploaded list includes every occurrence.

## Repeatable selection

For each unique item ID, I calculate SHA-256 over a JSON array containing the seed
and item ID. I sort by that value, breaking ties by item ID, and take the requested
number without replacement. This is deterministic pseudorandom ranking, named
`sha256-rank-v1`. It avoids dependence on Python's random-number implementation,
input row order or database row order. The database retains the entire population,
hash, seed, rationale, algorithm and selected IDs. It does not let a later edit
silently change the population or wording behind a completed test.

The user chooses the sample size and explains why. The program does not calculate
a statistically sufficient sample size or project a deviation rate onto a population.

## Evidence, exceptions and remediation

A result can only refer to an item in its saved selection. Pass and exception both
require a tester, notes and an evidence file. I store the actual bytes, filename,
uploader and SHA-256 digest, so moving the original file does not break the record.
Results are append-only and cannot be overwritten. An exception creates a deficiency
in the same transaction, with a remediation owner, action and due date. Changes to
the remediation plan are logged. Closure needs a passing result from a new sample
run created after the exception, for the same control, plus a reviewer and explanation.
The original exception remains visible after closure. The tool does not assign
material-weakness or significant-deficiency classifications.

Requests track who owes which evidence and when. Received files are stored in the
database. Follow-ups have their own owners and due dates. A request can only be
fulfilled after evidence is attached and all follow-ups are resolved. Status reports
use an explicit as-of date so overdue counts can be repeated.

## Review pack and limits

The Python exporter uses openpyxl to make a portable Excel workbook. The current
matrix, requests, follow-ups, deficiencies, populations, sample items, document
versions, evidence metadata and event history have separate sheets because they
have different row meanings. Stable IDs connect them. Dates are Excel dates, headers
are frozen, filters are enabled and long text wraps. All imported text is written
as literal text, never an Excel formula. This is a point-in-time export, not an
editable interface back into the database.

This is a SOX-style learning project, not an audit opinion or a certified compliance
system. I used the [PCAOB's AS 2201](https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201)
as context for keeping control procedures, supporting evidence and deficiencies
connected. That standard requires professional judgments that this tool does not
make. The database owner can still replace the database or disable its triggers.
There is no login, role separation, encrypted storage or tamper-proof external archive.
I use only fictional data and keep the database on a trusted local machine.
