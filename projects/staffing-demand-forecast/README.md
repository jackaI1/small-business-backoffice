# staffing-demand-forecast

I built a ticket-demand and staffing planner to learn how the underlying idea works. This is a learning project.

## Run it yourself

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python and the project's dependencies. From a terminal:

```sh
uv sync --frozen --extra dev
uv run staffing-refresh --synthetic --output outputs/latest
```

Open `outputs/latest/staffing_plan.xlsx`, or point the Power BI project's `SourceFolder` parameter at that folder and refresh. To use another daily dataset:

```sh
uv run staffing-refresh --input /path/to/tickets.csv --regions config/regions.csv --output outputs/latest
```

The CSV needs `date,region_id,tickets`, with one row per region per day. Missing dates are rejected. A day with no tickets must have an explicit zero. The [data guide](data/README.md) describes the format and minimum history. Keep source files outside the output folder, which is replaced after a successful refresh.

## What the example found

| Region | Selected model | Selected WAPE | Repeat last day | Repeat last week |
| --- | --- | ---: | ---: | ---: |
| Australia | Weekly seasonal model with a slowing trend | 6.99% | 27.58% | 9.03% |
| Canada | Weekly seasonal model | 5.74% | 31.37% | 7.87% |
| United Kingdom | Weekly seasonal model | 6.67% | 29.76% | 8.26% |
| All regions, weighted by tickets | Regional selections | **6.34%** | **29.94%** | **8.28%** |

These are reproducible synthetic results, not a promise about a real queue. The [full error table](outputs/sample/fact_metrics.csv) also includes average error in tickets, larger-error sensitivity and overprediction or underprediction. A model selected earlier does not have to be the best model on every later period.

## From tickets to people

I add a buffer based on earlier underpredictions to the future ticket estimate. Then I multiply by minutes per ticket and divide by the useful ticket-handling time available from one person. The plan allows for breaks, training and other unavailable time, called shrinkage, and for the share of remaining time spent handling tickets, called occupancy. It rounds people up separately for each day and region.

The supplied assumptions give peak daily needs of 11 people in Australia, 17 in Canada and 16 in the United Kingdom. The workbook shows the calculation step by step. I distinguish a day's headcount from **agent shifts**, the sum of daily staffing counts across the planning period. This estimates workload coverage. It does not assign individual shifts or guarantee response times.

## How I put it together

`src/staffing_forecast/` validates inputs, fits statsmodels seasonal exponential-smoothing models, runs the backtest and writes the exports. A rolling-origin backtest repeatedly fits on the past and predicts the next period. I compare two seasonal models with both a last-day and a last-week baseline, then refit the selected regional models on all available history.

`outputs/sample/` contains six tidy tables, an Excel workbook and a manifest recording the settings, selected models and source fingerprint. Fact tables hold observations and predictions. Dimension tables hold shared dates, regions and model names. The [design notes](docs/design.md) explain their grain and the separation between model selection and evaluation.

`powerbi/Staffing.pbip` is an editable Power BI project with three report pages, six tables, eight relationships and 17 DAX measures. DAX is Power BI's calculation language. The pages compare actual and predicted tickets, show daily staffing gaps, and compare backtest errors by region. [The report specification](docs/powerbi.md) covers every page and measure. I validate the files and model metadata automatically. I have not verified Desktop rendering or executed DAX in a live Power BI engine on this Mac.

## Tests and limits

There are 5 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



Generated output omitted: outputs/ (generated output).

The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

Retained project workflows: `staffing-demand-forecast-refresh.yml`. Their commands use this folder and their triggers use its paths.
