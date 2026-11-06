# Run the cash check

I keep all inputs synthetic in this repository. Each input directory is a complete snapshot, not an incremental feed. I do not combine old snapshots when reporting a new one.

## Install

Python 3.11+ and PostgreSQL 16+ are required. From the repository:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

On Ubuntu, I install `postgresql` and `libreoffice-calc` through apt. I add PostgreSQL's binary directory (for example `/usr/lib/postgresql/16/bin`) to PATH, then run `python scripts/check.py` as a regular user. PostgreSQL refuses to start as root. On macOS, the README gives the Homebrew commands. Calc is optional for normal report generation, but required for the native recalculation test.

## Use an existing database

I create an empty local database named `cash_forecast` using my PostgreSQL role. The role needs permission to create tables and read/write them. I put its connection string in an environment variable, outside the repository:

```sh
export DATABASE_URL='postgresql://localhost/cash_forecast'
cash-forecast --input data/synthetic --as-of 2026-10-31 \
  --minimum-cad 15000 --date-window 3 --output output/demo
```

For hosted databases I use the provider's connection string with TLS. I never paste real credentials or bank exports into a commit. CLI database errors avoid printing the connection string.

To run integration tests against a disposable database:

```sh
export TEST_DATABASE_URL="$DATABASE_URL"
pytest -q
```

Each database test uses a unique schema and removes it afterwards. The main report uses the connection's default schema. The temporary-cluster helper uses loopback-only trust authentication, an unused port, a private temporary directory, and a foreground process handle. It records its PID, start time, port, cleanup command and verified shutdown. It never starts a Homebrew service or touches an existing cluster.

## Input files

I copy `data/synthetic/` to a new folder and preserve the exact column names and order. Dates use `YYYY-MM-DD`. Money is signed with at most two decimal places: receipts positive, payments negative. IDs are stable strings, unique within each file even across accounts. Different IDs with repeated business details are allowed and kept for ambiguity checks.

| File | Contents |
| --- | --- |
| `accounts.csv` | Account ID, CAD/USD currency, common closing balance date, bank and ledger balances on that date |
| `bank.csv` | Bank line ID, account, posting date, signed amount, currency, reference |
| `ledger.csv` | Ledger entry ID and the same fields as bank lines |
| `expected.csv` | Cash event ID, account, due date, signed amount, currency, description, optional settled bank ID |
| `fx.csv` | Currency, effective date, CAD per unit of that currency |

I include every bank and ledger cash entry after the opening balance date through the reporting date. Later rows may be present but are excluded from reconciliation. The program cannot detect a source export that omitted a transaction, so I check export completeness myself.

An empty reference is permitted. Missing accounts, conflicting currencies, duplicate IDs, invalid amounts, missing fields, and entries dated on or before opening balances fail validation. The bank and ledger opening balances may differ; the difference remains explicit in the balance bridge. All accounts must share a balance date.

A `settled_bank_id` must point to a bank entry with the same account and amount. Two expected events cannot claim the same bank settlement. A link only removes expected cash if that bank entry's date is on or before the reporting date. I use the source settlement ID to mark paid invoices; the program does not guess that a same-value invoice has been paid.

I supply CAD at 1 and a USD rate dated within 14 days before the reporting date. These are demonstration assumptions, not market quotes. A future-dated rate is never used early. Rates allow up to six decimal places.

## Outputs and review

`cash-report.xlsx` contains the forecast, planned cash, daily calculations, account checks, open items and record links. `results.json` includes the dataset hash, run ID, rule used for every pair, candidate IDs, ages, selected FX dates, excluded expected items and daily-low warnings.

Amounts in reconciliation remain in their account's currency. Only the forecast is consolidated into CAD. For the example, the CAD operating difference of 1,540 is explained by 565 of bank-only items, minus -1,000 of ledger-only items, plus the -25 paired variance. The USD difference is a bank fee of -15.

The first forecast period starts the day after the reporting date, even if that is a weekend. Each period is exactly seven days and the horizon is 91 days. To resolve an overdue item, I update its due date or settlement link in the next snapshot. The helper produces 34 included expected cash events and excludes one paid event and one beyond the horizon.

In the workbook I can edit existing planned dates, amounts, FX rates, opening cash and the minimum target. Formula ranges cover the generated rows and dates; adding new events or moving them outside the horizon needs a fresh CSV run. The overdue-days field is a source snapshot, so changing a planned date does not change the original overdue age. The chart is linked to the weekly closing cash, daily lows and minimum target.
