"""A portable Python Excel writer with cached results and editable linked calculations."""

from datetime import datetime, time, timedelta
from pathlib import Path

import xlsxwriter


def write_report(path: Path, result: dict):
    forecast = result["forecast"]
    recon = result["reconciliation"]
    with xlsxwriter.Workbook(path, {"strings_to_formulas": False, "strings_to_urls": False}) as wb:
        wb.set_properties(
            {"title": "Cash reconciliation and 13-week forecast", "author": "Jack Lai"}
        )
        body = wb.add_format({"font_name": "Arial", "font_size": 10})
        title = wb.add_format({"font_name": "Arial", "font_size": 15, "bold": True})
        header = wb.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "bold": True,
                "bg_color": "#24364B",
                "font_color": "white",
                "align": "center",
            }
        )
        numfmt = '#,##0.00;(#,##0.00);"-"'
        number = wb.add_format({"font_name": "Arial", "font_size": 10, "num_format": numfmt})
        difference = wb.add_format(
            {"font_name": "Arial", "font_size": 10, "num_format": "#,##0.00;(#,##0.00);0.00"}
        )
        editable = wb.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "num_format": numfmt,
                "font_color": "#1246A0",
                "bg_color": "#FFF3CC",
            }
        )
        datefmt = wb.add_format({"font_name": "Arial", "font_size": 10, "num_format": "dd-mmm-yy"})
        ratefmt = wb.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "num_format": "0.000000",
                "font_color": "#1246A0",
                "bg_color": "#FFF3CC",
            }
        )
        warning = wb.add_format({"bg_color": "#FCE1DF", "font_color": "#A32020"})

        def sheet(name, labels, widths):
            ws = wb.add_worksheet(name)
            ws.hide_gridlines(2)
            ws.set_default_row(20)
            for col, width in enumerate(widths):
                ws.set_column(col, col, width, body)
            ws.write(1, 0, labels[0], title)
            ws.write_row(4, 0, labels[1], header)
            ws.freeze_panes(5, 1)
            ws.set_landscape()
            ws.fit_to_pages(1, 0)
            ws.repeat_rows(0, 4)
            return ws

        ws = sheet(
            "Forecast",
            (
                "13-week cash forecast (CAD)",
                [
                    "Period start",
                    "Opening",
                    "Receipts",
                    "Payments",
                    "Closing",
                    "Minimum",
                    "Headroom",
                    "Daily low",
                    "Liquidity",
                ],
            ),
            [15, 16, 16, 16, 16, 16, 16, 16, 15],
        )
        ws.set_tab_color("#24364B")
        ws.write(2, 0, "As of")
        ws.write_datetime(2, 1, datetime.combine(result["as_of"], time()), datefmt)
        ws.write(21, 0, "Opening cash (CAD)")
        ws.write_number(21, 1, float(forecast["opening_cad"]), editable)
        ws.write(22, 0, "Minimum cash (CAD)")
        ws.write_number(22, 1, float(forecast["minimum_cad"]), editable)
        ws.write(24, 0, "Blue cells are inputs. Receipts and payments come from Expected cash.")
        ws.write(
            25, 0, "Daily low includes opening cash and each day's net cash. No intraday ordering."
        )
        ws.write(
            26, 0, "Overdue unsettled cash is scheduled on day one. FX is fixed at the as-of rate."
        )
        ws.write(
            27, 0, "Reconciliation differences require review. This forecast starts from bank cash."
        )

        flows = sheet(
            "Expected cash",
            (
                "Expected receipts and payments",
                [
                    "ID",
                    "Account",
                    "Due",
                    "Planned date",
                    "Description",
                    "Currency",
                    "Amount",
                    "CAD per unit",
                    "Amount CAD",
                    "Overdue days",
                ],
            ),
            [22, 20, 15, 15, 34, 12, 16, 16, 17, 16],
        )
        flows.write(
            2,
            0,
            "Source: imported CSV snapshot. Edit amount, planned date or FX rate to explore cash.",
        )
        for row, f in enumerate(forecast["flows"], 5):
            flows.write_row(row, 0, [f["id"], f["account"]])
            for col, key in ((2, "due"), (3, "planned_date")):
                flows.write_datetime(row, col, datetime.combine(f[key], time()), datefmt)
            flows.write_row(row, 4, [f["description"], f["currency"]])
            flows.write_number(row, 6, float(f["amount"]), editable)
            flows.write_number(row, 7, float(f["rate"]), ratefmt)
            flows.write_formula(row, 8, f"=ROUND(G{row + 1}*H{row + 1},2)", number, float(f["cad"]))
            flows.write_number(row, 9, f["overdue_days"])
        last = max(6, len(forecast["flows"]) + 5)
        # Keep an empty data row if there are no expected flows; SUMIFS still returns zero.
        amount = f"'Expected cash'!$I$6:$I${last}"
        planned = f"'Expected cash'!$D$6:$D${last}"
        daily = sheet(
            "Daily cash",
            ("Daily net cash (CAD)", ["Date", "Opening", "Net cash", "Closing"]),
            [16, 18, 18, 18],
        )
        running = forecast["opening_cad"]
        daily_closes = []
        for day in range(91):
            row, excel = day + 5, day + 6
            when = result["as_of"] + timedelta(days=day + 1)
            net = sum(f["cad"] for f in forecast["flows"] if f["planned_date"] == when)
            daily.write_datetime(row, 0, datetime.combine(when, time()), datefmt)
            opening_formula = "='Forecast'!$B$22" if day == 0 else f"=D{excel - 1}"
            daily.write_formula(row, 1, opening_formula, number, float(running))
            daily.write_formula(row, 2, f"=SUMIFS({amount},{planned},A{excel})", number, float(net))
            running += net
            daily.write_formula(row, 3, f"=SUM(B{excel}:C{excel})", number, float(running))
            daily_closes.append(running)
        for i, week in enumerate(forecast["weeks"]):
            row, excel = i + 5, i + 6
            d_first, d_last = 6 + i * 7, 12 + i * 7
            ws.write_datetime(row, 0, datetime.combine(week["start"], time()), datefmt)
            ws.write_formula(
                row, 1, "=$B$22" if i == 0 else f"=E{excel - 1}", number, float(week["opening"])
            )
            for col, sign, key in ((2, ">0", "inflows"), (3, "<0", "outflows")):
                formula = (
                    f'=SUMIFS({amount},{planned},">="&A{excel},'
                    f'{planned},"<"&A{excel}+7,{amount},"{sign}")'
                )
                ws.write_formula(row, col, formula, number, float(week[key]))
            ws.write_formula(row, 4, f"=SUM(B{excel}:D{excel})", number, float(week["closing"]))
            ws.write_formula(row, 5, "=$B$23", number, float(week["minimum"]))
            ws.write_formula(row, 6, f"=E{excel}-F{excel}", number, float(week["headroom"]))
            ws.write_formula(
                row,
                7,
                f"=MIN(B{excel},'Daily cash'!D{d_first}:D{d_last})",
                number,
                float(week["daily_low"]),
            )
            ws.write_formula(
                row,
                8,
                f'=IF(H{excel}<F{excel},"BELOW MIN","OK")',
                body,
                "BELOW MIN" if week["breach"] else "OK",
            )
        ws.conditional_format(
            "I6:I18",
            {"type": "text", "criteria": "containing", "value": "BELOW", "format": warning},
        )
        chart = wb.add_chart({"type": "line"})
        for name, col, color in (
            ("Closing cash", 4, "#24558A"),
            ("Minimum", 5, "#A32020"),
            ("Daily low", 7, "#B07821"),
        ):
            chart.add_series(
                {
                    "name": name,
                    "categories": ["Forecast", 5, 0, 17, 0],
                    "values": ["Forecast", 5, col, 17, col],
                    "line": {"color": color, "width": 2},
                }
            )
        chart.set_title(
            {"name": "Cash available (CAD)", "name_font": {"name": "Arial", "size": 12}}
        )
        chart.set_x_axis({"date_axis": True, "num_format": "d-mmm"})
        chart.set_y_axis({"num_format": "#,##0;(#,##0)"})
        chart.set_legend({"position": "bottom"})
        chart.set_size({"width": 750, "height": 330})
        ws.insert_chart("A30", chart)
        ws.print_area("A1:I47")

        controls = sheet(
            "Account checks",
            (
                "Bank and ledger balance checks",
                [
                    "Account",
                    "Currency",
                    "Bank closing",
                    "Ledger closing",
                    "Difference",
                    "Opening diff",
                    "Bank open items",
                    "Ledger open items",
                    "Paired variance",
                    "Unexplained",
                ],
            ),
            [22, 12, 18, 18, 18, 18, 20, 20, 20, 18],
        )
        controls.write(2, 0, "Amounts stay in account currency. Unexplained should be 0.00.")
        for row, c in enumerate(recon["controls"], 5):
            controls.write_row(row, 0, [c["account"], c["currency"]])
            for col, key in (
                (2, "bank_closing"),
                (3, "ledger_closing"),
                (5, "opening_difference"),
                (6, "bank_unmatched"),
                (7, "ledger_unmatched"),
                (8, "paired_variance"),
            ):
                controls.write_number(row, col, float(c[key]), number)
            e = row + 1
            controls.write_formula(row, 4, f"=C{e}-D{e}", difference, float(c["difference"]))
            controls.write_formula(
                row, 9, f"=E{e}-(F{e}+G{e}-H{e}+I{e})", difference, float(c["unexplained"])
            )
        controls.conditional_format(
            5,
            9,
            len(recon["controls"]) + 4,
            9,
            {
                "type": "cell",
                "criteria": "not between",
                "minimum": -0.005,
                "maximum": 0.005,
                "format": warning,
            },
        )

        issues = sheet(
            "Open items",
            (
                "Unmatched records and amount differences",
                [
                    "Source",
                    "ID",
                    "Account",
                    "Date",
                    "Amount",
                    "Reference / counterpart",
                    "Reason",
                    "Age days",
                    "Age band",
                    "Candidate IDs",
                ],
            ),
            [12, 22, 20, 15, 16, 30, 32, 12, 12, 36],
        )
        issues.write(
            2, 0, "Variance amount = bank minus ledger. Review items are not cleared matches."
        )
        for row, item in enumerate(recon["unmatched"], 5):
            issues.write_row(row, 0, [item["source"], item["id"], item["account"]])
            issues.write_datetime(row, 3, datetime.combine(item["date"], time()), datefmt)
            issues.write_number(row, 4, float(item["amount"]), number)
            issues.write_row(
                row,
                5,
                [
                    item["reference"],
                    item["reason"],
                    item["age_days"],
                    item["age_band"],
                    ", ".join(item["candidates"]),
                ],
            )
        next_row = len(recon["unmatched"]) + 5
        for p in recon["pairs"]:
            if p["variance"]:
                issues.write_row(next_row, 0, ["variance", p["bank_id"], p["account"]])
                issues.write_number(next_row, 4, float(p["variance"]), number)
                issues.write_row(
                    next_row, 5, [p["ledger_id"], "variance_review", p["age_days"], p["age_band"]]
                )
                next_row += 1
        pairs = sheet(
            "Matches",
            (
                "One-to-one record links",
                [
                    "Account",
                    "Bank ID",
                    "Ledger ID",
                    "Rule",
                    "Bank amount",
                    "Ledger amount",
                    "Variance",
                    "Date gap days",
                ],
            ),
            [22, 22, 22, 25, 18, 18, 18, 18],
        )
        for row, p in enumerate(recon["pairs"], 5):
            pairs.write_row(row, 0, [p["account"], p["bank_id"], p["ledger_id"], p["rule"]])
            for col, key in ((4, "bank_amount"), (5, "ledger_amount"), (6, "variance")):
                pairs.write_number(row, col, float(p[key]), number)
            pairs.write_number(row, 7, p["date_gap"])
        ws.activate()
