"""Open the exported workbook in a real calculation engine, including edits."""

from dataclasses import replace
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

from openpyxl import load_workbook
import pytest

from insurance_projection.cli import load_cohorts, run
from insurance_projection.engine import Assumptions, ProjectionEngine
from insurance_projection.report import export_report


@pytest.fixture(scope="module")
def results():
    return run(load_cohorts("examples/cohorts.csv"), Assumptions())


def recalculate(source, output, profile):
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        pytest.skip("LibreOffice is required for native workbook recalculation; CI installs it")
    # LibreOffice can trust saved Excel formula caches during conversion.
    # Remove them first so this test proves actual calculation, not cache reuse.
    inputs = output.parent / f"{output.name}-inputs"
    inputs.mkdir()
    input_path = inputs / source.name
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(input_path, "w") as edited:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet") and item.filename.endswith(".xml"):
                root = ET.fromstring(content)
                for cell in root.findall(".//s:c", ns):
                    if cell.find("s:f", ns) is not None:
                        value = cell.find("s:v", ns)
                        if value is not None:
                            cell.remove(value)
                content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            edited.writestr(item, content)
    output.mkdir()
    command = [executable, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--convert-to", "xlsx", "--outdir", str(output), str(input_path)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    print(f"Owned fixture PID={process.pid}, started={time.time():.3f}, port=none, cleanup=SIGTERM process group {process.pid}")
    try:
        log, _ = process.communicate(timeout=60)
        assert process.returncode == 0, log[-2000:]
        assert (output / source.name).is_file(), log[-2000:]
    finally:
        # This group belongs only to the disposable, isolated-profile fixture.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            pytest.fail(f"LibreOffice fixture process group {process.pid} remains")
    return output / source.name


def edit_numeric_cells(source, dest, changes):
    """Patch only the requested numeric inputs in a disposable ZIP copy."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(dest, "w") as edited:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == "xl/worksheets/sheet2.xml":
                root = ET.fromstring(content)
                for address, value in changes.items():
                    cell = root.find(f".//s:c[@r='{address}']/s:v", ns)
                    assert cell is not None
                    cell.text = str(value)
                content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            edited.writestr(item, content)


def test_export_cached_values_and_real_formulas(tmp_path, results):
    path = export_report(results, tmp_path / "projection.xlsx")
    formulas = load_workbook(path, data_only=False)
    values = load_workbook(path, data_only=True)
    assert formulas.sheetnames == ["Summary", "Assumptions", "Projection", "Cohorts", "Mortality"]
    for index, (_, projections) in enumerate(results.items(), 7):
        expected = sum(p.summary["pv_liabilities"] for p in projections)
        assert values["Summary"][f"F{index}"].value == pytest.approx(expected)
        assert formulas["Summary"][f"F{index}"].value.startswith("=")
    assert formulas["Projection"]["P7"].value == "=N7-L7+(M7+Q7)/(1+Assumptions!$C$7)"
    assert formulas["Cohorts"]["J7"].data_type == "f"
    formulas.close()
    values.close()


def test_native_recalculation_all_scenarios_and_reserves(tmp_path, results):
    source = export_report(results, tmp_path / "projection.xlsx")
    path = recalculate(source, tmp_path / "recalculated", tmp_path / "profile")
    book = load_workbook(path, data_only=True)
    projection = book["Projection"]
    r = 7
    for index, (_, projections) in enumerate(results.items(), 7):
        for column, key in (("C", "pv_premiums"), ("D", "pv_claims"), ("E", "pv_expenses"), ("F", "pv_liabilities"), ("H", "pv_profit")):
            assert book["Summary"][f"{column}{index}"].value == pytest.approx(sum(p.summary[key] for p in projections), abs=0.00001)
        for p in projections:
            for expected in p.rows:
                for column, key in (("E", "opening"), ("F", "mortality"), ("K", "closing"), ("P", "reserve_beg"), ("Q", "reserve_end")):
                    assert projection[f"{column}{r}"].value == pytest.approx(expected[key], abs=0.00001)
                r += 1
    for ci, p in enumerate(results["Base"], 7):
        assert book["Cohorts"][f"J{ci}"].value == pytest.approx(p.summary["net_premium"])
    for sheet in book:
        assert not any(c.data_type == "e" for row in sheet for c in row), sheet.title
    book.close()


@pytest.mark.parametrize("edits,assumptions", [
    ({"C7": 0.02}, replace(Assumptions(), discount_rate=0.02)),
    ({"D7": 1.4}, replace(Assumptions(), mortality_factor=1.4)),
    ({"G7": 0}, replace(Assumptions(), lapse_factor=0)),
])
def test_excel_input_change_reprojects(tmp_path, results, edits, assumptions):
    source = export_report(results, tmp_path / "projection.xlsx")
    edited = tmp_path / "edited.xlsx"
    edit_numeric_cells(source, edited, edits)
    path = recalculate(edited, tmp_path / "recalculated", tmp_path / "profile")
    with ProjectionEngine() as engine:
        expected = [engine.project(p.cohort, assumptions) for p in results["Base"]]
    book = load_workbook(path, data_only=True)
    assert book["Summary"]["F7"].value == pytest.approx(sum(p.summary["pv_liabilities"] for p in expected), abs=0.00001)
    assert book["Summary"]["F7"].value != pytest.approx(sum(p.summary["pv_liabilities"] for p in results["Base"]))
    # Editing Base must leave independently parameterized comparison cases alone.
    assert book["Summary"]["F8"].value == pytest.approx(sum(p.summary["pv_liabilities"] for p in results["Mortality -20%"]), abs=0.00001)
    book.close()
