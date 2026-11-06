import json
from pathlib import Path

import pytest

from ifrs_consolidation.cli import read_csv
from ifrs_consolidation.model import Entry

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "three_subs"


@pytest.fixture
def config():
    return json.loads((EXAMPLE / "config.json").read_text())


@pytest.fixture
def entries():
    return [Entry.from_row(row) for row in read_csv(EXAMPLE / "ledger.csv")]


@pytest.fixture
def plan():
    return read_csv(EXAMPLE / "plan.csv")
