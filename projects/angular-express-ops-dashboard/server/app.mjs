import express from "express";
import { fileURLToPath } from "node:url";
import {
  metadata,
  records,
  stations,
  utilisation,
  anomalyType,
} from "./data.mjs";

export function parseFilters(query) {
  const { from = metadata.from, to = metadata.to, station = "all" } = query;
  const validDate = (value) =>
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value;
  if (
    !validDate(from) ||
    !validDate(to) ||
    from > to ||
    (Date.parse(to) - Date.parse(from)) / 86400000 > 30
  ) {
    throw new Error(
      "Choose valid dates in order, covering no more than 31 days.",
    );
  }
  if (
    typeof station !== "string" ||
    (station !== "all" && !stations.some((item) => item.id === station))
  ) {
    throw new Error("Choose a station from the list.");
  }
  return { from, to, station };
}
export function selectRecords(filters) {
  return records.filter(
    (row) =>
      row.date >= filters.from &&
      row.date <= filters.to &&
      (filters.station === "all" || row.stationId === filters.station),
  );
}
export function csvCell(value) {
  const text = String(value);
  // Escape spreadsheet formula prefixes as well as commas, quotes and newlines.
  const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}
export function createApp({ apiOnly = false } = {}) {
  const app = express();
  app.disable("x-powered-by");
  app.get("/api/health", (_req, res) => res.json({ status: "ok" }));
  app.get("/api/metadata", (_req, res) => res.json(metadata));
  app.use(
    ["/api/volume", "/api/stations", "/api/anomalies", "/api/export.csv"],
    (req, res, next) => {
      try {
        res.locals.filters = parseFilters(req.query);
        res.locals.rows = selectRecords(res.locals.filters);
        next();
      } catch (error) {
        res.status(400).json({ message: error.message });
      }
    },
  );
  app.get("/api/volume", (_req, res) => {
    const hours = Array.from({ length: 12 }, (_, index) => ({
      hour: index + 12,
      volume: 0,
    }));
    for (const row of res.locals.rows)
      hours[row.hour - 12].volume += row.volume;
    const total = hours.reduce((sum, row) => sum + row.volume, 0);
    const peak = hours.reduce(
      (best, row) => (row.volume > best.volume ? row : best),
      hours[0],
    );
    res.json({ total, peakHour: total ? peak.hour : null, hours });
  });
  app.get("/api/stations", (_req, res) => {
    const result = stations
      .filter(
        (station) =>
          res.locals.filters.station === "all" ||
          station.id === res.locals.filters.station,
      )
      .map((station) => {
        const rows = res.locals.rows.filter(
          (row) => row.stationId === station.id,
        );
        const volume = rows.reduce((sum, row) => sum + row.volume, 0);
        const capacityTotal = rows.reduce((sum, row) => sum + row.capacity, 0);
        return {
          ...station,
          volume,
          capacityTotal,
          utilisation: capacityTotal
            ? Math.round((volume / capacityTotal) * 1000) / 10
            : 0,
        };
      });
    res.json(result);
  });
  app.get("/api/anomalies", (_req, res) => {
    res.json(
      res.locals.rows
        .filter(anomalyType)
        .map((row) => ({
          id: row.id,
          date: row.date,
          hour: row.hour,
          stationId: row.stationId,
          station: stations.find((station) => station.id === row.stationId)
            .name,
          volume: row.volume,
          utilisation: utilisation(row),
          type: anomalyType(row),
        }))
        .sort(
          (a, b) => b.utilisation - a.utilisation || a.id.localeCompare(b.id),
        ),
    );
  });
  app.get("/api/export.csv", (_req, res) => {
    const header = [
      "date",
      "hour",
      "station",
      "volume",
      "hourly_capacity",
      "utilisation_pct",
      "anomaly",
    ];
    const lines = res.locals.rows.map((row) => [
      row.date,
      row.hour,
      row.stationId,
      row.volume,
      row.capacity,
      utilisation(row),
      anomalyType(row) ?? "",
    ]);
    const { from, to } = res.locals.filters;
    res.set(
      "Content-Disposition",
      `attachment; filename="venue-${from}-to-${to}.csv"`,
    );
    res
      .type("text/csv")
      .send(
        [header, ...lines]
          .map((row) => row.map(csvCell).join(","))
          .join("\r\n") + "\r\n",
      );
  });
  if (apiOnly) return app;
  app.use("/api", (_req, res) =>
    res.status(404).json({ message: "API route not found." }),
  );
  const browser = fileURLToPath(
    new URL("../dist/venue/browser/", import.meta.url),
  );
  app.use(express.static(browser));
  app.get("/{*path}", (_req, res) =>
    res.sendFile("index.html", { root: browser }),
  );
  return app;
}
