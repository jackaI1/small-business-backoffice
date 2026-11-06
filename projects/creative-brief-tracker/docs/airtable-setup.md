# Base setup and daily use

From the repository folder, run the README's environment-variable commands and `uv run brief-tracker setup`. The tool uses Airtable's schema API, which creates table definitions rather than campaign records. The empty base needs no paid extensions, Airtable automations or collaborator accounts. A base may contain Airtable's default empty table; setup leaves it alone.

The first field in every created table is `Key` (single-line text). Do not rename, edit or duplicate generated keys. `Name` is a readable label. Link fields contain Airtable record IDs rather than a person's display name. Airtable creates reciprocal link fields automatically; those additional fields are harmless.

| Table | Fields created by setup |
| --- | --- |
| Assignees | Key, Name, Email (email), CapacityHours (number) |
| Briefs | Key, Name, Description (long text), Due (date), Status |
| Deliverables | Key, Name, Brief (link to Briefs), Assignee (link to Assignees), Start and Due (dates), Hours (number), Status |
| Approvals | Key, Name, Deliverable (link to Deliverables), Assignee (link to Assignees), Due (date), Status |

Other than the types noted, fields are single-line text. Status uses text so no paid configuration or pre-created choices are needed. Use these exact status values:

| Table | Active values | Closed values |
| --- | --- | --- |
| Briefs | Active | Done, Cancelled |
| Deliverables | Planned, In progress, Blocked | Done, Cancelled |
| Approvals | Pending, Changes requested | Approved, Cancelled |

Unknown or blank statuses are treated as unfinished. Completing a deliverable does not approve it. Cancelling a deliverable suppresses its approval reminders. Cancelling or completing a brief suppresses its child reminders and capacity use. Existing status fields survive both seed and replanning.

Suggested Airtable views:

- Deliverables: group by Assignee, sort Due ascending, hide Done and Cancelled.
- Approvals: filter out Approved and Cancelled, sort Due ascending.
- Briefs: group by Status, sort Due ascending.

These are optional manual views, not required for the Python tool.

## Input and operating steps

1. Copy the sample campaign JSON. Keep personal campaign files outside this public checkout or in an ignored location. Enter unique person and brief keys made from letters, digits, underscores or hyphens.
2. List steps in forward order. `days` is an integer from 1 to 260; `hours` and capacity are finite nonnegative numbers. `approval: true` creates a pending review row for that task's owner.
3. Run `seed --data /path/to/campaign.json`. The entire input is validated before writes. Missing assignees, duplicate keys and invalid dates stop the import.
4. Update task/approval statuses in Airtable as work proceeds. Set each person's `CapacityHours` for the next report's window.
5. Use `plan` with the existing brief key, new deadline and a JSON list of steps to revise dates. New step keys add tasks. Before removing an existing step, cancel both its task and any approval in Airtable.
6. Run `remind` with a fresh output folder. Review warnings and `report.json`, then open the `.eml` drafts. Add a sender in the mail app if needed. Nothing sends automatically.

With real data, protect the output directory: report JSON and email drafts contain names, addresses and campaign details. `out/` is ignored by git. No workflow uploads these files.

## Troubleshooting

- HTTP 401/403: check the credential's scopes, base access and your Airtable permissions. No automatic retries for denied access.
- HTTP 422: check that fields still match the table above and that `Key` values are unique. Setup checks existing schemas but does not repair incompatible tables.
- HTTP 429: the client waits 30 seconds, then retries, up to three attempts. If quota is exhausted, wait for the monthly reset. Avoid running several clients against the same base at once.
- Interrupted setup: rerun setup. Existing compatible tables are reused. Schema table creation is not automatically retried because it could duplicate a table after an uncertain network failure.
- Interrupted seed/plan: rerun the same command. Stable keys let completed batches update the same rows. Airtable does not provide a multi-table transaction, so partial writes can be visible until the rerun finishes.

References: [API introduction](https://support.airtable.com/articles/6292134965-getting-started-with-airtable-s-web-api), [personal access tokens](https://airtable.com/create/tokens), [Airtable REST API](https://airtable.com/developers/web/api/introduction).
