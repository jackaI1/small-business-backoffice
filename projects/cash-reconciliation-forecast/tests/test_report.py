import shutil
import subprocess
import tempfile
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook

from cashforecast.forecast import forecast
from cashforecast.reconcile import reconcile
from cashforecast.report import write_report


@pytest.fixture
def report(sample, tmp_path):
    as_of = date(2026, 10, 31)
    reconciliation = reconcile(sample.accounts, sample.bank, sample.ledger, as_of)
    result = {
        "as_of": as_of,
        "reconciliation": reconciliation,
        "forecast": forecast(sample, reconciliation, as_of, Decimal("15000")),
    }
    path = tmp_path / "cash-report.xlsx"
    write_report(path, result)
    return path, result


def test_formula_caches_match_python_and_chart_links_to_cells(report):
    path, result = report
    formulas = load_workbook(path, data_only=False)
    values = load_workbook(path, data_only=True)
    try:
        assert formulas["Forecast"]["E6"].value == "=SUM(B6:D6)"
        assert formulas["Forecast"]["B7"].value == "=E6"
        assert "SUMIFS" in formulas["Forecast"]["C18"].value
        for row, week in enumerate(result["forecast"]["weeks"], 6):
            assert values["Forecast"][f"E{row}"].value == float(week["closing"])
            assert values["Forecast"][f"H{row}"].value == float(week["daily_low"])
        with ZipFile(path) as archive:
            chart = archive.read("xl/charts/chart1.xml").decode()
            for col in ("E", "F", "H"):
                assert f"Forecast!${col}$6:${col}$18" in chart
            assert "Forecast!$A$6:$A$18" in chart
    finally:
        formulas.close()
        values.close()


def test_source_text_cannot_become_excel_formula(sample, tmp_path):
    # A reference/description imported from a CSV must stay text even if it starts with '='.
    malicious = replace(
        sample.flows[0], description='=HYPERLINK("https://example.test","open")', settled_bank_id=""
    )
    changed = replace(sample, flows=(malicious,))
    as_of = date(2026, 10, 31)
    rec = reconcile(changed.accounts, changed.bank, changed.ledger, as_of)
    path = tmp_path / "safe.xlsx"
    write_report(
        path,
        {
            "as_of": as_of,
            "reconciliation": rec,
            "forecast": forecast(changed, rec, as_of, Decimal("15000")),
        },
    )
    wb = load_workbook(path)
    try:
        assert wb["Expected cash"]["E6"].data_type == "s"
        assert wb["Expected cash"]["E6"].value == malicious.description
    finally:
        wb.close()


def test_empty_flows_workbook_has_valid_bounded_formulas(sample, tmp_path):
    changed = replace(sample, flows=())
    as_of = date(2026, 10, 31)
    rec = reconcile(changed.accounts, changed.bank, changed.ledger, as_of)
    path = tmp_path / "empty.xlsx"
    write_report(
        path,
        {
            "as_of": as_of,
            "reconciliation": rec,
            "forecast": forecast(changed, rec, as_of, Decimal("15000")),
        },
    )
    wb = load_workbook(path, data_only=True)
    try:
        assert wb["Forecast"]["C6"].value == 0
        assert wb["Forecast"]["E18"].value == 60406.88
    finally:
        wb.close()


def test_native_recalculation_updates_cash_warning_and_linked_chart(report, tmp_path):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        pytest.skip("install LibreOffice Calc to verify native workbook recalculation")
    path, result = report
    wb = load_workbook(path)
    # Change a later-period receipt and the threshold. Output must recompute, not use caches.
    flows = wb["Expected cash"]
    changed_row = next(
        row for row in range(6, flows.max_row + 1) if flows.cell(row, 1).value == "CUSTOMERS-13"
    )
    flows.cell(changed_row, 7).value = 19500
    wb["Forecast"]["B23"] = 100000
    edited = tmp_path / "edited.xlsx"
    wb.save(edited)
    wb.close()
    target = tmp_path / "recalculated"
    target.mkdir()
    # A unique profile prevents connecting to or closing the owner's LibreOffice session.
    with tempfile.TemporaryDirectory(prefix="cash-calc-profile-") as profile:
        process = subprocess.Popen(
            [
                soffice,
                f"-env:UserInstallation={Path(profile).as_uri()}",
                "--headless",
                "--convert-to",
                "xlsx",
                "--outdir",
                str(target),
                str(edited),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert process.wait(timeout=60) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    recalculated = load_workbook(target / "edited.xlsx", data_only=True)
    try:
        forecast_sheet = recalculated["Forecast"]
        assert forecast_sheet["E18"].value == pytest.approx(
            float(result["forecast"]["weeks"][-1]["closing"]) + 10000
        )
        assert forecast_sheet["I18"].value == "BELOW MIN"
        assert forecast_sheet["H6"].value == pytest.approx(
            float(result["forecast"]["weeks"][0]["daily_low"])
        )
        for sheet in recalculated:
            assert not [cell.coordinate for row in sheet for cell in row if cell.data_type == "e"]
        with ZipFile(target / "edited.xlsx") as archive:
            chart = archive.read("xl/charts/chart1.xml").decode()
            assert "$E$6:$E$18" in chart
    finally:
        recalculated.close()
