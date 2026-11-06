# Design notes

I wanted one place to answer three questions: when was the venue busiest, which station faced the most pressure, and which hours deserve a closer look?

## Screens and layout

I used a slate background (`#edf2f6`), white working surfaces (`#ffffff`), ink text (`#203649`), blue hourly bars (`#2458a6`), teal station meters (`#287f81`), and amber surge flags (`#936016`). Avenir Next, with local system fallbacks, gives the headings a compact feel without a font download. Labels remain sentence case, and the numbers use aligned digits.

The hourly chart is the main visual. Station comparisons sit alongside it on wide screens, and anomaly rows span the width below. On phones, the panels stack and only the anomaly table scrolls horizontally. The controls, headings, and values stay left aligned. I avoided an extra row of disconnected metric cards: totals and peak hour belong with the hourly chart they describe.

```text
Navigation: Shift overview | Anomaly review
Date range + station + apply + export
Hourly volume (wide)       | Station utilisation
Hours worth a closer look (full width)
```

The review route replaces the three-panel overview with the full anomaly table and a surge/quiet selector. Both routes share applied filters.

## Synthetic dataset and calculations

`server/data.mjs` generates 7 dates × 12 hours × 4 stations = 336 records using fixed arithmetic. The dates are 2026-10-26 through 2026-11-01, inclusive, and hours are venue-local 12 through 23. There are no time zone conversions or visitor-level records. `volume` counts interactions, not distinct people.

Each station has a fixed handling capacity per hour. Utilisation is `volume / capacity * 100`, rounded to one decimal place. For multiple hours, I divide the sum of volume by the sum of capacity. I do not add percentages. Ratios above 100% are meaningful demand pressure; the visual meter stops at 100%, but the numeric label retains the full ratio.

The volume endpoint groups all selected dates by hour of day. Peak hour is the first hour with the maximum volume; no activity yields `null`. Stations without records have zero activity and capacity. The anomaly endpoint computes surge (utilisation >=95%) and quiet (<25%) labels from individual station hours and sorts highest utilisation first. The overview shows the first five; the review route shows all matching rows. This is threshold detection, not a statistical anomaly model.

## Angular request lifecycle

`FiltersComponent` owns a typed, non-nullable `FormGroup` for from/to/station. A group validator checks real calendar dates, ordering, and a maximum of 31 inclusive days. Applying a valid form writes query parameters. Shared links and browser navigation restore the form from the route. An invalid link displays a warning and loads the default dataset until corrected.

`DataService` owns applied filters in a `BehaviorSubject`, an observable with a current value. Each panel combines filter changes with its own retry subject. Nested `switchMap` cancels obsolete requests, including retries from an old filter selection. `catchError` is inside the request stream, so an error does not terminate later updates. `startWith` emits loading for every request, and `shareReplay` shares one current response among subscribers. Its reference counting and Angular async pipes release subscriptions when the route is destroyed. The metadata and download subscriptions use `takeUntilDestroyed` as well.

`PanelComponent` consistently renders loading and errors, with a panel-specific retry button. Projection only displays ready content, avoiding a stale chart during a new request. A separate metadata error can be retried while the charts remain visible. Download failures keep the Export CSV button available. I capture the applied filters when an export begins so the filename continues to describe its response if filters change while it downloads.

## API contract

All data routes accept `from=YYYY-MM-DD`, `to=YYYY-MM-DD`, and `station=all|north|south|concessions|information`. Dates are inclusive. Defaults cover the sample week. Malformed, duplicated, reversed, and oversized filters return JSON with HTTP 400. Valid dates outside the sample dataset return empty results.

| GET route         | Response                                                              |
| ----------------- | --------------------------------------------------------------------- |
| `/api/health`     | Health status                                                         |
| `/api/metadata`   | Date bounds and station names/capacity                                |
| `/api/volume`     | Total, peak hour, 12 hourly counts                                    |
| `/api/stations`   | Volume, summed capacity, weighted utilisation per selected station    |
| `/api/anomalies`  | Flagged station hours sorted by utilisation                           |
| `/api/export.csv` | All matching station-hour rows, including capacity and anomaly labels |

The CSV quotes every cell, escapes quotes, and neutralises spreadsheet formula prefixes. The download uses the applied date/station filters, not unsubmitted form edits or the review-only Show selector. Unknown API routes return JSON 404; non-API routes serve the Angular shell for direct navigation.

## Running and verifying

The Angular 20 app uses strict TypeScript and strict template checking. Express 5 serves both built apps and the API from one local origin. The production app stays at `/`, while the venue app is mounted at `/venue/`. The host in `server/src/index.ts` combines the original database-backed API with venue-only routes, so venue filter validation never intercepts production queries. Each Angular build keeps its own pinned compiler version: the existing production workspace uses Angular 22, and the venue app uses Angular 20 with Jasmine/Karma. In development, both Angular servers proxy `/api` to Express. The production view uses port 4200, and the venue view uses port 4201. The Node scripts forward termination signals to owned child processes; test servers use Playwright's graceful shutdown and never reuse unrelated listeners.

Jasmine/Karma unit tests use Angular TestBed and HttpTestingController to test actual forms, rendered panels, cancellation, request sharing, retries, and CSV parameters. Node tests exercise the Express app through HTTP, including arithmetic and invalid inputs. Playwright runs against the production build in Chromium at desktop and mobile sizes; it checks the real CSV bytes as well as user-visible chart totals. Only failure/loading tests intercept requests.

Useful references: [Angular typed forms](https://angular.dev/guide/forms/typed-forms), [Angular HTTP testing](https://angular.dev/guide/http/testing), and [RxJS switchMap](https://rxjs.dev/api/operators/switchMap).
