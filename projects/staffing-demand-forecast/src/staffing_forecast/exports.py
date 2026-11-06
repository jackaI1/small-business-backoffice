"""One row per region/day. Keep repeated backtests out of the report fact."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from staffing_forecast.forecast import Settings, metric_table, predict, rolling_backtest, select_models


def headcount(volume, handling_minutes, paid_hours, shrinkage, occupancy):
    people = volume * handling_minutes / (paid_hours * 60 * (1 - shrinkage) * occupancy)
    # Match Excel/DAX precision at exact capacity boundaries without losing tiny positive workloads.
    return max(int(volume > 0), math.ceil(round(people, 10)))


def build_tables(tickets: pd.DataFrame, regions: pd.DataFrame, settings: Settings) -> tuple[dict, dict]:
    backtest = rolling_backtest(tickets, settings)
    selected = select_models(backtest)
    metrics = metric_table(backtest, selected)
    daily_rows = []
    for region, group in tickets.groupby("region_id", sort=True):
        group = group.sort_values("date")
        model = selected[region]
        config = regions.set_index("region_id").loc[region]
        calibration = backtest.loc[
            (backtest.region_id == region) & (backtest.model == model) & (backtest.phase == "calibration")
        ]
        buffer = max(0.0, float(np.quantile(calibration.actual - calibration.forecast, 0.90)))
        evaluation = backtest.loc[
            (backtest.region_id == region) & (backtest.model == model) & (backtest.phase == "evaluation")
        ].set_index("date")
        for row in group.itertuples(index=False):
            tested = row.date in evaluation.index
            forecast = float(evaluation.loc[row.date, "forecast"]) if tested else None
            daily_rows.append(
                {
                    "date": row.date,
                    "region_id": region,
                    "actual": row.tickets,
                    "forecast": forecast,
                    "period": "evaluation" if tested else "history",
                    "model": model,
                    "origin_date": evaluation.loc[row.date, "origin_date"] if tested else None,
                    "absolute_error": abs(forecast - row.tickets) if tested else None,
                    "matched_actual": row.tickets if tested else None,
                    "planning_volume": None,
                    "required_headcount": None,
                    "headcount_gap": None,
                }
            )
        forecast = predict(group.tickets, settings.horizon, model)
        future_dates = pd.date_range(group.date.max() + pd.Timedelta(days=1), periods=settings.horizon, freq="D")
        for date, value in zip(future_dates, forecast, strict=True):
            planned = float(value + buffer)
            required = headcount(
                planned, config.handling_minutes, config.paid_hours, config.shrinkage, config.occupancy
            )
            daily_rows.append(
                {
                    "date": date,
                    "region_id": region,
                    "actual": None,
                    "forecast": float(value),
                    "period": "future",
                    "model": model,
                    "origin_date": group.date.max(),
                    "absolute_error": None,
                    "matched_actual": None,
                    "planning_volume": planned,
                    "required_headcount": required,
                    "headcount_gap": required - config.available_headcount,
                }
            )
    demand = pd.DataFrame(daily_rows).sort_values(["date", "region_id"]).reset_index(drop=True)
    dates = pd.DataFrame({"date": pd.date_range(demand.date.min(), demand.date.max(), freq="D")})
    dates["year"] = dates.date.dt.year
    dates["month"] = dates.date.dt.month
    dates["month_name"] = dates.date.dt.strftime("%b")
    dates["weekday_number"] = dates.date.dt.dayofweek + 1
    dates["weekday"] = dates.date.dt.day_name()
    dates["week_start"] = dates.date - pd.to_timedelta(dates.weekday_number - 1, unit="D")
    dates["is_future"] = (dates.date > tickets.date.max()).astype(int)
    models = pd.DataFrame({"model": sorted(backtest.model.unique())})
    tables = {
        "fact_demand": demand,
        "fact_backtest": backtest,
        "fact_metrics": metrics,
        "dim_date": dates,
        "dim_region": regions.copy(),
        "dim_model": models,
    }
    evaluation = backtest.loc[backtest.phase == "evaluation"].copy()
    chosen = evaluation.loc[evaluation.apply(lambda r: selected[r.region_id] == r.model, axis=1)]
    baseline = evaluation.loc[evaluation.model == "naive"]
    seasonal = evaluation.loc[evaluation.model == "seasonal_naive"]
    manifest = {
        "schema_version": 1,
        "history_start": str(tickets.date.min().date()),
        "history_end": str(tickets.date.max().date()),
        "settings": vars(settings),
        "selected_models": selected,
        "source_sha256": hashlib.sha256(tickets.to_csv(index=False, date_format="%Y-%m-%d").encode()).hexdigest(),
        "evaluation_wape": float(chosen.absolute_error.sum() / chosen.actual.sum()) if chosen.actual.sum() else None,
        "naive_wape": float(baseline.absolute_error.sum() / baseline.actual.sum()) if baseline.actual.sum() else None,
        "seasonal_naive_wape": float(seasonal.absolute_error.sum() / seasonal.actual.sum())
        if seasonal.actual.sum()
        else None,
        "rows": {name: len(table) for name, table in tables.items()},
    }
    validate_tables(tables)
    return tables, manifest


def validate_tables(tables: dict):
    for name, keys in [
        ("fact_demand", ["date", "region_id"]),
        ("dim_date", ["date"]),
        ("dim_region", ["region_id"]),
        ("dim_model", ["model"]),
        ("fact_backtest", ["region_id", "origin_date", "date", "model"]),
        ("fact_metrics", ["region_id", "phase", "model"]),
    ]:
        if tables[name].duplicated(keys).any() or tables[name][keys].isna().any().any():
            raise ValueError(f"Invalid keys in {name}")
    for name in ("fact_demand", "fact_backtest", "fact_metrics"):
        table = tables[name]
        for key, dimension in [("region_id", "dim_region"), ("model", "dim_model"), ("date", "dim_date")]:
            if key in table and not table[key].isin(tables[dimension][key]).all():
                raise ValueError(f"Broken {key} relationship in {name}")
        if np.isinf(table.select_dtypes(include="number").to_numpy()).any():
            raise ValueError(f"Nonfinite numeric export: {name}")


def write_tables(tables: dict, manifest: dict, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(output / f"{name}.csv", index=False, date_format="%Y-%m-%d", float_format="%.8f")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
