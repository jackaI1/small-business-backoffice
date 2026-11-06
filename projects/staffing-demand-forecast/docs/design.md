# Forecast and staffing design

I use daily ticket counts to estimate daily regional workload. The default source is deterministic synthetic data: 730 days from 2024-01-01 through 2025-12-30, three fictional regional queues, seed 42. Weekday effects, a gradual trend, annual variation, random counts and two short incidents make a useful controlled comparison. The output is a 28-day plan, not an individual roster or queueing simulation.

## Forecast evaluation

I considered a spreadsheet-only moving average, a seasonal statistical pipeline and a hosted forecasting service. The statistical pipeline keeps the model comparison reproducible, supports weekly patterns and runs without credentials. Excel remains useful for reviewing assumptions, while Power BI consumes the same exported data.

The candidate models are:

| Identifier | Prediction method |
| --- | --- |
| `naive` | Repeat the last observed day for every future day |
| `seasonal_naive` | Repeat the most recent seven days |
| `ets_seasonal` | Additive weekly exponential smoothing with an estimated level and seven seasonal effects |
| `ets_damped` | The same weekly pattern plus an additive trend that slows over the forecast horizon |

The last two use [statsmodels Holt-Winters ExponentialSmoothing](https://www.statsmodels.org/stable/generated/statsmodels.tsa.holtwinters.ExponentialSmoothing.html). Negative predictions are clipped to zero. Constant and all-zero series receive constant forecasts. An optimizer failure stops publication rather than silently replacing the model.

With default settings, the first fit uses 338 days. Six 28-day calibration folds choose the lowest mean absolute error per region. A further eight nonoverlapping 28-day evaluation folds measure performance. Each fit expands its training window and sees only dates before its origin. Evaluation targets become training history in later folds, as they would during real refreshes, but cannot change the regional model selection.

MAE is mean absolute error in tickets. RMSE is the square root of mean squared error, making larger mistakes matter more. WAPE is summed absolute error divided by summed actuals. Bias is mean forecast minus actual. WAPE is unavailable when actual tickets total zero. Aggregate WAPE is calculated from errors and volumes, not by averaging regional percentages.

The minimum input length is `min_train + (calibration_folds + evaluation_folds) * fold_horizon`, or 476 dates by default. The CLI's `--horizon` changes both the future horizon and the length of each backtest period. The Python `Settings` interface exposes the other settings. Recheck evaluation quality when changing the horizon.

## Staffing calculation

For each region, I calculate the 90th percentile of `actual - forecast` on calibration dates for its selected model, floored at zero. This additive buffer is an empirical planning allowance, not a calibrated confidence interval or a 90% service guarantee. Evaluation errors never set it. Its size is visible as planning volume minus forecast volume in the daily fact table.

```text
planning tickets = forecast tickets + earlier-error buffer
work hours = planning tickets * handling minutes / 60
useful hours per person = paid hours * (1 - shrinkage) * occupancy
required people = ceiling(work hours / useful hours per person)
headcount gap = required people - available people
```

Rounding happens at region/day grain before adding across regions. Python, Excel and DAX first round fractional people to 10 decimal places to remove floating-point noise at exact capacity boundaries, then round up to whole people. A positive workload always requires at least one person, even below that precision. Required people for several days is a count of agent shifts, not simultaneous employees. Peak headcount is the maximum daily total in the selected period. Changing assumptions in Excel recalculates its formulas. Power BI derives headcount using DAX and the imported regional assumptions. Change the configuration and rerun the pipeline to keep both outputs aligned.

This model omits arrival times within a day, backlog carryover, leave rosters, cross-region pooling, skill routing and service-level targets. It fits weekly seasonality, not annual seasonality or explicit incident regressors. Validate with representative operational data before using it for staffing decisions.

## Export contracts

| Table | Unique row grain | Purpose |
| --- | --- | --- |
| `fact_demand` | date, region | Historical actuals, selected-model evaluation predictions and future forecasts |
| `fact_backtest` | region, origin date, target date, model | Every candidate's prediction, fold, phase, actual and absolute error |
| `fact_metrics` | region, phase, model | Regional accuracy summary and selected-model flag |
| `dim_date` | date | Common continuous calendar, weekday order, Monday week start and future flag |
| `dim_region` | region ID | Region names, minutes per ticket, paid hours, shrinkage, occupancy and available people |
| `dim_model` | model | Candidate identifiers |

`fact_demand.period` is `history`, `evaluation` or `future`. Historical dates before evaluation have no forecast. Evaluation dates contain one selected-model prediction per region/day. Future dates have no actuals, errors or matched actuals. Their staffing fields are populated. This prevents comparing a future prediction with an invented zero actual or counting every candidate as additional demand.

The report uses eight single-direction many-to-one relationships from facts to dimensions. `fact_metrics` has no date relationship because its rows summarize a complete phase, rather than a specific date. `origin_date` is audit information, not an active date relationship. CSVs use ISO dates, UTF-8, eight decimal places and empty fields for nulls. The manifest records row counts, settings, selected models, weighted evaluation metrics and a SHA-256 fingerprint of normalized input.

## Refresh behavior

The CLI validates complete common calendars, unique keys, known regions, finite integer counts and valid capacity inputs before fitting. It writes into a temporary sibling directory and moves completed exports into place only after Excel succeeds. Caught publication failures restore the previous folder. Temporary staging is removed. The command rejects a nonempty output without a manifest and rejects source files inside the output folder. Do not run two local refreshes into the same folder at once. A hard process kill during the rename window can interrupt publication; this is not a transactional database.

The weekly GitHub workflow serializes its own refresh jobs and uploads an artifact. It never commits generated operational inputs or updates Power BI service credentials. To schedule a private dataset, run the same command on a machine with access to that CSV, store it outside the public repository, and point Power BI at the completed output folder. Desktop import needs no service account. Service refresh requires a separate gateway/service setup, which this repository does not configure.
