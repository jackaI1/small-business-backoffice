import shutil
from pathlib import Path

import pytest

from cashforecast.inputs import load_csv
from cashforecast.models import money


@pytest.fixture
def inputs(tmp_path):
    source = Path(__file__).resolve().parents[1] / "data/synthetic"
    shutil.copytree(source, tmp_path / "csv")
    return tmp_path / "csv"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1.001", "1000000000000"])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        money(value)


@pytest.mark.parametrize(
    "file,old,new,message",
    [
        ("bank.csv", "B002,", "B001,", "duplicate id"),
        ("bank.csv", "12000.00,CAD", "12000.00,USD", "currency"),
        ("bank.csv", "2026-10-02", "2026-07-31", "opening"),
        ("bank.csv", "operating-cad", "missing-account", "unknown account"),
        ("bank.csv", "id,account", "wrong,account", "expected columns"),
        ("bank.csv", "INV-100", " INV-100", "whitespace"),
        ("fx.csv", "1.375000", "NaN", "finite"),
        ("fx.csv", "1.375000", "0.000000", "positive"),
        ("fx.csv", "1.000000", "1.010000", "CAD must equal"),
        ("expected.csv", "B001", "missing-bank", "settlement"),
    ],
)
def test_bad_inputs_fail_before_storage(inputs, file, old, new, message):
    path = inputs / file
    path.write_text(path.read_text().replace(old, new, 1))
    with pytest.raises(ValueError, match=message):
        load_csv(inputs)


def test_same_bytes_same_dataset_and_changed_file_new_snapshot(inputs):
    first = load_csv(inputs)
    assert load_csv(inputs).id == first.id
    path = inputs / "bank.csv"
    path.write_text(path.read_text().replace("BANK-FEE", "BANK-SERVICE-FEE"))
    assert load_csv(inputs).id != first.id


def test_duplicate_fx_key_rejected(inputs):
    path = inputs / "fx.csv"
    path.write_text(path.read_text() + "USD,2026-10-31,1.375000\n")
    with pytest.raises(ValueError, match="unique"):
        load_csv(inputs)
