"""Refresh an editable Excel template using portable, public Python dependencies."""

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo


def write_workbook(tables: dict, path: Path):
    wb = load_workbook(Path(__file__).parent / "assets" / "staffing_template.xlsx")
    summary, assumptions, daily, errors = wb.worksheets
    summary["A2"] = "Daily staffing needs"
    summary["A3"] = "Synthetic demonstration by default. Headcount covers workload per day; it is not a shift roster."
    summary["A4"] = "Change blue assumptions to compare capacity. Positive gap means more people needed."
    for col, label in enumerate(
        ["Region", "Forecast tickets", "Agent shifts", "Peak people in a day", "Peak extra people"], 1
    ):
        summary.cell(5, col, label)
    assumptions.append(
        ["Region", "Minutes per ticket", "Paid hours per day", "Shrinkage", "Occupancy", "Available people"]
    )
    for r in tables["dim_region"].itertuples(index=False):
        assumptions.append(
            [r.region_id, r.handling_minutes, r.paid_hours, r.shrinkage, r.occupancy, r.available_headcount]
        )
    assumptions["H2"] = "Source: config/regions.csv. Illustrative staffing assumptions."
    assumptions["H3"] = "Shrinkage is paid time unavailable for tickets."
    assumptions["H4"] = "Occupancy is the share of remaining time spent on tickets."
    daily.append(
        [
            "Date",
            "Region",
            "Forecast tickets",
            "Planning tickets",
            "Work hours",
            "Hours per person",
            "Required people",
            "Available people",
            "Extra people",
        ]
    )
    assumption_rows = {region: i + 2 for i, region in enumerate(tables["dim_region"].region_id)}
    future = tables["fact_demand"].query("period == 'future'")
    for rowno, row in enumerate(future.itertuples(index=False), 2):
        a = assumption_rows[row.region_id]
        daily.append(
            [
                row.date.to_pydatetime(),
                row.region_id,
                row.forecast,
                row.planning_volume,
                f"=IF(AND(ISNUMBER(Assumptions!B{a}),Assumptions!B{a}>0),D{rowno}*Assumptions!B{a}/60,NA())",
                f"=IF(AND(ISNUMBER(Assumptions!C{a}),Assumptions!C{a}>0,ISNUMBER(Assumptions!D{a}),Assumptions!D{a}>=0,Assumptions!D{a}<1,ISNUMBER(Assumptions!E{a}),Assumptions!E{a}>0,Assumptions!E{a}<=1),Assumptions!C{a}*(1-Assumptions!D{a})*Assumptions!E{a},NA())",
                f"=MAX(IF(D{rowno}>0,1,0),ROUNDUP(ROUND(E{rowno}/F{rowno},10),0))",
                f"=IF(AND(ISNUMBER(Assumptions!F{a}),Assumptions!F{a}>=0),IF(MOD(Assumptions!F{a},1)=0,Assumptions!F{a},NA()),NA())",
                f"=G{rowno}-H{rowno}",
            ]
        )
    end = daily.max_row
    for i, region in enumerate(tables["dim_region"].region_id, 6):
        summary.cell(i, 1, region)
        summary.cell(i, 2, f"=SUMIFS('Daily plan'!C$2:C${end},'Daily plan'!B$2:B${end},A{i})")
        summary.cell(i, 3, f"=SUMIFS('Daily plan'!G$2:G${end},'Daily plan'!B$2:B${end},A{i})")
        summary.cell(i, 4, f"=_xlfn.MAXIFS('Daily plan'!G$2:G${end},'Daily plan'!B$2:B${end},A{i})")
        summary.cell(i, 5, f"=_xlfn.MAXIFS('Daily plan'!I$2:I${end},'Daily plan'!B$2:B${end},A{i})")
    note_row = max(12, 8 + len(assumption_rows))
    summary.cell(
        note_row, 1, "Agent shifts add daily rounded people. Peak people is the highest single-day need per region."
    )
    summary.cell(
        note_row + 1,
        1,
        "Planning tickets add an empirical buffer from earlier forecast errors, not a confidence interval.",
    )
    summary.cell(
        note_row + 2, 1, "Accuracy uses later evaluation dates that did not choose the model. Lower error is better."
    )
    errors.append(["Region", "Model", "Selected", "MAE tickets", "RMSE tickets", "WAPE", "Bias tickets", "Test days"])
    for r in tables["fact_metrics"].query("phase == 'evaluation'").itertuples(index=False):
        errors.append([r.region_id, r.model, r.selected, r.mae, r.rmse, r.wape, r.bias, r.n])
    for ws, header, widths in [
        (summary, 5, [24, 22, 22, 24, 23]),
        (assumptions, 1, [15, 24, 22, 18, 18, 23]),
        (daily, 1, [16, 14, 22, 22, 18, 22, 22, 22, 20]),
        (errors, 1, [15, 24, 14, 22, 22, 18, 22, 18]),
    ]:
        ws.sheet_view.showGridLines = False
        ws.freeze_panes = f"C{header + 1}" if ws == daily else f"A{header + 1}"
        for col, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = width
        for row in ws:
            for cell in row:
                cell.font = Font(name="Arial", size=11)
                cell.alignment = Alignment(vertical="center")
                if cell.data_type == "f":
                    cell.number_format = "#,##0"
        for cell in ws[header][: len(widths)]:
            cell.fill = PatternFill("solid", fgColor="253B53")
            cell.font = Font(name="Arial", size=11, color="FFFFFF", bold=True)
        ws.row_dimensions[header].height = 30
    summary["A2"].font = Font(name="Arial", size=16, bold=True)
    assumptions.column_dimensions["H"].width = 90
    assumption_end = len(assumption_rows) + 1
    for row in assumptions.iter_rows(min_row=2, max_row=assumption_end, min_col=2, max_col=6):
        for cell in row:
            cell.font = Font(name="Arial", size=11, color="1565C0")
            cell.fill = PatternFill("solid", fgColor="EDF4FC")
    for row in range(2, assumption_end + 1):
        assumptions[f"D{row}"].number_format = assumptions[f"E{row}"].number_format = "0%"
    for column, low, high, kind in [
        ("B", 0.01, 1440, "decimal"),
        ("C", 0.01, 24, "decimal"),
        ("D", 0, 0.99, "decimal"),
        ("E", 0.01, 1, "decimal"),
        ("F", 0, 100000, "whole"),
    ]:
        validation = DataValidation(type=kind, operator="between", formula1=low, formula2=high)
        validation.showErrorMessage = True
        validation.error = "Enter a value within the staffing bounds."
        assumptions.add_data_validation(validation)
        validation.add(f"{column}2:{column}{assumption_end}")
    for row in daily.iter_rows(min_row=2, max_row=end):
        row[0].number_format = "yyyy-mm-dd"
        for cell in row[2:6]:
            cell.number_format = "#,##0.0"
    for row in errors.iter_rows(min_row=2):
        row[5].number_format = "0.0%"
        for i in (3, 4, 6):
            row[i].number_format = "0.0"
    for ws in (daily, errors):
        table = Table(displayName=ws.title.replace(" ", ""), ref=f"A1:{get_column_letter(ws.max_column)}{ws.max_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(table)
    chart = BarChart()
    chart.title = "Peak people needed per region"
    chart.y_axis.title = "People per day"
    chart.add_data(Reference(summary, min_col=4, min_row=5, max_row=5 + len(assumption_rows)), titles_from_data=True)
    chart.set_categories(Reference(summary, min_col=1, min_row=6, max_row=5 + len(assumption_rows)))
    chart.width, chart.height = 20, 9
    chart.legend = None
    summary.add_chart(chart, f"A{note_row + 5}")
    wb.calculation = CalcProperties(calcId=0, fullCalcOnLoad=True)
    wb.save(path)
