from pathlib import Path

import pytest

from staffing_forecast.data import load_regions, synthetic_tickets, validate_tickets
from staffing_forecast.exports import build_tables
from staffing_forecast.forecast import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def regions():
    return load_regions(ROOT / "config/regions.csv")


@pytest.fixture(scope="session")
def tickets(regions):
    return validate_tickets(synthetic_tickets(), regions)


@pytest.fixture(scope="session")
def built(tickets, regions):
    return build_tables(tickets, regions, Settings())
