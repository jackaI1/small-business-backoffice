import json
import re
import runpy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_model_matches_export_contracts_and_has_one_way_relationships(built):
    model = json.loads((ROOT / "powerbi/Staffing.SemanticModel/model.bim").read_text())["model"]
    tables = {table["name"]: table for table in model["tables"]}
    assert set(tables) == set(built[0])
    for name, frame in built[0].items():
        assert {c["name"] for c in tables[name]["columns"]} == set(frame.columns)
        source = "\n".join(tables[name]["partitions"][0]["source"]["expression"])
        assert f'ReadCsv("{name}")' in source
        assert "Table.TransformColumnTypes" in source
    for relationship in model["relationships"]:
        assert relationship["crossFilteringBehavior"] == "oneDirection"
        assert relationship["toCardinality"] == "one"
        dimension = built[0][relationship["toTable"]][relationship["toColumn"]]
        assert dimension.is_unique
        assert built[0][relationship["fromTable"]][relationship["fromColumn"]].isin(dimension).all()


def test_report_visual_fields_and_measures_resolve():
    model = json.loads((ROOT / "powerbi/Staffing.SemanticModel/model.bim").read_text())["model"]
    tables = {t["name"]: t for t in model["tables"]}
    visuals = list((ROOT / "powerbi/Staffing.Report").rglob("visual.json"))
    assert len(visuals) == 9
    for path in visuals:
        visual = json.loads(path.read_text())
        for role in visual["visual"]["query"]["queryState"].values():
            for projection in role["projections"]:
                kind, field = next(iter(projection["field"].items()))
                table = tables[field["Expression"]["SourceRef"]["Entity"]]
                available = table["measures" if kind == "Measure" else "columns"]
                assert field["Property"] in {item["name"] for item in available}
    pages = json.loads((ROOT / "powerbi/Staffing.Report/definition/pages/pages.json").read_text())
    assert pages["activePageName"] in pages["pageOrder"]


def test_dax_column_references_resolve_and_export_matches_source():
    model = json.loads((ROOT / "powerbi/Staffing.SemanticModel/model.bim").read_text())["model"]
    tables = {t["name"]: t for t in model["tables"]}
    measures = json.loads((ROOT / "powerbi/measures.json").read_text())
    assert {m["name"]: m["expression"] for m in tables["fact_demand"]["measures"]} == measures
    for expression in measures.values():
        for table, column in re.findall(r"(\w+)\[([^\]]+)\]", expression):
            assert column in {c["name"] for c in tables[table]["columns"]}
    assert "HASONEVALUE" in measures["Required Headcount"]
    assert "SUMX" in measures["Required Agent Shifts"] and "ROUNDUP" in measures["Required Agent Shifts"]


def test_powerbi_builder_is_reproducible(tmp_path):
    module = runpy.run_path(str(ROOT / "scripts/build_powerbi.py"))
    builder = module["main"]
    # Create into a disposable folder, preserving every checked-in artifact.
    builder.__globals__["PBI"] = tmp_path
    (tmp_path / "measures.json").write_bytes((ROOT / "powerbi/measures.json").read_bytes())
    builder()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (ROOT / "powerbi" / path.relative_to(tmp_path)).read_bytes()


def test_committed_sample_is_complete_and_reconciles():
    folder = ROOT / "outputs/sample"
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, rows in manifest["rows"].items():
        assert len(pd.read_csv(folder / f"{name}.csv")) == rows
    assert (folder / "staffing_plan.xlsx").stat().st_size > 5000
