# Input contract and accounting workpapers

This guide describes the single-period workpaper engine for a parent with wholly owned
foreign operations held from formation. Its optional annual reporting layer adds the
comparative statutory statement components for a defined Canadian service-group
profile, documented in [statutory.md](statutory.md). Neither mode provides an audit
or professional compliance opinion.

## Basis and scope

I use the mechanics of [IAS 21 paragraphs 39 to 41](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2024/issued/part-a/ias-21-the-effects-of-changes-in-foreign-exchange-rates.pdf?bypass=on)
and [IFRS 10 paragraph B86](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ifrs-10-consolidated-financial-statements.pdf?bypass=on).
IAS 21 permits an average rate as a practical approximation of transaction-date
rates when appropriate; significant volatility requires more detailed source
translation. IFRS 10 requires removal of intragroup items, including unrealised
profits in assets. I therefore limit this model's internal sales to services fully
consumed during the period, so no unrealised profit remains in inventory or equipment.

The manifest must explicitly set `formation_only`, `services_fully_consumed` and
`average_rates_appropriate` to `true`. They are preparer assertions, not facts the
software can independently prove. Each subsidiary must have `ownership: "1"`.
The parent must use the presentation currency. I reject unsupported ownership or
scope rather than create a goodwill or non-controlling-interest plug.

The input ledgers must already reflect common accounting policies, correct local
recognition and measurement, functional-currency remeasurement of foreign monetary
items, and any tax entries. Genuine exchange gains/losses remain in profit;
consolidation does not automatically remove them. Hyperinflation, unavailable
exchange rates, business combinations, disposals, dividends, new capital issues,
purchase-price allocation and unrealised trading profits need a different model.

## Files and signs

`config.json` defines `period` (a valid `YYYY-MM`), `presentation_currency`, `parent`,
`entities`, `rates`, `plan_scenarios`, `plan_periods` and the three scope assertions.
The entity keys are stable identifiers, with `name`, `currency`, `ownership`, and
`opening_cta`. CTA is the cumulative translation adjustment. Opening CTA is in
presentation currency, positive for a credit equity reserve, and must be supplied
explicitly, even when zero. It must be zero for the parent.

Rates have unique `(scenario, period, currency)` keys, with positive `closing` and
`average` decimals. Rates are **CAD per one unit of functional currency**, not the
inverse. Presentation-currency rates must equal 1. All source numbers are decimal
strings, not binary floating-point calculations. CSV headers must be unique and
row widths must match them.

`ledger.csv` columns:

| Column | Meaning |
| --- | --- |
| `entity` | Entity key in the manifest |
| `account` | Exact account name in the fixed chart below |
| `amount` | Functional-currency signed amount: debit positive, credit negative |
| `partner` | Other group entity for intercompany items or parent investments; blank otherwise |
| `reference` | Shared pair identifier for intercompany items; blank for other accounts |
| `historical_rate` | CAD per local unit for historical equity/investment rows; blank otherwise |

The trial balance is **pre-close**. Revenue and expenses remain open. Include
opening retained earnings, not closing retained earnings, to avoid counting current
profit twice. The ledger includes opening equity plus all current closing asset,
liability, revenue and expense balances, and must sum to exactly zero locally.
Split a historical equity account into multiple rows if different tranches need
different historical rates. For opening retained earnings, carry forward the prior
translated amount; an effective historical rate or separate source tranches must
reproduce that amount. Do not retranslate it at the current closing rate.

The chart is intentionally explicit:

| Accounts | Translation basis |
| --- | --- |
| `cash`, `trade_receivables`, `inventory`, `property_plant_equipment` | Closing |
| `trade_payables`, `debt`, `ic_receivable`, `ic_payable` | Closing |
| `investment`, `share_capital`, `opening_retained_earnings` | Supplied historical |
| `revenue`, `cost_of_sales`, `operating_expense`, `finance_expense`, `tax_expense` | Average |
| `ic_service_revenue`, `ic_service_expense` | Average |

Unknown accounts block the close. This avoids silently dropping an unfamiliar
account from a statement. The base workpaper chart does not itself classify current/non-current items.
The annual layer implements that presentation and supporting comparative notes for
its supported cash-only service-group profile; other material accounts are rejected
until the annual profile and disclosures are extended. Statement expense lines are
positive deductions; fact-table and journal amounts keep debit/credit signs.

## Reconciliation sequence

1. Confirm each entity is present and its local trial balance sums to zero.
2. Validate rates and scope, then translate every row using its specified basis.
3. Group intercompany rows by unordered entity pair and reference within the
   current scenario/period. Require exactly two reciprocal rows, either receivable
   and payable, or service revenue and service expense. Multiple references between
   the same entities are allowed. A split invoice must be resolved at source.
