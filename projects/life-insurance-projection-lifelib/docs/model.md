# Model and report notes

I use annual, deterministic expected cash flows. Fractional policy counts represent expected outcomes, not actual people. Every cohort is new business at time zero, with level annual premiums payable while the policy is in force. There are no private records.

## Calculation order

For year t starting at t=0, N is the opening policy count, q is the attained-age death probability and l is the cancellation probability conditional on surviving the year:

```text
deaths       = N * q
lapses       = (N - deaths) * l
survivors    = N - deaths - lapses
premiums     = N * annual premium
claims       = deaths * benefit
acquisition_this_year = acquisition if t=0, otherwise 0
expenses     = N * (maintenance * (1 + inflation)^t + acquisition_this_year)
cash profit  = premiums - claims - expenses
```

The actual expense expression adds acquisition only in the first year; maintenance applies every year. Premiums and expenses occur at the start of the year. Death claims occur at the end. Lapses have no payout. A term policy's remaining survivors expire after its final covered year with no maturity benefit. Whole life includes the death year at attained age 119. Its q stays 1 even when a mortality sensitivity is below 100%, so there is no unpaid tail.

This sequential lapse convention is an explicit change from TradLife_A's additive decrement default. I also replace its projection-length default: the supplied public table extends past the template's commutation-table limit, and its final death year must be included. I do not use the template's commutation pricing or reserve placeholders. I use the inherited cash-flow present-value cells instead.

## Present values and reserves

With v=1/(1+i), I discount premiums and expenses in year t by v^t, and claims by v^(t+1). PV liabilities = PV claims + PV expenses - PV premiums. PV cash profit is its negative. These signs are from the insurer's viewpoint.

At the start of year t, before that year's premium and expenses, the aggregate cohort reserve is the present value of its remaining claims and expenses less remaining premiums. I use the same assumptions as the cash-flow projection, allow negative reserves and set the reserve after expiry to zero. These are gross prospective best-estimate values, not statutory reserves, cash surrender values or required capital.

The workbook uses the equivalent backward recursion:

```text
reserve_start[t] = expenses[t] - premiums[t]
                 + (claims[t] + reserve_end[t]) / (1 + i)
reserve_end[t]   = reserve_start[t+1]
final reserve_end = 0
```

The net premium is PV death benefits divided by the annuity-due value of premium payments, on the Base mortality, lapse and discount basis, excluding expenses. An annuity due means payments at the start of each year while a policy remains in force. With constant q=10%, interest 5% and three covered years:

```text
annuity due = 1 + 0.9/1.05 + 0.81/1.05^2
benefit PV for $1,000 = 100/1.05 + 90/1.05^2 + 81/1.05^3
net premium = benefit PV / annuity due = $95.238095...
```

Tests also cover zero and negative interest, a one-year expense example and a two-year whole-life example. A flat deterministic rate is both the valuation and discount rate. I do not project an asset portfolio or investment earnings.

## Source and assumption provenance

`insurance_projection/data/ssa_2022.csv` contains the age and male/female death-probability columns from the [Social Security Administration's 2022 period life table, 2025 Trustees Report](https://www.ssa.gov/oact/STATS/table4c6_2022_TR2025.html), retrieved November 5, 2026. The source is a US federal publication. The input file has all 120 ages, with no interpolation or smoothing. Source sentinel values and probability bounds are tested.

Population mortality includes people who would not qualify for an insured-life product. I chose it for a reproducible public example, not as a suitable underwriting table. Premiums, cohort sizes, expenses, lapses, inflation and discount rates are my illustrative assumptions and are not calibrated to experience. Mortality is multiplied by the scenario factor and capped at 1, except terminal q remains exactly 1. Lapses are similarly capped at 1 after multiplying the duration rate by the scenario factor.

## Files and data flow

- `engine.py`: validates inputs, loads lifelib's installed annual model and evaluates inherited cells. Each run Space is deleted in `finally`; the model closes on context exit.
- `cells.py`: the explicit modelx overrides, including assumption access, sequential lapses and final projection year.
- `cli.py`: reads the CSV and JSON, runs seven scenarios, writes the workbook and machine-readable results.
- `report.py`: builds ordinary Excel formulas with lifelib results as initial cached values. Recalculation works offline and does not invoke Python. Every comparison has an independently editable assumption row, with its calculation rows on the visible Projection sheet.
- `tests/`: independent numerical examples, input validation, model cleanup, full report reconciliation and native spreadsheet edits.

Excel rows are created from the supplied ages and terms. Counts, benefits, premiums, mortality probabilities and assumption rates are live inputs. For new cohorts or different ages, sexes and terms, I edit the source files and regenerate the report. Excel validation helps with normal assumption edits; Python is the input-validation boundary for custom model definitions. Entering text or deleting required workbook inputs is outside the supported edit workflow.

The seven sensitivity rows are independent comparisons against their original starting assumptions. I use visible annual schedules because mortality and lapse sensitivities need the policy counts recalculated, and comparing three different drivers is clearer here than a two-input What-If table. Summary formulas aggregate those schedules; they do not approximate the change with a multiplier on finished results.

The report's native recalculation tests launch LibreOffice with a new temporary profile and a scoped process group. They close that group on completion or failure and verify that it is gone. CI installs LibreOffice rather than accepting a test run with these checks skipped. The checked-in workbook is an example; CI regenerates reports from source on every push and pull request.
