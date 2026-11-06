"""Point-in-time Excel review packs, generated from the actual saved records."""

import json
import re
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .core import iso_date

# XML 1.0 text excludes control characters, surrogate code points and U+FFFE/U+FFFF.
INVALID_XML_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")

SCHEETS = {
    "Matrix": [
        "control_id",
        "control_version",
        "process_id",
        "process_version",
        "risk",
        "description",
        "owner",
        "frequency",
        "key",
        "assertion",
        "test_procedure",
        "evidence_expected",
        "narrative",
    ],
    "Requests": [
        "id",
        "control_id",
        "description",
        "owner",
        "due",
        "status",
        "overdue",
        "evidence_ids",
        "open_followups",
        "requested_by",
        "created_at",
    ],
    "Follow-ups": [
        "id",
        "request_id",
        "description",
        "owner",
        "due",
        "status",
        "overdue",
        "resolution",
        "created_at",
    ],
    "Deficiencies": [
        "id",
        "result_id",
        "control_id",
        "owner",
        "due",
        "action",
        "status",
        "overdue",
        "resolution",
        "created_at",
    ],
    "Samples": [
        "run_id",
        "population_id",
        "control_id",
        "control_version",
        "process_id",
        "process_version",
        "seed",
        "size",
        "rationale",
        "algorithm",
        "tester",
        "created_at",
        "rank",
        "item_id",
        "date",
        "description",
        "outcome",
        "result_id",
        "notes",
        "evidence_id",
        "result_tester",
        "tested_at",
    ],
    "Populations": [
        "id",
        "control_id",
        "control_version",
        "process_id",
        "process_version",
        "period_start",
        "period_end",
        "source",
        "reconciliation",
        "item_count",
        "sha256",
        "created_at",
    ],
    "Population items": ["population_id", "id", "date", "description"],
    "Documents": [
        "kind",
        "id",
        "version",
        "author",
        "reason",
        "created_at",
        "name",
        "narrative",
        "process_id",
        "risk",
        "description",
        "owner",
        "frequency",
        "key",
        "assertion",
        "test_procedure",
        "evidence_expected",
    ],
    "Evidence": ["id", "filename", "sha256", "size_bytes", "actor", "created_at"],
    "History": ["id", "entity", "entity_id", "action", "actor", "detail", "created_at"],
}
DATE_COLUMNS = {"due", "date", "period_start", "period_end"}
LONG_COLUMNS = {
    "risk",
    "description",
    "test_procedure",
    "evidence_expected",
    "narrative",
    "rationale",
    "notes",
    "action",
    "resolution",
    "reconciliation",
    "detail",
}


def review_data(tracker, as_of):
    """Materialize one coherent read snapshot for all review sheets."""
    summary = tracker.status(as_of)
    data = {name: [] for name in SCHEETS}
    documents = tracker.rows("documents")
    current = {}
    for doc in documents:
        payload = json.loads(doc["payload"])
        current[doc["kind"], doc["id"]] = (doc, payload)
        data["Documents"].append({**doc, **payload})
    for (kind, _), (doc, payload) in current.items():
        if kind == "control":
            process, narrative = current["process", payload["process_id"]]
            data["Matrix"].append(
                {
                    **payload,
                    "control_id": doc["id"],
                    "control_version": doc["version"],
                    "process_version": process["version"],
                    "narrative": narrative["narrative"],
                }
            )
    pops = {p["id"]: p for p in tracker.rows("populations")}
    runs = {r["id"]: r for r in tracker.rows("runs")}
    results = {(r["run_id"], r["item_id"]): r for r in tracker.rows("results")}
    by_result = {r["id"]: r for r in results.values()}
    items = {}
    for pop in pops.values():
        entries = json.loads(pop["payload"])
        data["Populations"].append({**pop, "item_count": len(entries)})
        for entry in entries:
            items[pop["id"], entry["id"]] = entry
            data["Population items"].append({"population_id": pop["id"], **entry})
    for selected in tracker.rows("selections"):
        run = runs[selected["run_id"]]
        pop = pops[run["population_id"]]
        item = items[pop["id"], selected["item_id"]]
        result = results.get((run["id"], item["id"]), {})
        data["Samples"].append(
            {
                **pop,
                **run,
                **item,
                **selected,
                "outcome": result.get("outcome", "untested"),
                "result_id": result.get("id"),
                "notes": result.get("notes"),
                "evidence_id": result.get("evidence_id"),
                "result_tester": result.get("tester"),
                "tested_at": result.get("created_at"),
            }
        )
    followups = tracker.rows("followups")
    links = tracker.rows("request_evidence")
    for req in tracker.rows("requests"):
        data["Requests"].append(
            {
                **req,
                "overdue": req["status"] != "fulfilled" and req["due"] < as_of,
                "evidence_ids": ", ".join(
                    str(e["evidence_id"]) for e in links if e["request_id"] == req["id"]
                ),
                "open_followups": sum(
                    f["request_id"] == req["id"] and f["status"] == "open" for f in followups
                ),
            }
        )
    for followup in followups:
        data["Follow-ups"].append(
            {**followup, "overdue": followup["status"] == "open" and followup["due"] < as_of}
        )
    for deficiency in tracker.rows("deficiencies"):
        result = by_result[deficiency["result_id"]]
        pop = pops[runs[result["run_id"]]["population_id"]]
        data["Deficiencies"].append(
            {
                **deficiency,
                "control_id": pop["control_id"],
                "overdue": deficiency["status"] == "open" and deficiency["due"] < as_of,
            }
        )
    data["Evidence"] = tracker.rows("evidence")
    data["History"] = tracker.rows("events")
    return summary, data


