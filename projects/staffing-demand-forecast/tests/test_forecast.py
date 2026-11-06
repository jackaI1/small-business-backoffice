import numpy as np
import pytest

from staffing_forecast.forecast import MODELS, Settings, predict, rolling_backtest, score, select_models


@pytest.mark.parametrize("model", MODELS)
def test_forecasts_are_finite_nonnegative_and_cover_horizon(model):
    history = 30 + np.tile([5, 7, 4, 3, 8, 0, 0], 20) + np.arange(140) * 0.1
    result = predict(history, 28, model)
    assert result.shape == (28,)
    assert np.isfinite(result).all() and (result >= 0).all()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("level", [0, 20])
def test_constant_or_zero_history(model, level):
    np.testing.assert_allclose(predict([level] * 84, 28, model), level)


def test_baselines_are_last_day_and_last_week():
    np.testing.assert_array_equal(predict(np.arange(14), 10, "naive"), [13] * 10)
    np.testing.assert_array_equal(predict(np.arange(14), 10, "seasonal_naive"), [7, 8, 9, 10, 11, 12, 13, 7, 8, 9])


def test_error_metrics_and_zero_denominator():
    result = score([10, 20, 0], [12, 18, 3])
    assert result["mae"] == pytest.approx(7 / 3)
    assert result["wape"] == pytest.approx(7 / 30)
    assert result["bias"] == 1
    assert result["rmse"] == pytest.approx(np.sqrt(17 / 3))
    assert score([0, 0], [0, 1])["wape"] is None


def test_rolling_origins_precede_targets_and_never_overlap(built):
    backtest = built[0]["fact_backtest"]
    assert (backtest.origin_date < backtest.date).all()
    assert (backtest.date - backtest.origin_date).dt.days.equals(backtest.lead_days)
    assert backtest.lead_days.between(1, 28).all()
    for _, group in backtest.groupby(["region_id", "model"]):
        assert not group.date.duplicated().any()
        assert group.query("phase == 'calibration'").date.max() < group.query("phase == 'evaluation'").date.min()
        assert len(group.query("phase == 'evaluation'")) == 224


def test_selection_ignores_evaluation_targets(built):
    backtest = built[0]["fact_backtest"].copy()
    selected = select_models(backtest)
    backtest.loc[backtest.phase == "evaluation", ["actual", "forecast", "absolute_error"]] = 999999
    assert select_models(backtest) == selected


def test_future_changes_cannot_change_earlier_forecasts(tickets):
    # Small but real model refits, not mocks: alter only the final test window.
    small = tickets.query("region_id == 'CA'").tail(140).copy()
    settings = Settings(fold_horizon=7, calibration_folds=2, evaluation_folds=2, min_train=28)
    first = rolling_backtest(small, settings)
    cutoff = small.date.max() - __import__("pandas").Timedelta(days=6)
    small.loc[small.date >= cutoff, "tickets"] *= 10
    second = rolling_backtest(small, settings)
    np.testing.assert_allclose(first.forecast, second.forecast)


def test_insufficient_history_rejected(tickets):
    with pytest.raises(ValueError, match="need"):
        rolling_backtest(tickets.groupby("region_id").head(50), Settings())


@pytest.mark.parametrize("kwargs", [{"horizon": 0}, {"fold_horizon": -1}, {"min_train": 7}, {"horizon": 1.5}])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_seeded_demo_beats_both_baselines_on_independent_dates(built):
    tables, manifest = built
    assert manifest["evaluation_wape"] < manifest["seasonal_naive_wape"] < manifest["naive_wape"]
    for region, group in tables["fact_metrics"].query("phase == 'evaluation'").groupby("region_id"):
        assert group.query("selected == 1").mae.iloc[0] < group.query("model == 'naive'").mae.iloc[0], region
