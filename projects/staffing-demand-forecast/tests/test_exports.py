import json
from pathlib import Path

import formulas
import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from staffing_forecast.cli import refresh
from staffing_forecast.excel import write_workbook
from staffing_forecast.exports import headcount, validate_tables, write_tables

ROOT = Path(__file__).resolve().parents[1]


def test_fact_grain_future_nulls_and_headcount_reconcile(built, regions):
    tables, _ = built
    demand = tables["fact_demand"]
    assert len(demand) == 2274
    assert not demand.duplicated(["date", "region_id"]).any()
    future = demand.query("period == 'future'")
    assert len(future) == 84
    assert future.actual.isna().all() and future.matched_actual.isna().all()
    assert (future.planning_volume >= future.forecast).all()
    config = regions.set_index("region_id")
    for row in future.itertuples():
        r = config.loc[row.region_id]
        expected = np.ceil(
            row.planning_volume * r.handling_minutes / (60 * r.paid_hours * (1 - r.shrinkage) * r.occupancy)
        )
        assert expected == row.required_headcount
        assert row.headcount_gap == expected - r.available_headcount
    evaluation = demand.query("period == 'evaluation'")
    assert len(evaluation) == 672
    np.testing.assert_allclose(evaluation.absolute_error, abs(evaluation.forecast - evaluation.actual))


def test_headcount_rounds_per_day_and_region():
    assert headcount(0, 12, 8, 0.3, 0.85) == 0
    assert headcount(1, 12, 8, 0.3, 0.85) == 1
    assert headcount(100, 12, 8, 0.3, 0.85) == 5
    assert headcount(100, 12, 8, 0.5, 0.85) > headcount(100, 12, 8, 0.3, 0.85)


@pytest.mark.parametrize(
    "volume,minutes,hours,shrinkage,occupancy,expected",
    [(1512, 5, 8, 0.1, 0.7, 25), (918, 5, 7.5, 0.2, 0.85, 15), (1512.000001, 5, 8, 0.1, 0.7, 26)],
)
def test_headcount_does_not_add_people_for_floating_point_noise(volume, minutes, hours, shrinkage, occupancy, expected):
    assert headcount(volume, minutes, hours, shrinkage, occupancy) == expected


def test_positive_tiny_workload_still_needs_one_person():
    assert headcount(1e-12, 5, 8, 0.1, 0.7) == 1


@pytest.mark.parametrize(
    "volume,hours,shrinkage,occupancy,expected",
    [(1512, 8, 0.1, 0.7, 25), (918, 7.5, 0.2, 0.85, 15), (918.000001, 7.5, 0.2, 0.85, 16), (1e-12, 8, 0.1, 0.7, 1)],
)
def test_saved_excel_headcount_agrees_at_capacity_boundaries(
    built, tmp_path, volume, hours, shrinkage, occupancy, expected
):
    path = tmp_path / "boundary.xlsx"
    write_workbook(built[0], path)
    wb = load_workbook(path)
    wb["Daily plan"]["D2"] = volume
    for column, value in [("B", 5), ("C", hours), ("D", shrinkage), ("E", occupancy)]:
        wb["Assumptions"][f"{column}2"] = value
    wb.save(path)
    result = formulas.ExcelModel().loads(str(path)).finish().calculate()
    key = next(k for k in result if "DAILY PLAN" in k and k.endswith("'!G2"))
    assert float(result[key].value[0, 0]) == expected


def test_export_csv_roundtrip_and_manifest(built, tmp_path):
    tables, manifest = built
    write_tables(tables, manifest, tmp_path)
    for name, source in tables.items():
        actual = pd.read_csv(tmp_path / f"{name}.csv")
        assert list(actual.columns) == list(source.columns)
        assert len(actual) == len(source)
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    assert len(manifest["source_sha256"]) == 64
    selected = tables["fact_demand"].query("period == 'evaluation'")
    assert manifest["evaluation_wape"] == pytest.approx(selected.absolute_error.sum() / selected.actual.sum())


