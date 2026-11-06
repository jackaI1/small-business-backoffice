# Design notes

I wanted a short path from a production question to the records that explain it: filter the runs, compare the totals, then inspect a page of records. The data is fictional so the repository can be public and run without access to any facility.

## Data and request flow

The Angular form keeps draft filters separate from applied filters. Applying them resets the table to page one and requests four typed responses in parallel. Changing pages keeps the applied filters. An older in-flight request is cancelled before a new one starts. Loading and error states hide old totals, so an unsuccessful filter cannot leave an earlier result looking current.

Express validates parameters with strict Zod schemas before running SQL. SQLite computes sums, grouped daily totals and line comparisons. Every filter value is bound as a parameter; the only SQL identifiers and operators come from fixed server code. Pagination uses a capped page size and a date/id sort. Shared TypeScript response types live in `server/src/contracts.ts` and are imported as types by Angular.

The database schema constrains counts, line names, shifts, statuses and rejection totals. A single transaction replaces the marked demo rows with 30 days, three lines and two shifts per day. Fixed integer formulas provide variation without random values or dependence on the clock. A conflicting non-demo ID fails and rolls back the seed instead of replacing that row.

## Local operation

I chose Node 24's built-in SQLite driver to keep setup small. Its queries are synchronous, which suits this small read-only dataset; a larger service would need to measure request blocking and move to a worker or a database driver suitable for higher concurrency. The server owns the database connection, closes it on shutdown, and serves the compiled Angular files on the same origin. Development uses Angular's proxy for `/api` requests.

I chose SQLite over PostgreSQL because the demo does not need multiple database writers and I wanted a clean checkout to run without a database service. I chose server aggregation over browser aggregation so pagination never changes the totals.

## Interface

The dashboard is an operating view, with a short filter form, a summary strip, a line comparison beside daily totals, and the records underneath. Slate text (`#23364a`), blue comparisons (`#2877ac`) and a pale workspace (`#f4f7fa`) keep the tables legible. Delayed status uses both text and color. Tables use aligned numbers; overflowing tables have keyboard-focusable scroll regions. At narrow widths the filters wrap and the comparison sections stack. Focus outlines and error, loading and empty states are explicit.

## Verification boundaries

The API tests use real SQLite and Supertest rather than a mocked query layer. The Angular tests use Angular's HTTP testing backend to check requests and rendered states. The compiled-app smoke test runs the actual seed command twice, compares every generated row, launches the compiled server on an ephemeral port, checks responses and the Angular bundle, then stops the owned process in a finally block. It checks process exit before removing its temporary database.

There is no external service, background worker or persistent test server. Local browser checks close every test page and owned browser process. The rate limit is per process, the dataset is deliberately small, and this demo is not a multi-user production deployment.
