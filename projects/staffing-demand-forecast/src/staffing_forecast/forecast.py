"""Expanding-window evaluation with a separate, earlier model-selection window."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

MODELS = ("naive", "seasonal_naive", "ets_seasonal", "ets_damped")


@dataclass(frozen=True)
class Settings:
    horizon: int = 28
    fold_horizon: int = 28
    calibration_folds: int = 6
    evaluation_folds: int = 8
    min_train: int = 84

    def __post_init__(self):
        for value in vars(self).values():
            if type(value) is not int or value <= 0:
                raise ValueError("Forecast settings must be positive integers")
        if self.min_train < 14:
            raise ValueError("At least two complete weeks are needed")


def predict(train, horizon: int, model: str) -> np.ndarray:
    y = np.asarray(train, dtype=float)
    if horizon <= 0 or len(y) < 14 or not np.isfinite(y).all() or (y < 0).any():
        raise ValueError("Forecast needs finite nonnegative history (14+ days) and a positive horizon")
    if model == "naive":
        result = np.repeat(y[-1], horizon)
    elif model == "seasonal_naive":
        result = np.resize(y[-7:], horizon)
    elif model in ("ets_seasonal", "ets_damped"):
        if np.ptp(y) == 0:
            return np.repeat(y[-1], horizon)
        fit = ExponentialSmoothing(
            y,
            trend="add" if model == "ets_damped" else None,
            damped_trend=model == "ets_damped",
            seasonal="add",
            seasonal_periods=7,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
        if not fit.mle_retvals["success"]:
            raise RuntimeError(f"{model} optimizer did not converge; refresh not published")
        result = np.asarray(fit.forecast(horizon))
    else:
        raise ValueError(f"Unknown model: {model}")
    if not np.isfinite(result).all():
        raise RuntimeError("Forecast returned nonfinite values")
    return np.maximum(result, 0)


def score(actual, forecast) -> dict:
    actual, forecast = np.asarray(actual, dtype=float), np.asarray(forecast, dtype=float)
    error = forecast - actual
    denominator = actual.sum()
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "wape": float(np.abs(error).sum() / denominator) if denominator else None,
        "bias": float(error.mean()),
        "n": len(actual),
    }


def rolling_backtest(tickets: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    folds = settings.calibration_folds + settings.evaluation_folds
    rows = []
    for region, group in tickets.groupby("region_id", sort=True):
        group = group.sort_values("date").reset_index(drop=True)
        first_origin = len(group) - folds * settings.fold_horizon
        if first_origin < settings.min_train:
            raise ValueError(f"{region}: need {settings.min_train + folds * settings.fold_horizon} daily observations")
        for fold in range(folds):
            split = first_origin + fold * settings.fold_horizon
            train = group.tickets.iloc[:split].to_numpy()
            test = group.iloc[split : split + settings.fold_horizon]
            phase = "calibration" if fold < settings.calibration_folds else "evaluation"
            for model in MODELS:
                forecasts = predict(train, len(test), model)
                for lead, ((date, _, actual), forecast) in enumerate(
                    zip(test.itertuples(index=False, name=None), forecasts, strict=True), 1
                ):
                    rows.append(
                        (region, fold + 1, phase, group.date.iloc[split - 1], date, lead, model, actual, forecast)
                    )
    result = pd.DataFrame(
        rows, columns=["region_id", "fold", "phase", "origin_date", "date", "lead_days", "model", "actual", "forecast"]
    )
    result["absolute_error"] = (result.forecast - result.actual).abs()
    return result


def select_models(backtest: pd.DataFrame) -> dict[str, str]:
    # Selection never sees evaluation targets. MAE works even for all-zero regions.
    calibration = backtest.loc[backtest.phase == "calibration"]
    errors = calibration.groupby(["region_id", "model"]).absolute_error.mean().reset_index()
    best = errors.sort_values(["region_id", "absolute_error", "model"]).drop_duplicates("region_id")
    return dict(zip(best.region_id, best.model, strict=True))


def metric_table(backtest: pd.DataFrame, selected: dict) -> pd.DataFrame:
    rows = []
    for (region, phase, model), group in backtest.groupby(["region_id", "phase", "model"], sort=True):
        rows.append(
            {
                "region_id": region,
                "phase": phase,
                "model": model,
                "selected": int(selected[region] == model),
                **score(group.actual, group.forecast),
            }
        )
    return pd.DataFrame(rows)
