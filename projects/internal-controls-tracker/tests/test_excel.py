from datetime import datetime

import pytest
from conftest import exception, request
from openpyxl import load_workbook

from controls_tracker.excel import export_workbook


def records(sheet):
    values = list(sheet.values)
    return [dict(zip(values[0], row, strict=True)) for row in values[1:]]


def test_excel_round_trip_reconciles_matrix_samples_and_evidence(
    ready, evidence, tmp_path, control
):
    request(ready)
    ready.attach_evidence(request_id="AR-01", file=evidence, actor="Controller")
    run, _, _, _ = exception(ready, evidence)
    control["description"] = "New independent approval requirement"
    ready.save_control(**control)
    out = tmp_path / "review.xlsx"
    export_workbook(ready, out, "2026-08-10")
    wb = load_workbook(out)
    matrix = records(wb["Matrix"])
    assert matrix[0]["description"] == control["description"]
    assert matrix[0]["key"] is True
    assert matrix[0]["control_version"] == 2
    samples = records(wb["Samples"])
    assert len(samples) == 3
    assert {s["control_version"] for s in samples} == {1}
    assert {s["run_id"] for s in samples} == {run}
    assert sum(s["outcome"] == "exception" for s in samples) == 1
    assert len(records(wb["Population items"])) == 6
    assert len(records(wb["Documents"])) == 3
    assert len(records(wb["Evidence"])) == 2
    assert "content" not in list(wb["Evidence"].values)[0]
    assert isinstance(records(wb["Requests"])[0]["due"], datetime)
    assert records(wb["Requests"])[0]["overdue"] is True
    assert records(wb["Deficiencies"])[0]["overdue"] is True
    for sheet in wb:
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref
    wb.close()


@pytest.mark.parametrize(
    "value", ['=HYPERLINK("https://invalid.example","x")', "+1+1", "@SUM(A1:A2)", "-1+1", "\t=1+1"]
)
def test_imported_text_never_becomes_excel_formula(ready, control, tmp_path, value):
    control["description"] = value
    ready.save_control(**control)
    out = tmp_path / "literal.xlsx"
    export_workbook(ready, out, "2026-08-10")
    wb = load_workbook(out)
    sheet = wb["Matrix"]
    column = [c.value for c in sheet[1]].index("description") + 1
    assert sheet.cell(2, column).value == value.strip()
    assert sheet.cell(2, column).data_type == "s"
    assert not any(c.data_type == "f" for s in wb for row in s for c in row)
    wb.close()


def test_export_empty_database_has_headers_and_zero_counts(tracker, tmp_path):
    out = tmp_path / "empty.xlsx"
    export_workbook(tracker, out, "2026-08-10")
    wb = load_workbook(out)
    assert wb["Matrix"].max_row == 1
    assert wb["Requests"].max_row == 1
    assert dict(list(wb["Overview"].values)[1:])["exception_results"] == 0
    wb.close()
    with pytest.raises(FileExistsError):
        export_workbook(tracker, out, "2026-08-10")


def test_oversized_excel_text_fails_without_truncation(ready, control, tmp_path):
    control["description"] = "A" * 40000
    ready.save_control(**control)
    out = tmp_path / "too-long.xlsx"
    with pytest.raises(ValueError, match="Excel cell limit"):
        export_workbook(ready, out, "2026-08-10")
    assert not out.exists()


@pytest.mark.parametrize("character", ["\x01", "\ufffe", "\uffff"])
def test_unusual_xml_text_fails_cleanly_without_partial_export(ready, control, tmp_path, character):
    control["description"] = "Approval" + character + "date"
    ready.save_control(**control)
    out = tmp_path / "invalid.xlsx"
    with pytest.raises(ValueError, match="Excel cannot represent"):
        export_workbook(ready, out, "2026-08-10")
    assert not out.exists()
