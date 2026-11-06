# Power BI report setup and specification

I keep the report as an editable [Power BI project](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview). Its report definition uses [PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report), Microsoft's JSON report format, and its semantic model uses `model.bim`, a JSON description of tables, imports, relationships and calculations. This is a local import report. It does not need a paid service account.

## Open the example

1. Clone or download the entire repository onto Windows. Use a current Power BI Desktop that supports Power BI projects and the enhanced report format. Enable those preview features under **File > Options and settings > Options > Preview features** if required by that Desktop version, then restart Desktop.
2. Open `powerbi/Staffing.pbip`. The report points at `Staffing.SemanticModel` by relative path.
3. Select **Transform data > Edit parameters** and change `SourceFolder` to the absolute path of `outputs/sample`, such as `C:\Users\Jack\staffing-demand-forecast\outputs\sample`. The committed `C:\staffing-demand-forecast\outputs\sample` is an example path, not a credential. If Desktop asks about unavailable sources first, open the query editor and update this parameter before applying.
4. Apply changes and select **Refresh**. Six CSV tables are imported. Dates and numeric types are set explicitly with the `en-US` culture, so decimal points and ISO dates are interpreted consistently.
5. Open **Demand and forecast**, **Daily staffing**, and **Backtest accuracy**. Select a region in each page's slicer. The accuracy page also has a phase slicer. Use `evaluation` to see later results and `calibration` to see the earlier periods used to select the model.

To use refreshed output, run `uv run staffing-refresh --synthetic --output outputs/latest`, change `SourceFolder` to that folder, and refresh Desktop. A GitHub Actions artifact must be downloaded and extracted first. The report does not read directly from the workflow's artifact storage. Never edit files inside `.pbi` or commit Desktop caches.

## Report pages

| Page | Visuals and fields | What I use it for |
| --- | --- | --- |
| Demand and forecast | Region slicer; date line chart of Actual Tickets and Forecast Tickets; regional table of matched actual, matched forecast, variance percentage and evaluation WAPE | Check the weekly pattern and compare only dates with both an actual and a prediction |
| Daily staffing | Region slicer; date/region table of future forecast, planning tickets, required headcount and headcount gap; regional table of required agent shifts and peak daily headcount | Identify busy days and the daily people needed under the assumptions |
| Backtest accuracy | Region and phase slicers; region/model/phase table of backtest WAPE and MAE | Compare every candidate fairly over the same regional targets |

Every page is 1280 by 720 with a region slicer at the top and the main comparison below. The nine visual definitions are committed under `powerbi/Staffing.Report/definition/pages/`. There is no cached dataset or claimed screenshot of Desktop rendering.

## Tables and relationships

The [export contracts](design.md#export-contracts) describe all six tables. `dim_region` and `dim_model` filter all three facts. `dim_date[date]` filters `fact_demand[date]` and `fact_backtest[date]`. All relationships are one direction from a unique dimension key to many fact rows. Repeated candidate forecasts are deliberately kept in `fact_backtest`, separate from the one-row-per-day demand fact.

## DAX calculations

All 17 measures are stored in [`powerbi/measures.dax`](../powerbi/measures.dax). [`measures.json`](../powerbi/measures.json) is the builder's source. Run `uv run python scripts/build_powerbi.py` after changing the JSON to regenerate the project and DAX reference.

| Measure | Meaning and total behavior |
| --- | --- |
| Actual Tickets | Sum of known actuals, including history |
| Forecast Tickets | Sum of selected evaluation and future predictions in the filter context |
| Matched Actual Tickets | Actuals only on evaluation dates |
| Matched Forecast Tickets | Forecasts only where matched actuals exist, including actual zeroes |
| Forecast Variance Tickets / % | Matched forecast minus matched actual, divided by matched actual for the percentage |
| Evaluation WAPE / MAE | Matched absolute error divided by matched actual volume, or mean error per region/day |
| Future Forecast Tickets | Forecast restricted to the future period |
| Planning Tickets | Future volume including the earlier-error buffer |
| Required Agent Shifts | Calculate and round headcount per future region/day, then sum |
| Required Headcount | Agent shifts only when exactly one date is in context; blank for a multi-day total |
| Peak Daily Headcount | Maximum summed daily need in the selected dates and regions |
| Available Agent Shifts | Sum available people per future region/day |
| Headcount Gap | Required minus available on a single date; blank across multiple dates |
| Backtest WAPE / MAE | Error across the currently filtered region, model, phase and target dates |

For example, two regions each needing 1.2 people require four people after rounding separately. Across seven days, those four people per day produce 28 agent shifts, not 28 simultaneous people. `Required Headcount` deliberately leaves that multi-day total blank. `Peak Daily Headcount` finds the highest daily requirement, while `Required Agent Shifts` measures total scheduled workload. Ratios use `DIVIDE`, so zero denominators remain blank. Staffing calculations round fractional people to 10 decimal places before rounding up, matching Python and Excel at exact capacity boundaries. Any positive workload still needs at least one person.

When comparing models, keep the model dimension in the visual or select one model. A total across all candidate models repeats the same actual targets four times and is a pooled candidate error, not the deployed selected-model accuracy. The demand page's evaluation measures use only regional selections.

## Validation and limits

`uv run python scripts/validate_powerbi.py` validates 17 files against Microsoft's hosted JSON schemas. It needs internet access and sends no report data. The offline pytest suite checks table columns, relationship keys, visual references, measure references and reproducible project generation. `dotnet run --project scripts/PowerBiModelCheck -- powerbi/Staffing.SemanticModel/model.bim` uses Microsoft's Tabular Object Model to parse six tables, eight relationships and 17 measures. CI runs all three checks.

These checks verify the document structure and model metadata. They do not execute Power Query or DAX, render Desktop visuals, or prove service refresh. I have not performed those native-engine checks on this Mac. The committed project and exact setup steps make that final Desktop check reproducible on Windows. The requested report specification is also usable to recreate the pages through Desktop's interface if a preview-format change affects direct opening.
