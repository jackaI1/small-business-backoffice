"""A transparent formula schedule, with lifelib results as cached values.

The public CLI uses XlsxWriter so it needs only pip and works offline. The
schedule specification is also JSON-serializable for independent inspection.
"""

from pathlib import Path

from .engine import MORTALITY_SOURCE, load_mortality


def report_spec(results):
    sheets = {name: [] for name in ("Summary", "Assumptions", "Projection", "Cohorts", "Mortality")}

    def put(sheet, cell, value, style="body", cached=None):
        item = {"cell": cell, "style": style}
        if cached is None:
            item["value"] = value
        else:
            item.update(formula=value, cached=cached)
        sheets[sheet].append(item)

    for sheet, title in (("Summary", "Life insurance cash flows (USD)"),
                         ("Assumptions", "Annual assumptions"), ("Projection", "Cohort projection"),
                         ("Cohorts", "Synthetic policy cohorts"), ("Mortality", "SSA 2022 mortality")):
        put(sheet, "B2", title, "title")
    put("Summary", "B4", "Edit blue inputs on Assumptions. All seven comparisons recalculate. Negative liabilities mean future net income.")
    put("Summary", "B17", "Profit is premiums less claims and expenses, before investment income, reserve changes and tax.")
    put("Summary", "B18", "Reserves are signed prospective cash-flow values, not regulatory capital. Whole life has no surrender payout.")
    put("Assumptions", "B4", "Illustrative assumptions, not fitted insurer experience. Rates are annual. Premiums stay fixed across scenarios.")
    put("Cohorts", "B4", "Edit count, benefit and premium here. To change ages, terms or add cohorts, edit the CSV and rerun the CLI.")
    put("Mortality", "B4", f"Source: SSA period life table 2022, 2025 Trustees Report. {MORTALITY_SOURCE}")
    put("Mortality", "F6", "US population rates, not Canadian insured-life rates. q at 119 stays 100% in every scenario.")
    put("Projection", "B4", "Year 1 starts at issue. Premiums and expenses: start of year. Death claims: end. Lapses: after deaths.")

    def headers(sheet, row, columns):
        for col, title in columns.items():
            put(sheet, f"{col}{row}", title, "header")

    headers("Assumptions", 6, dict(zip("BCDEFGHIJ", ["Scenario", "Discount", "Mortality factor", "First lapse", "Later lapse", "Lapse factor", "Acquisition USD", "Maintenance USD", "Inflation"])))
    headers("Cohorts", 6, dict(zip("BCDEFGHIJ", ["Cohort", "Product", "Sex", "Issue age", "Policies", "Benefit USD", "Premium USD", "Years", "Net premium USD"])))
    headers("Mortality", 6, {"B": "Age", "C": "Male q", "D": "Female q"})
    rates = load_mortality()
    for age in range(120):
        for col, value in zip("BCD", [age, rates["male"][age], rates["female"][age]]):
            put("Mortality", f"{col}{age+7}", value, "integer" if col == "B" else "rate_input")
    for index, p in enumerate(results["Base"], 7):
        c = p.cohort
        for col, value in zip("BCDEFGHI", [c.id, c.product, c.sex, c.issue_age, c.count, c.benefit, c.annual_premium, c.years]):
            style = "input" if col in "FGH" else "body"
            put("Cohorts", f"{col}{index}", value, style)
    put("Cohorts", "B20", "Net premium is benefit PV divided by premium annuity on the Base basis, excluding expenses. It recalculates with Base inputs.")
    for index, (_, projections) in enumerate(results.items(), 7):
        a = projections[0].assumptions
        values = [list(results)[index-7], a.discount_rate, a.mortality_factor, a.lapse_first,
                  a.lapse_renewal, a.lapse_factor, a.acquisition, a.maintenance, a.inflation]
        for col, value in zip("BCDEFGHIJ", values):
            put("Assumptions", f"{col}{index}", value, "body" if col == "B" else ("input" if col in "HI" else "rate_input"))

    projection_headers = ["Scenario", "Cohort", "Year", "Age", "Opening", "Death rate", "Lapse rate", "Deaths", "Lapses", "Expiries", "Closing", "Premiums USD", "Claims USD", "Expenses USD", "Cash profit USD", "Reserve start USD", "Reserve end USD", "PV premiums USD", "PV claims USD", "PV expenses USD", "PV exposure"]
    headers("Projection", 6, dict(zip("ABCDEFGHIJKLMNOPQRSTU", projection_headers)))
    r = 7
    ranges = {}
    for si, (scenario, projections) in enumerate(results.items(), 7):
        scenario_start = r
        for ci, p in enumerate(projections, 7):
            block_start = r
            for t, data in enumerate(p.rows):
                last = t == len(p.rows) - 1
                c, a = p.cohort, p.assumptions
                put("Projection", f"A{r}", scenario)
                put("Projection", f"B{r}", c.id)
                put("Projection", f"C{r}", t + 1, "integer")
                formulas = {
                    "D": (f"=Cohorts!$E${ci}+C{r}-1", data["age"]),
                    "E": (f"=Cohorts!$F${ci}" if t == 0 else f"=K{r-1}", data["opening"]),
                    "F": (f'=IF(D{r}=119,1,MIN(1,INDEX(Mortality!${"C" if c.sex == "male" else "D"}$7:${"C" if c.sex == "male" else "D"}$126,D{r}+1)*Assumptions!$D${si}))', data["mortality"]),
                    "G": (f"=MIN(1,Assumptions!${'E' if t == 0 else 'F'}${si}*Assumptions!$G${si})", data["lapse"]),
                    "H": (f"=E{r}*F{r}", data["deaths"]),
                    "I": (f"=(E{r}-H{r})*G{r}", data["lapses"]),
                    "J": (f"=E{r}-H{r}-I{r}" if last else "=0", data["expiries"]),
                    "K": (f"=E{r}-H{r}-I{r}-J{r}", data["closing"]),
                    "L": (f"=E{r}*Cohorts!$H${ci}", data["premiums"]),
                    "M": (f"=H{r}*Cohorts!$G${ci}", data["claims"]),
                    "N": (f"=E{r}*(Assumptions!$I${si}*(1+Assumptions!$J${si})^(C{r}-1)+" + (f"Assumptions!$H${si})" if t == 0 else "0)"), data["expenses"]),
                    "O": (f"=L{r}-M{r}-N{r}", data["cash_profit"]),
                    "P": (f"=N{r}-L{r}+(M{r}+Q{r})/(1+Assumptions!$C${si})", data["reserve_beg"]),
                    "Q": ("=0" if last else f"=P{r+1}", data["reserve_end"]),
                    "R": (f"=L{r}/(1+Assumptions!$C${si})^(C{r}-1)", data["pv_premiums"]),
                    "S": (f"=M{r}/(1+Assumptions!$C${si})^C{r}", data["pv_claims"]),
                    "T": (f"=N{r}/(1+Assumptions!$C${si})^(C{r}-1)", data["pv_expenses"]),
                    "U": (f"=E{r}/(1+Assumptions!$C${si})^(C{r}-1)", data["opening"] / (1 + a.discount_rate) ** t),
                }
                for col, (formula, cached) in formulas.items():
                    put("Projection", f"{col}{r}", formula, "rate" if col in "FG" else ("number" if col in "DEHIJK" else "money"), cached)
                r += 1
            ranges[(scenario, c.id)] = (block_start, r - 1)
            if scenario == "Base":
                put("Cohorts", f"J{ci}", f"=SUM(Projection!S{block_start}:S{r-1})/SUM(Projection!U{block_start}:U{r-1})", "money", p.summary["net_premium"])
        ranges[scenario] = (scenario_start, r - 1)

    headers("Summary", 6, dict(zip("BCDEFGH", ["Scenario", "PV premiums", "PV claims", "PV expenses", "PV liabilities", "Change vs Base", "PV cash profit"])))
    base_pv = sum(p.summary["pv_liabilities"] for p in results["Base"])
    for sr, (name, projections) in enumerate(results.items(), 7):
        put("Summary", f"B{sr}", name)
        start, end = ranges[name]
        sums = {k: sum(p.summary[k] for p in projections) for k in projections[0].summary}
        for col, source, key in (("C", "R", "pv_premiums"), ("D", "S", "pv_claims"), ("E", "T", "pv_expenses")):
            put("Summary", f"{col}{sr}", f"=SUM(Projection!{source}{start}:{source}{end})", "money", sums[key])
        put("Summary", f"F{sr}", f"=D{sr}+E{sr}-C{sr}", "money", sums["pv_liabilities"])
        put("Summary", f"G{sr}", f"=F{sr}-$F$7", "money", sums["pv_liabilities"] - base_pv)
        put("Summary", f"H{sr}", f"=-F{sr}", "money", sums["pv_profit"])
    headers("Summary", 21, {"B": "Base cohort", "C": "PV liabilities", "D": "Initial reserve"})
    for sr, p in enumerate(results["Base"], 22):
        start, end = ranges[("Base", p.cohort.id)]
        put("Summary", f"B{sr}", p.cohort.id)
        put("Summary", f"C{sr}", f"=SUM(Projection!S{start}:T{end})-SUM(Projection!R{start}:R{end})", "money", p.summary["pv_liabilities"])
        put("Summary", f"D{sr}", f"=Projection!P{start}", "money", p.rows[0]["reserve_beg"])
    headers("Summary", 30, dict(zip("BCDEF", ["Base year", "Premiums USD", "Claims USD", "Expenses USD", "Cash profit USD"])))
    base_start, base_end = ranges["Base"]
    for year in range(1, max(p.cohort.years for p in results["Base"]) + 1):
        row = year + 30
        put("Summary", f"B{row}", year, "integer")
        for col, source, key in (("C", "L", "premiums"), ("D", "M", "claims"), ("E", "N", "expenses"), ("F", "O", "cash_profit")):
            total = sum(p.rows[year-1][key] for p in results["Base"] if year <= len(p.rows))
            put("Summary", f"{col}{row}", f"=SUMIF(Projection!$C${base_start}:$C${base_end},B{row},Projection!{source}{base_start}:{source}{base_end})", "money", total)
    return sheets