def _sheet(workbook, name, columns, rows):
    sheet = workbook.create_sheet(name)
    sheet.append(columns)
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, str):
                if len(value) > 32767:
                    raise ValueError(
                        f"Excel cell limit exceeded in {name}.{column}. "
                        "Use list/documents JSON for the full text."
                    )
                if INVALID_XML_TEXT.search(value):
                    raise ValueError(
                        f"Excel cannot represent control characters in {name}.{column}"
                    )
                if column in DATE_COLUMNS:
                    value = date.fromisoformat(value)
            values.append(value)
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
            if isinstance(cell.value, date):
                cell.number_format = "yyyy-mm-dd"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.column <= len(columns) and columns[cell.column - 1] == "overdue" and cell.value:
                cell.fill = PatternFill("solid", fgColor="FCE4D6")
        sheet.row_dimensions[sheet.max_row].height = (
            90 if name in {"Matrix", "Documents", "Samples", "History"} else 60
        )
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 32
    for index, column in enumerate(columns, 1):
        sheet.column_dimensions[get_column_letter(index)].width = (
            48 if column in LONG_COLUMNS else 28 if column in {"sha256", "created_at"} else 22
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False


def export_workbook(tracker, path, as_of):
    """Save a new file; never overwrite an existing review pack or truncate text."""
    as_of = iso_date(as_of, "as_of")
    path = Path(path)
    # An explicit read transaction keeps all sheets consistent if another client writes.
    tracker.db.execute("BEGIN")
    try:
        summary, data = review_data(tracker, as_of)
    finally:
        tracker.db.rollback()
    workbook = Workbook()
    workbook.remove(workbook.active)
    try:
        _sheet(
            workbook,
            "Overview",
            ["metric", "value"],
            [dict(metric=k, value=v) for k, v in summary.items()]
            + [
                dict(
                    metric="date meaning",
                    value="Current records; deadlines evaluated as of "
                    + as_of
                    + ". Not a reconstruction of past status.",
                ),
                dict(
                    metric="source",
                    value="SQLite review snapshot. Evidence IDs refer to "
                    "stored files; extract them with the controls extract command.",
                ),
                dict(
                    metric="selection",
                    value="SHA-256 seed ranking without replacement. "
                    "Sample size is chosen and justified by the tester.",
                ),
            ],
        )
        for name, columns in SCHEETS.items():
            _sheet(workbook, name, columns, data[name])
        # Exclusive creation protects earlier review packs. Remove a failed partial write.
        created = False
        try:
            with path.open("xb") as handle:
                created = True
                workbook.save(handle)
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
    finally:
        workbook.close()
    return str(path)
