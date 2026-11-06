# cash-reconciliation-forecast

I built a cash checking and planning tool to learn how the underlying idea works. This is a learning project.

## Run my example

I use Python 3.11 or newer and PostgreSQL, a database that keeps the imports and report history. On a Mac with Homebrew:

```sh
brew install python postgresql@16
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
python scripts/check.py
```

That command runs the tests, loads the five example CSV files into a temporary database, and creates the report plus `output/demo/results.json`. It stops its own database afterwards. Installing LibreOffice with `brew install --cask libreoffice` also enables the workbook recalculation test. Without Calc, that one test is skipped.

For Linux, an existing database, or my own CSV exports, I follow the [setup and input guide](docs/usage.md). A [saved example workbook](examples/cash-report.xlsx) is also available to download without running anything.

## What I see in the example

The example uses two CAD accounts and one USD account, with a reporting date of October 31, 2026.

| Result | Example |
| --- | --- |
| Cleared bank/ledger pairs | 8 |
| Linked amount differences needing review | 1, a CAD 25 supplier difference |
| Unmatched source records | 7, including fees, duplicate candidates, and an old cheque |
| Unexplained balance difference after accounting for open items | 0.00 in each account |
| Opening cash converted to CAD | 60,406.88 |
| First week's closing cash | 20,156.88 |
| First week's lowest daily cash | 5,156.88 |
| Weeks with daily cash below my CAD 15,000 target | 6 of 13 |

## How I use the report

I start with **Forecast** to see cash and warnings. **Expected cash** contains the planned receipts and payments, with signed amounts, dates, and the conversion rate for USD. Blue numbers are editable inputs. **Daily cash** shows the calculations behind the weekly low.

For reconciliation, I look at **Open items** for unmatched records and amount differences, then **Matches** to trace each bank-to-ledger link. **Account checks** explains the difference between the two closing balances. A zero unexplained difference means the bridge balances; it does not mean every open item has been resolved.

To refresh the report, I change the CSVs and rerun the command. Workbook edits are temporary what-if changes and do not write back to the database. To add cash events, I add CSV rows and regenerate the report.

## How I built it

The Python command validates the CSVs before storing anything. PostgreSQL keeps each complete import as an immutable snapshot identified by a file-content hash. Importing the same files again reuses that snapshot, while each report run gets its own history record. Matching uses rows read back from the database.

I match within the same account using signed amount, a configurable date window, and references with spaces and punctuation removed. I accept only a unique candidate in both directions. A shared reference with a different amount becomes a review item. Conflicting references and repeated candidates stay open. I never match CAD directly against USD.

For the forecast I start from bank closing balances, exclude receipts already recorded in the bank, and place overdue unpaid items on the first forecast day. I use the latest exchange rate on or before the reporting date and reject rates more than 14 days old. Amounts use decimal arithmetic, with conversion rounded to cents for each account balance and cash event.

I keep the matching rules, balance equation, database design, and forecast assumptions in [docs/design.md](docs/design.md). The Excel file is written by Python with formulas, cached results for previews, and a native chart linked to the forecast cells.

## Limits I keep in mind

This is a local planning tool using synthetic data. I review differences myself; it does not post journal entries or connect to a bank. Matching is one bank line to one ledger line, so split payments and batch deposits need manual review. The forecast assumes all three accounts' cash can be pooled, uses a fixed exchange rate, and nets payments within each day. It cannot show an intraday overdraft or account-specific transfer restrictions.

## Tests and limits

There are 6 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `cash-reconciliation-forecast-ci.yml`.
