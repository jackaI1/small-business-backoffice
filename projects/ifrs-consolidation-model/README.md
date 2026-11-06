# Group finance model

I built this to learn how accounts from several companies can become one set of group accounts. I use a fictional Canadian parent and three subsidiaries. The names, transactions, forecasts and exchange rates are synthetic.

I convert the balances into Canadian dollars and remove matching amounts between the companies, so internal transactions do not count as outside business. The annual example produces financial statements, supporting tables and a review checklist. It also exports scenario plans as CSV files.

## Run the example

With Python 3.11 or newer, from this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ifrs-close --statutory --input examples/statutory_group --output output/first-close
```

I open `output/first-close/annual_financial_statements.md` for the report. Each run needs a new output folder. A blocked close writes diagnostics and exits with a failure status.

## How I keep the calculations separate

`src/ifrs_consolidation/model.py` handles translation and consolidation with decimal arithmetic. `annual.py` assembles the annual presentation and checks it across periods. `cli.py` reads the CSV inputs and writes the pack, input hashes and review status. The [accounting guide](docs/accounting.md), [annual guide](docs/statutory.md) and [Power BI guide](docs/power-bi.md) explain the input conventions and outputs.

I translate balance-sheet accounts at closing rates, income and expenses at average rates, and opening equity at supplied historical rates. Reciprocal intercompany entries must match before they are eliminated. The example keeps currency movements separate from ordinary profit.

## Tests and limits

I ran the suite locally on Python 3.12: **75 tests passed**. The synthetic annual example also reported **99 automated checks passed**. Its manual review items remain pending. To run the suite:

```sh
python -m pytest -q
```

This is a simplified group model. It does not automatically handle acquisitions, goodwill or minority ownership, and its generated report is not an audited or filed statement pack.
