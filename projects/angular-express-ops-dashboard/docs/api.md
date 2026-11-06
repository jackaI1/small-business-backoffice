# API reference

I keep aggregation on the server so the cards and comparisons cover every matching run, independently of the current table page. All addresses are under `/api` and return JSON. Start the app using the root README first.

## Filters

`/summary`, `/lines`, `/trends` and `/runs` accept the same optional filters:

| Parameter | Values |
| --- | --- |
| `from` | Inclusive start date, a real date in `YYYY-MM-DD` form |
| `to` | Inclusive end date in the same form, on or after `from` |
| `line` | `alpha`, `beta`, `gamma` (displayed as Line A, B, C) |
| `status` | `complete`, `delayed` |

Omit a filter for all values. Empty, unknown, repeated or array-shaped parameters are rejected. Pagination parameters are accepted only on `/runs`. A calendar day is stored as a date, with no timezone conversion.

`/runs` also accepts `page` (default 1, maximum 100000) and `pageSize` (default 20, maximum 100). Both must be positive whole-number decimal strings. A page beyond the end returns an empty array and the actual record count. Rows are ordered by date descending, then id descending. The demo is read-only; concurrent external database edits could shift offset pages.

## Responses

`GET /api/summary?line=alpha&from=2026-10-01&to=2026-10-01`:

```json
{"runs":2,"planned":800,"produced":689,"rejected":7,"good":682,"downtimeMinutes":40,"rejectionRate":1.02}
```

`good` is produced minus rejected. `rejectionRate` is `100 * SUM(rejected) / SUM(produced)`, rounded to two decimal places. It is `null` when no units were produced. Empty summary queries return zero counts and a null rate.

`/lines` returns `{"data":[...]}` with a `line` field and the same totals for each matching line. `/trends` uses a `date` field and sorts days ascending. Groups without matching records are omitted rather than filled with invented zeros.

`/runs` returns the raw records and page metadata:

```json
{
  "data":[{"id":1179,"date":"2026-10-30","line":"gamma","shift":"night","status":"complete","planned":600,"produced":586,"rejected":7,"downtimeMinutes":5}],
  "page":1,"pageSize":1,"total":180,"totalPages":180
}
```

The sample dates and values are deterministic. `shift` is `day` or `night`; downtime is in minutes.

## Errors and limits

Invalid filters return HTTP 400:

```json
{"error":{"code":"INVALID_QUERY","message":"Check the query parameters.","details":[{"field":"pageSize","message":"Too big: expected number to be <=100"}]}}
```

Unknown routes return 404 with `NOT_FOUND`. Unexpected failures return 500 with `INTERNAL_ERROR` and a generic message; database details and stack traces stay out of the response. Validation error text can change between library versions; use the code and field to classify it.

All API routes share a 300-request, 60-second window per direct client address. HTTP 429 uses `RATE_LIMITED` and includes `Retry-After` in seconds. Standard rate-limit headers report the window. The local server does not trust forwarding headers. The in-memory limit resets on restart and is not shared across processes. There is no authentication; this server binds to the loopback interface.
