# Importing the planning and close pack into Power BI

I export plain UTF-8 CSVs so the calculations can be inspected without Power BI.
The model does not need a Microsoft account. I have tested the CSV keys, dimensions,
scenario/year isolation and translated-to-consolidated bridge in pytest; I do not
include a Power BI desktop report or claim a live service deployment.

1. Run the README example. In Power BI Desktop, choose **Get data > Text/CSV** and
   import `fact_financials.csv`, `dim_entity.csv`, `dim_account.csv`, `dim_period.csv`
   and `dim_scenario.csv` from the same output folder.
2. Set all key columns to Text, including `period`, and `amount` to Decimal Number
   using an English locale (decimal point). Source CSVs retain the Python decimal
   amounts; Power BI may round them to its numeric precision. Keep reconciliation
   checks in Python as the authority. Do not use fixed-decimal currency type if
   preserving more than four decimal places matters.
3. Create one-to-many, single-direction relationships from each dimension's key to
   the matching fact column: entity, account, period and scenario. Dimension keys
   are unique. There is one fact per `(scenario, period, entity, account, stage)`.
4. Use scenario and period slicers. Actual is the October monthly close in the original example, or the full
   year ended October in annual mode. The dimension grain identifies which. Base and
   Downside are annual income-only plans for 2027 to 2029. An annual plan is not directly comparable to an actual month; do not sum
   actual and planned periods together. The annual mode uses the `2026-10` key
   for its October year-end and labels its grain as year.
5. Filter `stage = consolidated` and `entity = GROUP` for a group statement. For an
   audit bridge, use the entity rows at `translated` plus `elimination`, comparing
   their sum against the group consolidated stage. Summing all stages together
   counts the group twice.

Every fact amount is in the presentation currency (CAD in the sample), with debit
positive and credit negative. `translated_ledger.csv` separately retains the local
currency, local amount, rate, reference and rate basis for each input row.
`elimination_journal.csv` preserves individual elimination references; the fact set
aggregates them at entity/account level.

These measures make a small income view. With one scenario and one period selected:

```dax
Group Signed Amount =
CALCULATE(
    SUM(fact_financials[amount]),
    fact_financials[stage] = "consolidated",
    dim_entity[entity] = "GROUP"
)

Revenue =
-CALCULATE([Group Signed Amount], dim_account[kind] = "revenue")

Expenses =
CALCULATE([Group Signed Amount], dim_account[kind] = "expense")

Profit = [Revenue] - [Expenses]
```

For a matrix, use scenario and period as columns, account as rows, and Group Signed
Amount as values. Use account kind filters to separate the position from income.
`translation_reserve` is a synthetic equity account; `translation_oci` is its current
period movement. They are linked amounts, not two independent income entries.
Exclude OCI and equity from a profit measure. Annual plans have no reserve or OCI
facts because they do not project financial position.

Use `plan_income_statement.csv` for a simpler already-presented view, without
relationships or sign changes. It includes separate subtotal rows; filter to the
line you want instead of adding revenue, gross profit and profit together. The
statement of financial position and income CSVs also contain subtotal rows.