def export_report(results, path):
    import xlsxwriter

    spec = report_spec(results)
    with xlsxwriter.Workbook(str(path), {"strings_to_formulas": False, "strings_to_urls": False}) as book:
        book.set_properties({"title": "Life insurance cash flows", "author": "Jack Lai"})
        formats = {
            "body": book.add_format({"font_name": "Arial", "font_size": 10}),
            "title": book.add_format({"font_name": "Arial", "font_size": 15, "bold": True, "font_color": "#203864"}),
            "header": book.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "bg_color": "#203864", "font_color": "white", "text_wrap": True, "align": "center", "valign": "vcenter"}),
        }
        for style, num_format in (("money", '#,##0;(#,##0);"-"'), ("number", "#,##0.00"), ("integer", "0"), ("rate", "0.00%"), ("input", "#,##0.00"), ("rate_input", "0.00%")):
            formats[style] = book.add_format({"font_name": "Arial", "font_size": 10, "num_format": num_format,
                                             **({"font_color": "#0000FF", "bg_color": "#FFF2CC"} if "input" in style else {})})
        for name, items in spec.items():
            sheet = book.add_worksheet(name)
            sheet.hide_gridlines(2)
            sheet.set_column("A:A", 3 if name != "Projection" else 23)
            sheet.set_column("B:B", 24)
            sheet.set_column("C:U", 19)
            sheet.set_default_row(20)
            sheet.set_row(1, 26)
            sheet.set_row(5, 32)
            if name != "Summary":
                sheet.freeze_panes(6, 2 if name == "Projection" else 0)
            for item in items:
                fmt = formats[item["style"]]
                if "formula" in item:
                    sheet.write_formula(item["cell"], item["formula"], fmt, item["cached"])
                else:
                    sheet.write(item["cell"], item["value"], fmt)
            if name == "Assumptions":
                sheet.data_validation("C7:C13", {"validate": "decimal", "criteria": "between", "minimum": -0.99, "maximum": 1})
                sheet.data_validation("E7:F13", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 1})
                sheet.data_validation("D7:D13", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 10})
                sheet.data_validation("G7:I13", {"validate": "decimal", "criteria": ">=", "value": 0})
                sheet.data_validation("J7:J13", {"validate": "decimal", "criteria": ">", "value": -1})
            if name == "Summary":
                sheet.set_tab_color("#203864")
                chart = book.add_chart({"type": "line"})
                end = 30 + max(p.cohort.years for p in results["Base"])
                chart.add_series({"name": "Cash profit USD", "categories": f"=Summary!$B$31:$B${end}", "values": f"=Summary!$F$31:$F${end}"})
                chart.set_title({"name": "Base annual cash profit"})
                chart.set_legend({"none": True})
                chart.set_x_axis({"name": "Policy year"})
                chart.set_y_axis({"num_format": '#,##0;(#,##0)'})
                sheet.insert_chart("I21", chart)
    return Path(path)
