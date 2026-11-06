# Import rules

The importer accepts UTF-8 comma-separated Details Only exports, optionally with a byte-order mark. Quoted commas and extra columns work. Formatted Salesforce reports with title lines, subtotals, currency symbols or footers need to be exported as detail rows instead.

The supported column labels are in the README and the three files under `demo/`. The separate contact and opportunity formats do not need a Record Type column. The combined format requires every header in `demo/salesforce-report.csv` and uses `member` or `sponsor` in Record Type. Blank fields unrelated to that record type are allowed. Consent in the combined format is `yes` or `no`; Email Opt Out in a contact export is `true`/`false` or `1`/`0`.

Membership fields and agreement fields are organisation-specific custom fields, not an assumed standard Salesforce schema. Rename headers after export if necessary. The plugin does not authenticate to Salesforce, fetch reports, or claim a live Salesforce integration.

Every upload is limited to 1 MiB and 2000 nonblank rows. Dates must be real ISO dates (YYYY-MM-DD). Amounts use a decimal point, no grouping, no signs, and at most two decimal places. All amounts are CAD, with a maximum of 9999999.99 per amount. Paid-to-date cannot exceed the pledge. IDs contain letters, numbers, underscores or hyphens, up to 80 characters. Referenced event IDs must already exist in WordPress.

The whole file runs in one database transaction. A missing header, duplicate ID in one file, conflicting email, invalid value or missing event rejects the upload without partially changing records. The error identifies the row where validation failed. Database failures show a generic retry message rather than exposing SQL.

Across files, the same member or agreement ID updates the existing record. Imports cannot move a member's expiry behind a recorded renewal. Once a recipient uses an unsubscribe link, subsequent imports and member form edits cannot silently subscribe them again. This release deliberately has no re-subscription action; a real consent recovery workflow needs a separate design.

An opportunity import is the current snapshot of an agreement, including its paid-to-date value. It is not a payment transaction ledger, and an older opportunity export can overwrite a newer pledge or paid amount. Export current reports and review dashboard totals after each upload. No rows are deleted when absent from an export.
