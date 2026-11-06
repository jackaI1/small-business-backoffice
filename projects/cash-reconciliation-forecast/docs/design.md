# Reconciliation and forecast design

## Import and history

`inputs.py` reads five strict CSV contracts into typed records. `db.py` creates the tables from `schema.sql` and stores the complete import inside a transaction. A SHA-256 hash of filenames and file bytes identifies the snapshot. An advisory transaction lock serializes simultaneous imports of the same hash. Unique keys and foreign keys protect the normalized accounts, entries, expected flows and dated FX rates.

The CLI reads that snapshot back from PostgreSQL before calculating. It saves the report parameters and result as a JSONB audit record with a new run ID. Repeating an import does not duplicate transactions. Editing a file makes a new independent snapshot. Historical snapshots are retained until the database owner removes them. This project intentionally has no delete-history command.

Database commits precede local file generation. If disk writing fails, the completed run remains in the database; rerunning safely produces another run and replaces the local report. Report files are snapshots, not a database editing interface. The JSON stores money as strings to preserve decimal precision.

## Matching

Only entries on or before `as_of` are eligible. Accounts must agree and posting dates must be within the inclusive calendar-day window (default three, configurable zero to 31).

I apply three passes:

1. Same nonempty normalized reference and exact signed amount.
2. Exact signed amount with a missing reference on at least one side.
3. Same nonempty reference with a different amount, reported as `variance_review`.

References are uppercased and stripped to ASCII letters and digits. Each pass builds a candidate graph and accepts an edge only if it is the sole candidate for both records. Accepted records leave the pool. Stable IDs determine output order, so reversing the CSV order does not change results. The third pass creates a review link, never a cleared match. Conflicting nonempty references with equal amounts stay open. Many-to-one and one-to-many settlement are unsupported.

For unmatched entries I retain candidate IDs and distinguish no candidate from ambiguity or conflicting references. Age is reporting date minus posting date; variance links use the older of their two dates. Bands are 0-7, 8-30, 31-60 and 61+ calendar days.

The matching passes compare candidate records in memory. They suit monthly exports and are quadratic in the worst case. The PostgreSQL index supports dataset/account/date/amount inspection, but this version does not promise high-volume bank-feed performance.

## Balance bridge

For each account, closing cash is opening cash plus signed in-period entries. The independently computed balance difference must equal:

```text
bank closing - ledger closing
  = bank opening - ledger opening
    + unmatched bank amounts
    - unmatched ledger amounts
    + sum(bank amount - ledger amount for linked pairs)
```

The remainder is `unexplained`. It should be zero even when open items exist. Open item counts and variance amounts remain separate review signals. I do not adjust source balances or post an automatic journal entry to force agreement.

## Cash forecast

I value each account's bank closing balance using its latest FX rate on or before `as_of`. Rates older than 14 days fail. USD rates mean CAD per USD; CAD must be 1. I use `Decimal` in Python and `NUMERIC` in PostgreSQL, with half-up rounding to cents on each converted balance and expected event.

The horizon starts on `as_of + 1` and ends on `as_of + 91`, inclusive. Expected cash already linked to an in-period bank settlement is excluded to prevent counting it twice. Events beyond the horizon are listed as excluded. Unpaid overdue events are pulled into the first day, with their original dates and overdue ages retained. Noncash ledger entries do not automatically become future cash.

For each week, closing = opening + receipts + signed payments. Next week's opening equals that closing. Separately, I compute daily net balances and compare the lowest value, including the week's opening balance, with minimum liquidity. Exactly meeting the minimum is allowed. The weekly warning can therefore flag a shortfall even with positive closing headroom.

The model assumes freely pooled cash across accounts and a constant as-of FX rate. It does not model bank transfer delays, restricted cash, intraday payment order, interest or credit facilities. Estimated collections are inputs, not a statistical prediction of customer behaviour.

## Workbook and tests

`report.py` uses XlsxWriter so a fresh Python installation can produce the report without Node or Excel automation. Source strings are written as literal text to prevent CSV formula injection. Expected cash has row-level conversion formulas. Daily net cash uses bounded `SUMIFS`; weekly cash rolls forward with formulas; daily lows use `MIN`; warnings use `IF`. A native line chart references the forecast cells.

The workbook keeps audit checks downstream of the forecast. Changing an unexplained-balance check cannot change the forecast. Inputs are blue, the forecast is first, and exceptions are highlighted by conditional formatting. Cached formula values make file previews useful, while Calc/Excel performs full recalculation when inputs change.

Pytest checks matching boundaries and duplicates, currency isolation and rounding, FX selection, ageing, settlement exclusions, horizon cutoffs, the cash rollforward and the daily minimum. PostgreSQL tests use isolated schemas to prove idempotency, round trips, rollback and foreign-key enforcement. Workbook tests inspect the chart's cell references, reject formula injection, compare cached results with Python, and change a later receipt and the liquidity threshold before a real LibreOffice recalculation.

CI runs these tests with PostgreSQL 16 and LibreOffice Calc and then creates the example report. The local helper owns a temporary PostgreSQL process and shuts it down in a `finally` block, including failed tests.
