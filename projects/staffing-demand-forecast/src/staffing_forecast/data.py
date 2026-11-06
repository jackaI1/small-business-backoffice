"""A deliberately synthetic, reproducible workload and strict CSV contracts."""

from pathlib import Path

import numpy as np
import pandas as pd

REGION_COLUMNS = [
    "region_id",
    "region_name",
    "handling_minutes",
    "paid_hours",
    "shrinkage",
    "occupancy",
    "available_headcount",
]


def synthetic_tickets(days: int = 730, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    t = np.arange(days)
    rows = []
    for region, base, slope, weekday in [
        ("CA", 220, 0.10, [1.28, 1.18, 1.10, 1.06, 0.94, 0.56, 0.50]),
        ("UK", 160, 0.07, [1.35, 1.16, 1.07, 1.03, 0.91, 0.59, 0.49]),
        ("AU", 125, 0.05, [1.24, 1.17, 1.09, 1.04, 0.97, 0.60, 0.53]),
    ]:
        # Slow annual variation and two short incidents are intentionally unmodelled.
        annual = 1 + 0.07 * np.sin(2 * np.pi * t / 365.25)
        mean = (base + slope * t) * annual * np.take(weekday, dates.dayofweek)
        mean = mean + np.where(((t >= 420) & (t < 424)) | ((t >= 650) & (t < 653)), base * 0.35, 0)
        tickets = rng.poisson(mean)
        rows.extend(zip(dates, [region] * days, tickets, strict=True))
    return (
        pd.DataFrame(rows, columns=["date", "region_id", "tickets"])
        .sort_values(["date", "region_id"])
        .reset_index(drop=True)
    )


def load_regions(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"region_id": str}, keep_default_na=False)
    if set(df.columns) != set(REGION_COLUMNS) or df.empty:
        raise ValueError("Region config must contain the documented columns and at least one region")
    if df.isna().any().any() or df.region_id.duplicated().any():
        raise ValueError("Region config has missing values or duplicate region IDs")
    if not df.region_id.str.fullmatch(r"[A-Z0-9_]{1,24}").all():
        raise ValueError("Region IDs must be short uppercase identifiers")
    if not df.region_name.map(lambda s: isinstance(s, str) and bool(s.strip()) and s[0] not in "=+-@").all():
        raise ValueError("Region names must be plain text, not spreadsheet formulas")
    numeric = df[REGION_COLUMNS[2:]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Region assumptions must be finite")
    df[numeric.columns] = numeric
    if (df.handling_minutes <= 0).any() or (df.paid_hours <= 0).any():
        raise ValueError("Handling minutes and paid hours must be positive")
    if ((df.shrinkage < 0) | (df.shrinkage >= 1)).any() or ((df.occupancy <= 0) | (df.occupancy > 1)).any():
        raise ValueError("Shrinkage must be [0,1); occupancy must be (0,1]")
    if (df.available_headcount < 0).any() or (df.available_headcount % 1 != 0).any():
        raise ValueError("Available headcount must be a nonnegative integer")
    return df[REGION_COLUMNS].sort_values("region_id").reset_index(drop=True)


def validate_tickets(df: pd.DataFrame, regions: pd.DataFrame) -> pd.DataFrame:
    if set(df.columns) != {"date", "region_id", "tickets"} or df.empty:
        raise ValueError("Tickets require date, region_id, tickets columns")
    df = df.copy()
    df["date"] = pd.to_datetime(df.date, format="%Y-%m-%d", errors="raise")
    if df.isna().any().any() or df.duplicated(["date", "region_id"]).any():
        raise ValueError("Tickets contain missing values or duplicate date/region keys")
    if not (df.date == df.date.dt.normalize()).all():
        raise ValueError("Ticket dates must be daily, without times")
    df["tickets"] = pd.to_numeric(df.tickets, errors="raise")
    if not np.isfinite(df.tickets).all() or (df.tickets < 0).any() or (df.tickets % 1 != 0).any():
        raise ValueError("Ticket volumes must be finite nonnegative integers")
    if set(df.region_id) != set(regions.region_id):
        raise ValueError("Ticket regions must exactly match region config")
    expected = pd.date_range(df.date.min(), df.date.max(), freq="D")
    for _, group in df.groupby("region_id"):
        if not group.sort_values("date").date.reset_index(drop=True).equals(pd.Series(expected)):
            raise ValueError("Every region needs a complete common calendar; supply explicit zeroes for no tickets")
    return df[["date", "region_id", "tickets"]].sort_values(["region_id", "date"]).reset_index(drop=True)


def load_tickets(path: str | Path, regions: pd.DataFrame) -> pd.DataFrame:
    return validate_tickets(pd.read_csv(path, dtype={"region_id": str}, keep_default_na=False), regions)