@pytest.mark.parametrize("case", ["duplicate", "orphan"])
def test_export_key_guards(built, case):
    tables = {name: df.copy() for name, df in built[0].items()}
    if case == "duplicate":
        tables["fact_demand"] = pd.concat([tables["fact_demand"], tables["fact_demand"].iloc[[0]]])
    else:
        tables["fact_demand"].loc[0, "region_id"] = "MISSING"
    with pytest.raises(ValueError):
        validate_tables(tables)


def test_excel_formulas_evaluate_and_react_to_input(built, tmp_path):
    path = tmp_path / "plan.xlsx"
    write_workbook(built[0], path)
    wb = load_workbook(path)
    assert wb.sheetnames == ["Staffing plan", "Assumptions", "Daily plan", "Forecast accuracy"]
    assert len(wb["Assumptions"].data_validations.dataValidation) == 5
    assert len(wb["Staffing plan"]._charts) == 1
    daily = wb["Daily plan"]
    assert daily.max_row == 85
    # Evaluate the actual saved formulas with an independent formula engine.
    model = formulas.ExcelModel().loads(str(path)).finish()
    result = model.calculate()
    key = next(k for k in result if "DAILY PLAN" in k and k.endswith("'!G2"))
    assert (
        float(result[key].value[0, 0]) == built[0]["fact_demand"].query("period == 'future'").required_headcount.iloc[0]
    )
    first_region = daily["B2"].value
    config_row = next(r for r in range(2, 5) if wb["Assumptions"].cell(r, 1).value == first_region)
    wb["Assumptions"].cell(config_row, 2).value *= 2
    wb.save(path)
    changed = formulas.ExcelModel().loads(str(path)).finish().calculate()
    assert float(changed[key].value[0, 0]) > float(result[key].value[0, 0])
    for value in result.values():
        assert not any(str(x).startswith(("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!")) for x in value.value.flat)


def test_refresh_preserves_previous_output_when_excel_fails(built, tmp_path, monkeypatch):
    output = tmp_path / "published"
    write_tables(*built, output)
    before = (output / "manifest.json").read_bytes()
    monkeypatch.setattr("staffing_forecast.cli.build_tables", lambda *args: built)

    def fail(*args):
        raise RuntimeError("fixture export failure")

    monkeypatch.setattr("staffing_forecast.cli.write_workbook", fail)
    with pytest.raises(RuntimeError, match="fixture"):
        refresh(output, ROOT / "config/regions.csv")
    assert (output / "manifest.json").read_bytes() == before
    assert not list(tmp_path.glob(".staffing-*"))


def test_refresh_refuses_unowned_directory(tmp_path):
    (tmp_path / "owner.txt").write_text("keep this")
    with pytest.raises(ValueError, match="Output"):
        refresh(tmp_path, ROOT / "config/regions.csv")
    assert (tmp_path / "owner.txt").read_text() == "keep this"


@pytest.mark.parametrize("source", ["tickets", "regions"])
def test_refresh_refuses_to_replace_source_files(built, tmp_path, monkeypatch, source):
    output = tmp_path / "published"
    write_tables(*built, output)
    config = output / "regions.csv" if source == "regions" else ROOT / "config/regions.csv"
    if source == "regions":
        config.write_bytes((ROOT / "config/regions.csv").read_bytes())
    input_path = output / "tickets.csv" if source == "tickets" else None
    if input_path:
        built[0]["fact_demand"].query("period != 'future'")[["date", "region_id", "actual"]].rename(
            columns={"actual": "tickets"}
        ).to_csv(input_path, index=False)
    monkeypatch.setattr("staffing_forecast.cli.build_tables", lambda *args: built)
    with pytest.raises(ValueError, match="source"):
        refresh(output, config, input_path)
    assert (input_path or config).is_file()


@pytest.mark.parametrize("available", [None, -1, 1.5])
def test_excel_rejects_invalid_available_people_even_when_pasted(built, tmp_path, available):
    path = tmp_path / "plan.xlsx"
    write_workbook(built[0], path)
    wb = load_workbook(path)
    wb["Assumptions"]["F2"] = available
    wb.save(path)
    result = formulas.ExcelModel().loads(str(path)).finish().calculate()
    key = next(k for k in result if "DAILY PLAN" in k and k.endswith("'!H2"))
    assert str(result[key].value[0, 0]) == "#N/A"
