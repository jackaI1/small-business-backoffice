"""Build the checked-in Power BI project from explicit CSV and measure contracts.

Power BI Desktop uses model.bim (TMSL) and the editable PBIR report format.
No service credentials or private authoring libraries are required.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/"
TABLES = {
    "fact_demand": {
        "date": "dateTime",
        "region_id": "string",
        "actual": "double",
        "forecast": "double",
        "period": "string",
        "model": "string",
        "origin_date": "dateTime",
        "absolute_error": "double",
        "matched_actual": "double",
        "planning_volume": "double",
        "required_headcount": "int64",
        "headcount_gap": "int64",
    },
    "fact_backtest": {
        "region_id": "string",
        "fold": "int64",
        "phase": "string",
        "origin_date": "dateTime",
        "date": "dateTime",
        "lead_days": "int64",
        "model": "string",
        "actual": "double",
        "forecast": "double",
        "absolute_error": "double",
    },
    "fact_metrics": {
        "region_id": "string",
        "phase": "string",
        "model": "string",
        "selected": "int64",
        "mae": "double",
        "rmse": "double",
        "wape": "double",
        "bias": "double",
        "n": "int64",
    },
    "dim_date": {
        "date": "dateTime",
        "year": "int64",
        "month": "int64",
        "month_name": "string",
        "weekday_number": "int64",
        "weekday": "string",
        "week_start": "dateTime",
        "is_future": "int64",
    },
    "dim_region": {
        "region_id": "string",
        "region_name": "string",
        "handling_minutes": "double",
        "paid_hours": "double",
        "shrinkage": "double",
        "occupancy": "double",
        "available_headcount": "int64",
    },
    "dim_model": {"model": "string"},
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def field(table, name, measure=False):
    return {"Measure" if measure else "Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def projection(table, name, measure=False):
    return {"field": field(table, name, measure), "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def visual(name, kind, roles, x, y, width, height):
    return {
        "$schema": SCHEMA + "report/definition/visualContainer/2.4.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": height, "width": width, "tabOrder": 0},
        "visual": {
            "visualType": kind,
            "query": {"queryState": {role: {"projections": items} for role, items in roles.items()}},
            "drillFilterOtherVisuals": True,
        },
    }


def main():
    expressions = [
        {
            "name": "SourceFolder",
            "kind": "m",
            "expression": '"C:\\staffing-demand-forecast\\outputs\\sample" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        },
        {
            "name": "ReadCsv",
            "kind": "m",
            "expression": [
                "(name as text) as table =>",
                "let",
                '    Raw = Csv.Document(File.Contents(SourceFolder & "/" & name & ".csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                "    Headers = Table.PromoteHeaders(Raw, [PromoteAllScalars=true]),",
                '    Blanks = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers))',
                "in Blanks",
            ],
        },
    ]
    measures = json.loads((PBI / "measures.json").read_text())
    dax = "\n\n".join(f"{name} =\n{expression}" for name, expression in measures.items()) + "\n"
    (PBI / "measures.dax").write_text(dax)
    tables = []
    mtypes = {"dateTime": "type date", "double": "type number", "int64": "Int64.Type", "string": "type text"}
    for name, columns in TABLES.items():
        types = ", ".join('{"' + col + '", ' + mtypes[typ] + "}" for col, typ in columns.items())
        table = {
            "name": name,
            "columns": [
                {
                    "name": col,
                    "dataType": typ,
                    "sourceColumn": col,
                    "summarizeBy": "none",
                    **({"formatString": "yyyy-MM-dd"} if typ == "dateTime" else {}),
                }
                for col, typ in columns.items()
            ],
            "partitions": [
                {
                    "name": name,
                    "mode": "import",
                    "source": {
                        "type": "m",
                        "expression": [
                            "let",
                            f'    Source = ReadCsv("{name}"),',
                            f'    Typed = Table.TransformColumnTypes(Source, {{{types}}}, "en-US")',
                            "in Typed",
                        ],
                    },
                }
            ],
        }
        if name == "dim_date":
            for col in table["columns"]:
                if col["name"] == "month_name":
                    col["sortByColumn"] = "month"
                elif col["name"] == "weekday":
                    col["sortByColumn"] = "weekday_number"
        if name == "fact_demand":
            table["measures"] = [
                {
                    "name": n,
                    "expression": e,
                    "formatString": "0.0%" if ("%" in n or "WAPE" in n) else "#,0.0" if "MAE" in n else "#,0",
                }
                for n, e in measures.items()
            ]
        tables.append(table)
    relationships = []
    for name in ("fact_demand", "fact_backtest", "fact_metrics"):
        for column, dimension in [("date", "dim_date"), ("region_id", "dim_region"), ("model", "dim_model")]:
            if column in TABLES[name]:
                relationships.append(
                    {
                        "name": f"{name}_{dimension}",
                        "fromTable": name,
                        "fromColumn": column,
                        "toTable": dimension,
                        "toColumn": column,
                        "fromCardinality": "many",
                        "toCardinality": "one",
                        "crossFilteringBehavior": "oneDirection",
                    }
                )
    write(
        PBI / "Staffing.SemanticModel/model.bim",
        {
            "name": "Staffing",
            "compatibilityLevel": 1600,
            "model": {
                "culture": "en-US",
                "defaultPowerBIDataSourceVersion": "powerBI_V3",
                "expressions": expressions,
                "tables": tables,
                "relationships": relationships,
                "annotations": [{"name": "PBI_QueryOrder", "value": json.dumps(["SourceFolder", "ReadCsv", *TABLES])}],
            },
        },
    )
    write(
        PBI / "Staffing.SemanticModel/definition.pbism",
        {"$schema": SCHEMA + "semanticModel/definitionProperties/1.0.0/schema.json", "version": "1.0", "settings": {}},
    )
    write(
        PBI / "Staffing.pbip",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": "Staffing.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )
    report = PBI / "Staffing.Report"
    write(
        report / "definition.pbir",
        {
            "$schema": SCHEMA + "report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../Staffing.SemanticModel"}},
        },
    )
    write(
        report / "definition/report.json",
        {"$schema": SCHEMA + "report/definition/report/3.1.0/schema.json", "themeCollection": {}},
    )
    pages = {"demand": "Demand and forecast", "staffing": "Daily staffing", "accuracy": "Backtest accuracy"}
    write(
        report / "definition/pages/pages.json",
        {
            "$schema": SCHEMA + "report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": list(pages),
            "activePageName": "demand",
        },
    )
    for name, display in pages.items():
        folder = report / "definition/pages" / name
        write(
            folder / "page.json",
            {
                "$schema": SCHEMA + "report/definition/page/2.0.0/schema.json",
                "name": name,
                "displayName": display,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
        )
        visuals = [
            visual("region_filter", "slicer", {"Values": [projection("dim_region", "region_name")]}, 20, 20, 260, 100)
        ]
        if name == "demand":
            visuals += [
                visual(
                    "demand_trend",
                    "lineChart",
                    {
                        "Category": [projection("dim_date", "date")],
                        "Y": [projection("fact_demand", n, True) for n in ("Actual Tickets", "Forecast Tickets")],
                    },
                    20,
                    140,
                    1240,
                    360,
                ),
                visual(
                    "variance",
                    "tableEx",
                    {
                        "Values": [projection("dim_region", "region_name")]
                        + [
                            projection("fact_demand", n, True)
                            for n in (
                                "Matched Actual Tickets",
                                "Matched Forecast Tickets",
                                "Forecast Variance %",
                                "Evaluation WAPE",
                            )
                        ]
                    },
                    20,
                    520,
                    1240,
                    180,
                ),
            ]
        elif name == "staffing":
            visuals += [
                visual(
                    "daily_staffing",
                    "tableEx",
                    {
                        "Values": [projection("dim_date", "date"), projection("dim_region", "region_name")]
                        + [
                            projection("fact_demand", n, True)
                            for n in (
                                "Future Forecast Tickets",
                                "Planning Tickets",
                                "Required Headcount",
                                "Headcount Gap",
                            )
                        ]
                    },
                    20,
                    140,
                    1240,
                    400,
                ),
                visual(
                    "staffing_totals",
                    "tableEx",
                    {
                        "Values": [projection("dim_region", "region_name")]
                        + [
                            projection("fact_demand", n, True)
                            for n in ("Required Agent Shifts", "Peak Daily Headcount")
                        ]
                    },
                    20,
                    560,
                    1240,
                    140,
                ),
            ]
        else:
            visuals += [
                visual("phase_filter", "slicer", {"Values": [projection("fact_backtest", "phase")]}, 310, 20, 270, 100),
                visual(
                    "model_comparison",
                    "tableEx",
                    {
                        "Values": [
                            projection("dim_region", "region_name"),
                            projection("dim_model", "model"),
                            projection("fact_backtest", "phase"),
                        ]
                        + [projection("fact_demand", n, True) for n in ("Backtest WAPE", "Backtest MAE")]
                    },
                    20,
                    140,
                    1240,
                    560,
                ),
            ]
        for item in visuals:
            write(folder / "visuals" / item["name"] / "visual.json", item)


if __name__ == "__main__":
    main()
