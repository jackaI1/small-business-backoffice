# Design and boundaries

The command line is intentionally small: `demo`, `setup`, `seed`, `plan`, `remind`. The real Airtable path and the local demo use `airtable.py`; the sandbox is only a replacement server, not a separate fake tracker implementation.

- `schedule.py` validates ordered review steps and assigns inclusive weekday start/end dates backward from a final deadline. Weekend deadlines roll to Friday. Input is copied, not mutated.
- `setup.py` creates four tables in link dependency order. It checks existing expected fields before adding missing tables, and never modifies an incompatible schema. This needs schema read/write token scopes during setup only.
- `airtable.py` uses HTTPX with 20-second timeouts, pagination offsets and batches of at most ten records. PATCH uses Airtable's `performUpsert` with `Key` as the merge field. Reads and upserts have at most three attempts; table-creation POSTs have one attempt. Tokens go in authorization headers, redirects are disabled, and errors omit server bodies.
- `tracker.py` checks all planned input before writes, resolves assignee/brief/task IDs, then creates linked records. New rows get initial statuses; updates omit Status. Rows absent from input are never deleted. Removing a scheduled task or approval requires explicit cancellation first.
- `reminders.py` reads fresh records once per table, joins by record ID, groups task and approval deadlines by owner and saves standard email files plus structured risk details. Overdue means strictly before the report date. Due today is due, not overdue. Missing fields are handled explicitly because Airtable omits empty fields.
- `sandbox.py` implements the GET/PATCH subset used by seed, plan and reminders, with record IDs, partial updates, pagination and ten-row batch enforcement. Setup uses mocked schema responses in tests because the demo starts with the four tables already available. The sandbox does not implement Airtable permissions, a graphical interface, or every server-side validation rule.

## Consistency and recovery

Airtable's API does not offer a transaction across the four tables. Data and stale-step checks happen before the first write, but a later request can still fail after earlier tables changed. A successful rerun converges by stable Key rather than creating duplicate rows. Table-creation POSTs are not retried; rerunning setup first lists tables to discover what succeeded.

One planner should write to a base at a time. Request spacing is per client, not a distributed rate limiter. Changes to statuses after the client's initial read are preserved for existing rows because updates never send Status. Concurrent creation using the same Key is outside the single-writer model. Treat a new approval after materially changing an approved design as a new step with its own Key, or deliberately reset its Status in Airtable.

## Resource ownership

The sandbox binds only to 127.0.0.1 on an OS-assigned port. It runs a scoped server thread inside the foreground command, records the owning PID, process start, port and cleanup instruction, and closes the listening socket in `finally`. The demo prints this metadata after cleanup with `closed: true`. Tests verify the port refuses a new connection after the context ends, including on a raised exception. HTTP clients are context-managed too. No browser pages or detached background processes are needed.

## Test boundaries

Mocked HTTP tests exercise authentication headers, pagination, batch payloads, rate-limit retries, redacted errors and schema creation links. Pure tests cover workback validation, linked sync and reminder decisions. Local HTTP integration tests use real sockets, and a subprocess test runs the same demo command shown in the README without Airtable environment variables. These do not replace a credentialed smoke test against an actual Airtable base; the repository ships no account, token or live verification claim.
