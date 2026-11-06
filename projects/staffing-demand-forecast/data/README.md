The default refresh generates synthetic daily support tickets in memory. There are 730 dates beginning January 1, 2024, with seed 42 and three fictional regions. No customer or employee records are included.

The generator in `src/staffing_forecast/data.py` combines regional volume, weekday patterns, a gradual trend, mild annual variation, Poisson noise and two short incidents. It is a controlled example for comparing models, not evidence of performance on a real support queue.

To bring another daily series, supply a CSV with exactly `date,region_id,tickets`. Dates use `YYYY-MM-DD`. Counts must be finite, nonnegative integers. Each region must have one row for every date over the same date range. Use an explicit zero for a day with no tickets. A missing row is rejected rather than silently treated as zero. The region IDs must match the staffing configuration.

At least 476 daily observations are needed with the default backtest settings. Keep private source data outside this public repository, and direct its exports to an ignored output folder.