4. Require the translated pair sum to be exactly zero. Zero pairs are allowed;
   any nonzero difference, even below a cent, blocks the pack. No automatic
   tolerance, FX plug or suspense account is used. This is deliberately stricter
   than a production close with authorised rounding journals. If different rates
   cause a mismatch, the preparer must reconcile the underlying transaction and
   use appropriate approved source detail; do not alter rates just to force a match.
5. Reverse both rows through an auditable elimination journal. Remove each parent
   investment against the matching subsidiary's formation share capital, requiring
   an exact historical translated match. Keep subsidiary post-formation retained
   earnings in the group. Investment eliminations must each balance.
6. Compute each closing CTA as the sum of its translated pre-close trial balance.
   Because the local ledger was balanced, this residual reflects the different
   translation bases. Positive CTA is a credit equity reserve. OCI movement equals
   closing CTA minus the supplied opening CTA. It is not all of closing CTA.
7. Check group assets equal liabilities plus equity, intercompany and investment
   accounts are zero, and the CTA roll-forward reconciles. Only then export.

The reserve report uses positive equity amounts; the signed fact export uses
negative amounts for credit reserves and OCI. The position report shows both
opening retained earnings and current profit, and their subtotal called closing
retained earnings. Do not add all three rows together.

## Hand calculation for October 2026

The CAD parent holds investments of 11,000, 11,200 and 9,600, matching the original
translated capital of the US, EU and UK companies. Its share capital is 50,000.
The foreign entities' opening retained earnings translate to 2,200 + 1,400 + 800.
Their opening CTAs are 500 + 200 + 100.

| Entity | Net closing assets at closing rate | Capital plus opening retained earnings at historical rates | Current profit at average rate | Closing CTA |
| --- | ---: | ---: | ---: | ---: |
| US | 20,000 | 13,200 | 4,800 | 2,000 |
| EU | 16,200 | 12,600 | 2,700 | 900 |
| UK | 18,025 | 10,400 | 6,840 | 785 |

For the US, 16,200 cash + 1,200 receivable - 1,400 payable = 16,000 USD of net
assets; at 1.25 this is 20,000 CAD. Capital and opening retained earnings use
1.10; current income uses 1.20. CTA is 20,000 - 13,200 - 4,800 = 2,000 CAD.

The US/EU balance pair translates as 1,200 USD × 1.25 = 1,000 EUR × 1.50 = 1,500
CAD. The UK/US balance pair is 1,000 GBP × 1.75 = 1,400 USD × 1.25 = 1,750 CAD.
Each of the two service pairs translates to 1,800 CAD on both sides. Eliminations
remove 3,250 of receivables and payables, 3,600 of revenue and expenses, and 31,800
of investments and subsidiary capital. Every journal balances; group profit is
unchanged by these service eliminations.

External revenue is 1,200 + 14,400 + 13,500 + 12,600 = 41,700 CAD. External costs
are 500 + 9,600 + 9,000 + 7,560 = 26,660 CAD. Profit is 15,040. Closing CTA is
3,685; opening CTA is 800; current translation OCI is 2,885.
Group equity is 50,000 + 4,400 + 15,040 + 3,685 = 73,125 CAD, equal to group cash
once investments and reciprocal balances have been eliminated.

## Planning and review

`plan.csv` adds `scenario` and `period` to the same ledger columns. It only accepts
income and expense accounts. Every configured scenario/year must exist with all
group entities. Each group is independently translated and matched, so one year's
receivable, sale or reference cannot cancel another year's item. There is no plan
balance sheet or planned CTA. A plan is a financial forecast, not an IFRS statement.

The example starts from the actual period's income amounts as an **illustrative
annual planning baseline**, not an annualisation of the October close or a claim
about seasonality. Base grows all amounts by 10% per year. Downside reduces
external revenue and internal services by 5% per year while external costs rise
2%. Fixed budget rates isolate operating assumptions. For 2027, Base profit is
16,544 CAD; Downside profit is 39,615 - 27,193.20 = 12,421.80 CAD.

Full decimal precision is retained in CSV outputs and checks; apply display
rounding in a viewer. Independently rounded statement lines can have a visible
rounding difference. An approved production rounding policy is outside this model.

The CLI validates the actual close and all plans before exporting statements. On
failure it writes a blocking status, reconciliation failure and checklist to a
fresh folder, returns code 1, and emits no statements or fact table. It protects
existing output folders, including failed runs. On success the status remains
`REVIEW_REQUIRED`; the five manual approvals cannot be passed by arithmetic.
