import express from "express";
import { test } from "node:test";
import assert from "node:assert/strict";
import request from "supertest";
import { createApp, csvCell } from "./app.mjs";
import { records } from "./data.mjs";
const app = createApp();
test("dataset has 336 unique, reproducible station hours", () => {
  assert.equal(records.length, 336);
  assert.equal(new Set(records.map((row) => row.id)).size, 336);
});
test("health and metadata describe the sample week", async () => {
  await request(app).get("/api/health").expect(200, { status: "ok" });
  const { body } = await request(app).get("/api/metadata").expect(200);
  assert.equal(body.stations.length, 4);
  assert.equal(body.from, "2026-10-26");
  assert.equal(body.to, "2026-11-01");
});
test("hourly totals equal the underlying dataset", async () => {
  const { body } = await request(app).get("/api/volume").expect(200);
  assert.equal(
    body.total,
    records.reduce((sum, row) => sum + row.volume, 0),
  );
  assert.equal(body.hours.length, 12);
  assert.equal(
    body.peakHour,
    body.hours.reduce((a, b) => (a.volume > b.volume ? a : b)).hour,
  );
});
test("date and station filters apply together and include both endpoints", async () => {
  const { body } = await request(app)
    .get("/api/volume?from=2026-10-30&to=2026-10-30&station=north")
    .expect(200);
  assert.equal(
    body.total,
    records
      .filter((row) => row.date === "2026-10-30" && row.stationId === "north")
      .reduce((sum, row) => sum + row.volume, 0),
  );
  assert.equal(body.hours.find((row) => row.hour === 18).volume, 230);
});
test("station utilisation is capacity weighted, not a sum of percentages", async () => {
  const { body } = await request(app)
    .get("/api/stations?station=north")
    .expect(200);
  assert.equal(body.length, 1);
  assert.equal(body[0].capacityTotal, 180 * 12 * 7);
  assert.equal(
    body[0].utilisation,
    Math.round((body[0].volume / body[0].capacityTotal) * 1000) / 10,
  );
});
test("anomalies include surge and quiet thresholds, sorted by pressure", async () => {
  const { body } = await request(app).get("/api/anomalies").expect(200);
  assert.equal(body[0].id, "2026-10-30-18-north");
  assert.equal(body[0].utilisation, 127.8);
  assert.ok(
    body.some(
      (row) => row.id === "2026-10-28-14-information" && row.type === "quiet",
    ),
  );
  assert.ok(
    body.every((row) =>
      row.type === "surge" ? row.utilisation >= 95 : row.utilisation < 25,
    ),
  );
});
test("empty dates return zero totals, no peak, no anomalies, no capacity", async () => {
  const query = "?from=2026-12-01&to=2026-12-01";
  const volume = await request(app)
    .get("/api/volume" + query)
    .expect(200);
  assert.equal(volume.body.total, 0);
  assert.equal(volume.body.peakHour, null);
  await request(app)
    .get("/api/anomalies" + query)
    .expect(200, []);
  const stations = await request(app)
    .get("/api/stations" + query)
    .expect(200);
  assert.ok(
    stations.body.every(
      (row) => row.capacityTotal === 0 && row.utilisation === 0,
    ),
  );
});
for (const [name, query] of [
  ["reversed range", "from=2026-11-01&to=2026-10-26"],
  ["impossible date", "from=2026-02-30"],
  ["invalid date", "from=oops"],
  ["oversized range", "from=2026-01-01&to=2026-12-31"],
  ["unknown station", "station=not-a-station"],
  ["duplicate station", "station=north&station=south"],
])
  test(`rejects ${name}`, async () => {
    await request(app)
      .get("/api/volume?" + query)
      .expect(400);
  });
test("CSV uses applied filters, quoted fields, and a download filename", async () => {
  const result = await request(app)
    .get("/api/export.csv?from=2026-10-30&to=2026-10-30&station=north")
    .expect(200);
  assert.match(result.headers["content-type"], /text\/csv/);
  assert.match(
    result.headers["content-disposition"],
    /venue-2026-10-30-to-2026-10-30.csv/,
  );
  const lines = result.text.trim().split("\r\n");
  assert.equal(lines.length, 13);
  assert.ok(
    lines
      .slice(1)
      .every(
        (row) => row.includes('"north"') && row.startsWith('"2026-10-30"'),
      ),
  );
  assert.ok(lines.some((row) => row.includes('"230","180","127.8","surge"')));
});
test("CSV protects formula prefixes and escapes embedded quotes", () => {
  assert.equal(csvCell("=1+1"), '"\'=1+1"');
  assert.equal(csvCell('a,"b"'), '"a,""b"""');
});
test("unknown API route returns JSON 404 instead of the app shell", async () => {
  await request(app)
    .get("/api/missing")
    .expect(404, { message: "API route not found." });
});

test("venue routes delegate unrelated production filters to their host", async () => {
  const host = express();
  host.use(createApp({ apiOnly: true }));
  host.get("/api/summary", (_req, res) => res.json({ production: true }));
  await request(host)
    .get("/api/summary?line=alpha&from=2026-10-01")
    .expect(200, { production: true });
  await request(host).get("/api/volume?station=north").expect(200);
});
