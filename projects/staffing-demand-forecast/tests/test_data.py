import numpy as np
import pandas as pd
import pytest

from staffing_forecast.data import load_regions, load_tickets, synthetic_tickets, validate_tickets


def test_synthetic_is_reproducible_and_explicit(tickets):
    assert len(tickets) == 2190
    assert set(tickets.region_id) == {"AU", "CA", "UK"}
    pd.testing.assert_frame_equal(synthetic_tickets(), synthetic_tickets())
    assert not synthetic_tickets(seed=9).tickets.equals(synthetic_tickets().tickets)


@pytest.mark.parametrize(
    "case", ["duplicate", "missing_day", "negative", "infinity", "fraction", "null", "unknown_region", "missing_region"]
)
def test_bad_tickets_rejected(tickets, regions, case):
    df = tickets.copy()
    if case == "duplicate":
        df = pd.concat([df, df.iloc[[0]]])
    elif case == "missing_day":
        df = df.iloc[1:]
    elif case in {"negative", "infinity", "fraction", "null"}:
        df["tickets"] = df.tickets.astype(float)
        df.loc[0, "tickets"] = {"negative": -1, "infinity": np.inf, "fraction": 0.5, "null": np.nan}[case]
    elif case == "unknown_region":
        df.loc[0, "region_id"] = "UNKNOWN"
    elif case == "missing_region":
        df = df.query("region_id != 'CA'")
    with pytest.raises(ValueError):
        validate_tickets(df, regions)


def test_column_order_is_not_meaningful(tickets, regions):
    result = validate_tickets(tickets[["tickets", "region_id", "date"]], regions)
    assert list(result.columns) == ["date", "region_id", "tickets"]


@pytest.mark.parametrize(
    "column,value",
    [
        ("shrinkage", 1),
        ("shrinkage", -0.1),
        ("occupancy", 0),
        ("paid_hours", 0),
        ("handling_minutes", -1),
        ("available_headcount", 1.5),
        ("region_name", "=1+1"),
        ("occupancy", np.inf),
    ],
)
def test_bad_staffing_inputs_rejected(regions, tmp_path, column, value):
    df = regions.copy()
    if column == "available_headcount":
        df[column] = df[column].astype(float)
    df.loc[0, column] = value
    path = tmp_path / "regions.csv"
    df.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_regions(path)


def test_na_is_a_valid_region_identifier(regions, tickets, tmp_path):
    config = regions.replace({"AU": "NA", "Australia": "North America"})
    path = tmp_path / "regions.csv"
    config.to_csv(path, index=False)
    actual = load_regions(path)
    assert "NA" in set(actual.region_id)
    input_path = tmp_path / "tickets.csv"
    tickets.replace({"AU": "NA"}).to_csv(input_path, index=False)
    assert "NA" in set(load_tickets(input_path, actual).region_id)
