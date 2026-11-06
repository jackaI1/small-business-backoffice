# creative-brief-tracker

I built a creative brief tracker to learn how the underlying idea works. This is a learning project.

## Using my own Airtable base

Airtable is an editable set of linked tables. Its REST API lets this Python tool read and update those tables over the web. I can change task status in Airtable, then run the reminder command to read the latest state.

1. Create an empty base on Airtable's free plan. Copy its `app...` base ID from the URL.
2. Create a [personal access token](https://airtable.com/create/tokens), a private credential, with access to that base and the scopes `data.records:read`, `data.records:write`, `schema.bases:read` and `schema.bases:write`.
3. Set the two environment variables below. The token stays in the current shell; I never put it in a file that gets committed. `read -s` hides the token while I type it.

```sh
export AIRTABLE_BASE_ID='appYOUR_BASE_ID'
read -s AIRTABLE_TOKEN
export AIRTABLE_TOKEN
uv run brief-tracker setup
uv run brief-tracker seed --data data/sports-campaign.json
uv run brief-tracker remind --today 2026-11-16 --out out/airtable-demo
```

`setup` creates Assignees, Briefs, Deliverables and Approvals with the correct links. It leaves other tables alone and refuses incompatible existing fields. After setup, I can remove the token's schema write permission. [The setup guide](docs/airtable-setup.md) explains fields, statuses and useful table views.

I copy `data/sports-campaign.json` to make my own campaign. Each brief has a description, deadline and ordered steps; each step names a person by their short key, its duration in weekdays, estimated hours and whether it needs approval. Those input files are plans, while Airtable holds current progress. The sample uses reserved `example.test` addresses so it contains no real contact information.

## How I count available time

`CapacityHours` is the time a person has available for the report window, seven calendar days by default. The report counts the full estimated hours of unfinished tasks that have started or will start by the end of that window, including late work. If I change `--days`, I also adjust capacity in Airtable. An approval has its own reminder, but its hours are counted only through its linked task.

This is a conservative warning, not an automatic staffing decision. The tracker does not measure hours already spent, split a task's effort between weeks, skip holidays, enforce review dependencies, or automatically delay downstream work when feedback is late. Its schedules are sequential; I use separate briefs for parallel streams. Email files are drafts only. The local sandbox exercises the same REST client but is not a hosted Airtable account, and automated tests do not claim live Airtable verification.

## Tests and limits

There are 7 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: (removed workflow).

The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.
