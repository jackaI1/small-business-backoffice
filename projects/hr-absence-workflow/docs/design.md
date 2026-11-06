# Design notes

I wanted every displayed balance to be explainable from its source records. The app keeps a journal instead of a separately editable balance field.

## Storage and boundaries

`employees` holds the employment record and optional link to a login. `file_notes` appends dated HR notes. `users` stores roles and PBKDF2-HMAC-SHA256 password hashes with a separate random 16-byte salt per account and 260,000 iterations. `requests` holds dates, duration, status, decision details and separate cancellation details. `ledger` holds signed minute changes, running balances, reasons, actors, timestamps and source references. `events` records other operations alongside balance events.

The CLI authenticates a stored account before calling the service. Every HR-only service operation checks its role, and manager request operations check the employee's assigned manager. The manager list explicitly selects request data and the employee name/code; it does not fetch file notes or employment dates. A linked employee account cannot decide its own request, even when it has the HR role. Linking accounts accurately is an administrator responsibility.

This is a local trust model. A user who can open the SQLite file can read tables or drop protections outside the app. It is not encrypted storage, hostile multi-user hosting, a tamper-proof legal archive or a production identity system. Only synthetic data belongs here.

## Balance rules

All changes use whole integer minutes, avoiding floating-point drift. Each weekday is 480 minutes. Pending requests do not consume or reserve a balance. Approval must find enough minutes at that moment. Rejection has no balance effect. Cancellation of approved leave inserts a refund rather than deleting the debit. Cancelled or rejected date ranges are available for another request.

Accrual uses the employee's configured monthly minutes. The calendar month must be complete according to the computer's local date. Employees must have started on or before the first of the month. Zero-rate employees get no entry. There is no proration, carryover cap, holiday calendar, multiple leave types, scheduling service or automatic monthly job. An operator explicitly runs each month, including any historical month they need to reconcile.

## Atomicity and history

Each write starts `BEGIN IMMEDIATE`, which serializes writers before reading a balance. Approval, its journal entry and its operation event commit in one transaction. If any validation or insertion fails, they all roll back. Two concurrent approvals cannot both spend the same hours. SQLite waits up to ten seconds for a lock; a longer conflict returns a CLI error for the operator to retry.

A unique employee/month key prevents duplicate accrual. Unique request/kind keys prevent duplicate debits or refunds. Database triggers reject updates and deletes on the journal and event tables. They prevent accidental edits through ordinary SQL; they do not prevent a database owner dropping a trigger. Failed actions leave no successful-action event.

Reports take the same write lock to keep their row totals and their report event in one consistent snapshot. Letter templates use a restricted field dictionary and Python's standard `string.Template` substitution, which does not execute template code. Output files use exclusive creation, and no command starts a server or background worker.

## Verification

Tests use disposable real SQLite files, saved accounts and actual CLI subprocesses. A concurrency test starts two separate connections with only one day's balance and verifies exactly one approval succeeds. Other tests cover duplicate accrual, invalid dates, overdrafts, scope checks, self-approval, cancellation, immutable history, template validation, CSV formula protection and refusing file replacement. CI runs the full suite on three Python versions.
