# life-insurance-projection-lifelib

I built a life-insurance cash-flow calculator to learn how the underlying idea works. This is a learning project.

## What I look at

The example contains 2,500 invented policies in four groups: two 20-year term groups and two whole-life groups. A cohort is just a group with the same starting age, premium and coverage. Whole-life coverage here pays on death through the mortality table's final year, age 119, with no savings account or cancellation payout.

Present value means the value today of future money, after allowing for interest. My report separates the present values of premiums, claims and expenses. Liabilities are claims plus expenses less premiums. A negative liability means the projected future income exceeds the projected payments. The reserve is that same calculation repeated at each future year, using only the remaining payments. I keep negative values visible.

Annual cash profit is premiums less claims and expenses. It excludes investment income, reserve changes and tax, so I do not treat it as accounting profit. The example's base present value of liabilities is **-$9,858,952.20**. That is an outcome of my invented premiums and assumptions, not a finding about an insurer.

## Change the example

I edit [examples/cohorts.csv](examples/cohorts.csv) to change ages, policy counts, coverage amounts, annual premiums or term lengths. All groups start at issue on the same projection date. I edit [examples/assumptions.json](examples/assumptions.json) for a different starting assumption set, then run:

```bash
insurance-project --cohorts examples/cohorts.csv \
  --assumptions examples/assumptions.json --output outputs/my_projection.xlsx
```

The command writes an Excel workbook, a CSV of every projected year and a JSON file containing inputs and results. It runs offline after installation. I can edit counts, benefits and premiums directly on the workbook's Cohorts sheet. I rerun Python for structural changes such as adding groups or changing ages and terms, because those determine the schedule's rows.

## My assumptions

I use the [SSA 2022 period life table published with the 2025 Trustees Report](https://www.ssa.gov/oact/STATS/table4c6_2022_TR2025.html), with separate male and female death probabilities for ages 0 through 119. A checked-in CSV makes the source version fixed and keeps projections reproducible. These are US population rates, not a Canadian insured-life pricing table, and I assume no future mortality improvement.

My starting discount rate is 3% a year. Cancellations, called lapses, are 8% in the first year and 4% in later years, applied to survivors after deaths. I allow $200 of acquisition expense per new policy and $40 of annual maintenance expense, growing at 2% a year. Amounts are illustrative USD with no currency conversion.

I compare mortality at 80% and 120% of the starting level, lapses at 50% and 150%, and discount rates one percentage point lower and higher. Premiums stay fixed. Each comparison has its own visible assumption row and live calculation schedule. Editing Base changes Base only; I can edit the comparison rows separately.

## How I built it

I load lifelib's `annuallife/TradLife_A` model through modelx, its formula evaluation engine. The project inherits lifelib's policy-count, premium, claim, expense and present-value cells. My adapter supplies the public mortality table, synthetic cohorts and stated assumptions. It changes the lapse order and projection end condition explicitly so policies reconcile and the final whole-life claim is included.

The workbook reproduces those annual calculations with ordinary cell formulas and checks them against lifelib. It calculates future reserves backwards and discounted cash flows forwards. The net premium comparison is the premium that balances death benefits alone, excluding expenses. I explain the file layout and timing in [docs/model.md](docs/model.md).

This is a deterministic learning model. It has no surrender values, dividends, reinsurance, tax, risk margin, regulatory reserve rules or stochastic investment paths. I built it in lifelib, an open-source actuarial modelling library; I have not used AXIS or validated equivalence with its product calculations.

## Tests and limits

There are 2 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



Retained project workflows: `life-insurance-projection-lifelib-ci.yml`. Their commands use this folder and their triggers use its paths.
